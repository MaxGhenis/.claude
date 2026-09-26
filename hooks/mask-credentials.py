#!/usr/bin/env python3
"""Keep Anthropic credentials out of tool output and tool input (d077).

PostToolUse (matcher "*"): masks every sk-ant-{oat01,ort01,api03,admin01}-...
string in the tool response through `hookSpecificOutput.updatedToolOutput`,
keeping the response's shape, and appends a fingerprint-only sighting to
~/.claude/state/credential-sightings.jsonl so a leak can be rotated.

PreToolUse (matcher "*"): refuses a tool call whose input carries a literal
credential, and a Bash command that would put a credential into a tmux or
screen command line, where any `ps` can read it.

Decision d077 (Max, 2026-09-25). Tests: uvx pytest tests/test_mask_credentials.py
Never prints a credential. Fails open: a hook error must not block tools.
"""
import hashlib
import json
import os
import re
import sys
import time

PAT = re.compile(r"sk-ant-(oat01|ort01|api03|admin01)-[A-Za-z0-9_\-]{20,}")
CRED_VARS = r"(CLAUDE_CODE_OAUTH_TOKEN|ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN)"
# A credential on a tmux spawn/setenv command line lands in the tmux server's argv
# (tmux keeps the first client's arguments). `send-keys 'export VAR="$(...)"'` is
# the safe form and is not matched. Only an expanded (`$...`) or literal value
# counts, so text that merely mentions the pattern (`VAR=<token>` in a commit
# message, a grep regex) is not refused.
VALUE = r"""["']?(\$|sk-ant-)"""
TMUX_SPAWN = re.compile(
    r"\btmux\b[^\n;|&]*\b(new-session|new|new-window|neww|respawn-pane|respawnp|"
    r"respawn-window|respawnw|split-window|splitw)\b[^\n;|&]*\b" + CRED_VARS + "=" + VALUE)
TMUX_SETENV = re.compile(
    r"\btmux\b[^\n;|&]*\b(set-environment|setenv)\b[^\n;|&]*\b" + CRED_VARS + r"\s+" + VALUE)
SCREEN_ARGV = re.compile(r"\bscreen\b[^\n;|&]*\b" + CRED_VARS + "=" + VALUE)
LEDGER = os.environ.get(
    "CREDENTIAL_SIGHTINGS_LEDGER",
    os.path.expanduser("~/.claude/state/credential-sightings.jsonl"),
)


def fingerprint(s):
    return hashlib.sha256(s.encode()).hexdigest()[:10]


def mask_text(text, seen):
    def repl(m):
        fp = fingerprint(m.group(0))
        seen.add((m.group(1), fp))
        return f"sk-ant-{m.group(1)}-[MASKED fp={fp}]"
    return PAT.sub(repl, text)


def mask(value, seen):
    if isinstance(value, str):
        return mask_text(value, seen) if "sk-ant-" in value else value
    if isinstance(value, list):
        return [mask(v, seen) for v in value]
    if isinstance(value, dict):
        return {k: mask(v, seen) for k, v in value.items()}
    return value


def record(event, seen):
    try:
        os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
        with open(LEDGER, "a") as h:
            for kind, fp in sorted(seen):
                h.write(json.dumps({
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "hook": event.get("hook_event_name"),
                    "tool": event.get("tool_name"),
                    "type": kind,
                    "fp": fp,
                    "session_id": event.get("session_id"),
                    "transcript_path": event.get("transcript_path"),
                }) + "\n")
    except OSError:
        pass


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.exit(0)


def main():
    raw = sys.stdin.read()
    if "sk-ant-" not in raw and '"PreToolUse"' not in raw:
        sys.exit(0)  # fast path: no credential in a PostToolUse payload
    event = json.loads(raw)
    name = event.get("hook_event_name")
    tool = event.get("tool_name")

    if name == "PreToolUse":
        seen = set()
        mask(event.get("tool_input"), seen)
        if seen:
            record(event, seen)
            emit({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "mask-credentials: this tool call carries a literal Anthropic "
                    "credential. Never copy a token into a command or file; read it "
                    "inside the process that needs it (e.g. "
                    "VAR=\"$(agent-secret get SERVICE ACCOUNT)\" cmd) and never echo it."),
            }})
        command = (event.get("tool_input") or {}).get("command", "") if tool == "Bash" else ""
        if command and any(p.search(command) for p in (TMUX_SPAWN, TMUX_SETENV, SCREEN_ARGV)):
            emit({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "mask-credentials: a credential variable on a tmux/screen command "
                    "line ends up in that server's argv, which any `ps` prints. Fetch "
                    "the credential "
                    "inside the pane instead, e.g. send-keys 'export VAR=\"$(agent-secret "
                    "get SERVICE ACCOUNT)\"'."),
            }})
        sys.exit(0)

    if name == "PostToolUse":
        seen = set()
        masked = mask(event.get("tool_response"), seen)
        if not seen:
            sys.exit(0)
        record(event, seen)
        emit({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": masked,
            "additionalContext": (
                f"mask-credentials: {len(seen)} Anthropic credential string(s) in this "
                "tool output were masked before you saw them. Do not try to recover, "
                "print or copy them. Tell the user a credential was exposed (fingerprint "
                "shown in the mask) so it can be rotated."),
        }})
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # fail open
        sys.stderr.write(f"mask-credentials: hook error ignored: {type(exc).__name__}\n")
        sys.exit(0)
