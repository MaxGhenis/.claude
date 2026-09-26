"""Unit tests for mask-credentials.py. Fake tokens only (marker TESTONLYFAKE)."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "mask-credentials.py"
# Assembled at runtime so this file never holds a complete credential-shaped string.
FAKE = "sk-ant-" + "oat01-" + "TESTONLYFAKE" * 8
FAKE_API = "sk-ant-" + "api03-" + "TESTONLYFAKE" * 7 + "-AA"
FP = hashlib.sha256(FAKE.encode()).hexdigest()[:10]


def run(event, tmp_path):
    env = dict(os.environ, CREDENTIAL_SIGHTINGS_LEDGER=str(tmp_path / "ledger.jsonl"))
    done = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event),
                          capture_output=True, text=True, env=env, timeout=20)
    assert done.returncode == 0, done.stderr
    assert FAKE not in done.stdout and FAKE_API not in done.stdout
    assert FAKE not in done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else None


def ledger(tmp_path):
    p = tmp_path / "ledger.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def post(tool, response):
    return {"hook_event_name": "PostToolUse", "tool_name": tool, "session_id": "s1",
            "transcript_path": "/tmp/t.jsonl", "tool_input": {}, "tool_response": response}


def pre(tool, tool_input):
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "s1",
            "transcript_path": "/tmp/t.jsonl", "tool_input": tool_input}


def test_bash_output_masked_shape_kept(tmp_path):
    resp = {"stdout": f"pid 1 tmux new-session -e CLAUDE_CODE_OAUTH_TOKEN={FAKE}\n",
            "stderr": "", "interrupted": False, "isImage": False}
    out = run(post("Bash", resp), tmp_path)
    upd = out["hookSpecificOutput"]["updatedToolOutput"]
    assert set(upd) == set(resp)
    assert upd["interrupted"] is False and upd["isImage"] is False
    assert f"sk-ant-oat01-[MASKED fp={FP}]" in upd["stdout"]
    assert "CLAUDE_CODE_OAUTH_TOKEN=" in upd["stdout"]
    assert "additionalContext" in out["hookSpecificOutput"]
    rows = ledger(tmp_path)
    assert [(r["type"], r["fp"], r["tool"]) for r in rows] == [("oat01", FP, "Bash")]


def test_env_dump_masks_every_credential_type(tmp_path):
    resp = {"stdout": f"ANTHROPIC_API_KEY={FAKE_API}\nCLAUDE_CODE_OAUTH_TOKEN={FAKE}\nHOME=/x\n",
            "stderr": "", "interrupted": False, "isImage": False}
    upd = run(post("Bash", resp), tmp_path)["hookSpecificOutput"]["updatedToolOutput"]
    assert upd["stdout"].count("[MASKED fp=") == 2 and "HOME=/x" in upd["stdout"]
    assert {r["type"] for r in ledger(tmp_path)} == {"api03", "oat01"}


def test_read_and_mcp_shapes(tmp_path):
    read = {"type": "text", "file": {"filePath": "/x/.env", "content": f"KEY={FAKE}\n",
                                     "numLines": 1, "startLine": 1, "totalLines": 1}}
    upd = run(post("Read", read), tmp_path)["hookSpecificOutput"]["updatedToolOutput"]
    assert upd["file"]["numLines"] == 1 and "[MASKED" in upd["file"]["content"]
    mcp = [{"type": "text", "text": f"token: {FAKE}"}]
    upd = run(post("mcp__x__y", mcp), tmp_path)["hookSpecificOutput"]["updatedToolOutput"]
    assert upd == [{"type": "text", "text": f"token: sk-ant-oat01-[MASKED fp={FP}]"}]


def test_clean_output_is_untouched(tmp_path):
    assert run(post("Bash", {"stdout": "sk-ant- mentioned but no token", "stderr": "",
                             "interrupted": False, "isImage": False}), tmp_path) is None
    assert run(post("Bash", {"stdout": "hello", "stderr": "", "interrupted": False,
                             "isImage": False}), tmp_path) is None
    assert ledger(tmp_path) == []


def test_literal_token_in_input_is_denied(tmp_path):
    for tool, inp in [("Bash", {"command": f"echo {FAKE}"}),
                      ("Write", {"file_path": "/tmp/x", "content": f"t={FAKE}"})]:
        out = run(pre(tool, inp), tmp_path)["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny"
        assert "literal Anthropic credential" in out["permissionDecisionReason"]


@pytest.mark.parametrize("command", [
    'tmux new-session -d -s orchestrator -e CLAUDE_CODE_OAUTH_TOKEN="$(agent-secret get claude-quota-x maxghenis)" claude',
    'tmux new-session -d -s orchestrator -c /tmp CLAUDE_CODE_OAUTH_TOKEN=$T claude --resume abc',
    'tmux new-window -t s -e ANTHROPIC_API_KEY="$K" python run.py',
    'tmux set-environment -g CLAUDE_CODE_OAUTH_TOKEN "$T"',
    'screen -dmS lane env CLAUDE_CODE_OAUTH_TOKEN=$T claude',
])
def test_multiplexer_argv_denied(tmp_path, command):
    out = run(pre("Bash", {"command": command}), tmp_path)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "argv" in out["permissionDecisionReason"]


@pytest.mark.parametrize("command", [
    "tmux send-keys -t lane 'export CLAUDE_CODE_OAUTH_TOKEN=\"$(agent-secret get claude-quota-x maxghenis)\"' Enter",
    "ps aux | grep claude",
    'CLAUDE_CODE_OAUTH_TOKEN="$(agent-secret get claude-quota-x maxghenis)" claude -p hi',
    "tmux new-session -d -s work 'bash -l'",
    "tmux capture-pane -p -t lane",
    # Text that mentions the pattern is not a launch (e.g. a commit message or a grep).
    "git commit -F - <<'EOF'\n`ps` output showing `tmux new-session -e CLAUDE_CODE_OAUTH_TOKEN=<token>`\nEOF",
    "grep -rn -E 'tmux new-session.*CLAUDE_CODE_OAUTH_TOKEN=' ~/m6-sol-lanes",
    "echo 'never run: tmux set-environment -g CLAUDE_CODE_OAUTH_TOKEN <value>'",
])
def test_safe_commands_allowed(tmp_path, command):
    assert run(pre("Bash", {"command": command}), tmp_path) is None


def test_malformed_input_fails_open(tmp_path):
    env = dict(os.environ, CREDENTIAL_SIGHTINGS_LEDGER=str(tmp_path / "l.jsonl"))
    for stdin in ["not json sk-ant-", '{"hook_event_name": "PreToolUse", ', ""]:
        done = subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True,
                              text=True, env=env, timeout=20)
        assert done.returncode == 0 and done.stdout == ""
