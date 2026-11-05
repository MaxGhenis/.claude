"""Tests for hooks/enforce-package-managers.sh, focused on its GitNexus rules.

Run: uv run --no-project --with pytest --with hypothesis pytest tests/test_enforce_package_managers.py -q -p no:cacheprovider

They run the real hook with a real JSON payload. Invariants, for every command:
  G1  a floating GitNexus runner is blocked, whichever runner, flags and version it names;
  G2  the pinned CLI and the index tool pass;
  G3  a command that only mentions gitnexus as text, or names another package, passes the GitNexus
      rules;
  G4  the hook always prints one JSON decision and exits 0.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from hypothesis import given, settings, strategies as st
import pytest


HOOK = Path(__file__).resolve().parents[1] / "hooks/enforce-package-managers.sh"


def decide(command: str) -> dict:
    result = subprocess.run(
        ["/bin/bash", str(HOOK)],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    # G4
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def floating_reason(command: str) -> bool:
    decision = decide(command)
    return decision["decision"] == "block" and "pinned" in decision["reason"]


RUNNERS = ["bunx", "npx", "pnpm dlx", "pnpm --silent dlx", "yarn dlx"]
FLAGS = ["", "-y", "--yes", "-y --quiet"]
VERSIONS = ["", "@latest", "@1.6.13", "@next"]
SUBCOMMANDS = ["", "analyze", "mcp", "status", "impact foo"]
PREFIXES = ["", "cd /tmp/x && ", "true; ", "(", "FOO=1 "]


@settings(max_examples=60, deadline=None)
@given(
    st.sampled_from(RUNNERS),
    st.sampled_from(FLAGS),
    st.sampled_from(VERSIONS),
    st.sampled_from(SUBCOMMANDS),
    st.sampled_from(PREFIXES),
)
def test_floating_runners_are_blocked(runner, flags, version, subcommand, prefix):
    # G1
    words = [word for word in (runner, flags, f"gitnexus{version}", subcommand) if word]
    assert floating_reason(prefix + " ".join(words))


@pytest.mark.parametrize(
    "command",
    [
        "gitnexus update",
        "cd /tmp/x && gitnexus update",
        "/some/where/.bin/gitnexus update",
    ],
)
def test_self_update_is_blocked(command):
    assert floating_reason(command)


@pytest.mark.parametrize(
    "command",
    [
        "gitnexus status",
        "gitnexus analyze --index-only",
        "gitnexus-index refresh axiom-corpus",
        "gitnexus-index doctor --probe",
        "~/.local/share/gitnexus-current/node_modules/.bin/gitnexus list",
        "git commit -m 'stop floating runners'",
    ],
)
def test_pinned_cli_and_tool_pass(command):
    # G2
    assert decide(command)["decision"] == "approve"


@pytest.mark.parametrize(
    "command",
    [
        "bunx gitnexus-plugin run",
        "bunx some-tool gitnexus",
        "grep -n 'gitnexus update' notes.md",
        'grep -n "bunx gitnexus" notes.md',
        "bun add -d vitest",
    ],
)
def test_other_packages_and_mentions_pass(command):
    # G3
    assert decide(command)["decision"] == "approve"


def test_setup_stays_blocked_with_its_own_reason():
    decision = decide("gitnexus setup")
    assert decision["decision"] == "block"
    assert "setup" in decision["reason"]


def test_existing_rules_still_apply():
    assert decide("pip install requests")["decision"] == "block"
    assert decide("npx tsc")["decision"] == "block"
