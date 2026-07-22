#!/bin/bash
# Test harness for hooks/guard-never-rules.sh
# Builds throwaway git fixtures, feeds synthetic PreToolUse JSON, asserts decisions.
# Usage: bash ~/.claude/tests/guard-never-rules-test.sh   (exit 0 = all pass)

set -u
HOOK="$HOME/.claude/hooks/guard-never-rules.sh"
FIX="$(mktemp -d "${TMPDIR:-/tmp}/guard-test-XXXXXX")"
trap 'rm -rf "$FIX"' EXIT

PASS=0; FAIL=0

git_q() { git "$@" >/dev/null 2>&1; }

# --- fixtures ---
# plain: single-worktree repo, no origin
mkdir -p "$FIX/plain" && cd "$FIX/plain" && git_q init -b main && git_q commit --allow-empty -m init

# shared: repo with a second worktree
mkdir -p "$FIX/shared" && cd "$FIX/shared" && git_q init -b main && git_q commit --allow-empty -m init
git_q worktree add "$FIX/shared-wt2" -b wt2

# withorigin: clone of a bare origin (origin/main exists); currently on main, plus branch "other"
mkdir -p "$FIX/origin.git" && cd "$FIX/origin.git" && git_q init --bare -b main
mkdir -p "$FIX/seed" && cd "$FIX/seed" && git_q init -b main && git_q commit --allow-empty -m init \
  && git_q remote add origin "$FIX/origin.git" && git_q push origin main
git_q clone "$FIX/origin.git" "$FIX/withorigin"
cd "$FIX/withorigin" && git_q branch other

# corpus: repo whose origin URL is axiom-corpus; on main
mkdir -p "$FIX/corpus" && cd "$FIX/corpus" && git_q init -b main && git_q commit --allow-empty -m init \
  && git_q remote add origin https://github.com/TheAxiomFoundation/axiom-corpus.git

run_bash() { # cwd command
  jq -cn --arg cwd "$1" --arg cmd "$2" \
    '{tool_name:"Bash", cwd:$cwd, tool_input:{command:$cmd}}' | bash "$HOOK"
}
run_edit() { # file_path new_string
  jq -cn --arg fp "$1" --arg ns "$2" \
    '{tool_name:"Edit", cwd:"/tmp", tool_input:{file_path:$fp, old_string:"x", new_string:$ns}}' | bash "$HOOK"
}

assert() { # desc expected(block:<rule>|allow) actual_output
  local desc="$1" expected="$2" out="$3"
  if [ "$expected" = "allow" ]; then
    if [ -z "$out" ]; then PASS=$((PASS+1)); echo "PASS  $desc"
    else FAIL=$((FAIL+1)); echo "FAIL  $desc — expected allow, got: $out"; fi
  else
    local rule="${expected#block:}"
    if printf '%s' "$out" | grep -q '"decision":"block"' && printf '%s' "$out" | grep -q "\[$rule\]"; then
      PASS=$((PASS+1)); echo "PASS  $desc"
    else FAIL=$((FAIL+1)); echo "FAIL  $desc — expected block:$rule, got: ${out:-<empty>}"; fi
  fi
}

# --- tg-getupdates ---
assert "getUpdates curl blocked"        "block:tg-getupdates" "$(run_bash "$FIX/plain" 'curl -s https://api.telegram.org/bot123/getUpdates')"
assert "getUpdates via var URL blocked" "block:tg-getupdates" "$(run_bash "$FIX/plain" 'curl -s "$TG_API/getUpdates?offset=1"')"
assert "python get_updates blocked"     "block:tg-getupdates" "$(run_bash "$FIX/plain" 'python -c "bot.get_updates(timeout=30)"')"
assert "sendMessage allowed"            "allow"               "$(run_bash "$FIX/plain" 'curl -s https://api.telegram.org/bot123/sendMessage -d chat_id=1 -d text=hi')"
assert "prose mention in commit allowed" "allow"              "$(run_bash "$FIX/plain" 'git commit -m "docs: NEVER call Telegram getUpdates from agents"')"

# --- keychain-dump ---
assert "dump-keychain -d bare blocked"  "block:keychain-dump" "$(run_bash "$FIX/plain" 'security dump-keychain -d')"
assert "dump-keychain -d login blocked" "block:keychain-dump" "$(run_bash "$FIX/plain" 'security dump-keychain -d login.keychain-db')"
assert "dump-keychain -d custom allowed" "allow"              "$(run_bash "$FIX/plain" 'security dump-keychain -d /tmp/scratch.keychain')"
assert "find-generic-password allowed"  "allow"               "$(run_bash "$FIX/plain" 'security find-generic-password -s claude-env -w')"

# --- trust-root ---
assert "gh variable set trust root blocked"    "block:trust-root" "$(run_bash "$FIX/plain" 'gh variable set AXIOM_CORPUS_RELEASE_PUBLIC_KEY --org TheAxiomFoundation --body abc')"
assert "gh variable delete trust root blocked" "block:trust-root" "$(run_bash "$FIX/plain" 'gh variable delete AXIOM_ENCODE_APPLY_SIGNING_PUBLIC_KEY --org TheAxiomFoundation')"
assert "gh api PATCH trust root blocked"       "block:trust-root" "$(run_bash "$FIX/plain" 'gh api orgs/TheAxiomFoundation/actions/variables/AXIOM_CORPUS_RELEASE_PUBLIC_KEY -X PATCH -f value=new')"
assert "reading trust root allowed"            "allow"            "$(run_bash "$FIX/plain" 'gh variable list --org TheAxiomFoundation | grep AXIOM_CORPUS_RELEASE_PUBLIC_KEY')"

# --- corpus-squash ---
assert "squash in corpus cwd blocked"      "block:corpus-squash" "$(run_bash "$FIX/corpus" 'gh pr merge 42 --squash')"
assert "-s flag in corpus cwd blocked"     "block:corpus-squash" "$(run_bash "$FIX/corpus" 'gh pr merge 42 -s --delete-branch')"
assert "merge-commit in corpus allowed"    "allow"               "$(run_bash "$FIX/corpus" 'gh pr merge 42 --merge')"
assert "squash via -R rulespec blocked"    "block:corpus-squash" "$(run_bash "$FIX/plain" 'gh pr merge 7 --squash -R TheAxiomFoundation/rulespec-us')"
assert "squash in plain repo allowed"      "allow"               "$(run_bash "$FIX/plain" 'gh pr merge 42 --squash')"

# --- corpus-push ---
assert "push origin main in corpus blocked"   "block:corpus-push" "$(run_bash "$FIX/corpus" 'git push origin main')"
assert "push refspec :main in corpus blocked" "block:corpus-push" "$(run_bash "$FIX/corpus" 'git push origin feature:main')"
assert "bare push on main in corpus blocked"  "block:corpus-push" "$(run_bash "$FIX/corpus" 'git push')"
assert "push branch in corpus allowed"        "allow"             "$(run_bash "$FIX/corpus" 'git push origin my-branch')"
assert "push -u flag branch in corpus allowed" "allow"            "$(run_bash "$FIX/corpus" 'git push -u origin fix/thing')"
assert "push main in plain repo allowed"      "allow"             "$(run_bash "$FIX/plain" 'git push origin main')"

# --- stash-shared ---
assert "stash pop in shared repo blocked"  "block:stash-shared" "$(run_bash "$FIX/shared" 'git stash pop')"
assert "stash push in shared wt blocked"   "block:stash-shared" "$(run_bash "$FIX/shared-wt2" 'git stash push -m wip')"
assert "stash list in shared allowed"      "allow"              "$(run_bash "$FIX/shared" 'git stash list')"
assert "stash in single-worktree allowed"  "allow"              "$(run_bash "$FIX/plain" 'git stash')"

# --- local-main ---
assert "checkout -b from local main blocked"   "block:local-main" "$(run_bash "$FIX/withorigin" 'git checkout -b feat main')"
assert "switch -c from local main blocked"     "block:local-main" "$(run_bash "$FIX/withorigin" 'git switch -c feat main')"
assert "checkout -b from origin/main allowed"  "allow"            "$(run_bash "$FIX/withorigin" 'git fetch origin && git checkout -b feat origin/main')"
assert "bare -b while on main blocked"         "block:local-main" "$(run_bash "$FIX/withorigin" 'git checkout -b feat')"
assert "explicit main without origin allowed"  "allow"            "$(run_bash "$FIX/plain" 'git checkout -b feat main')"

# bare -b while NOT on main: switch fixture to branch "other"
cd "$FIX/withorigin" && git_q checkout other
assert "bare -b while on other branch allowed" "allow"            "$(run_bash "$FIX/withorigin" 'git checkout -b feat2')"
cd "$FIX/withorigin" && git_q checkout main

# --- hf-dest (Edit branch) ---
assert "uk-data upload edit blocked"   "block:hf-dest" "$(run_edit "$HOME/PolicyEngine/policyengine-uk-data/upload.py" 'api.upload_file(repo_id="policyengine/other-repo")')"
assert "uk-data benign edit allowed"   "allow"         "$(run_edit "$HOME/PolicyEngine/policyengine-uk-data/README.md" 'documentation tweak')"
assert "repo_id outside uk-data allowed" "allow"       "$(run_edit "$HOME/other/upload.py" 'repo_id="x/y"')"

# --- innocent traffic ---
assert "ls allowed"            "allow" "$(run_bash "$FIX/plain" 'ls -la')"
assert "git status allowed"    "allow" "$(run_bash "$FIX/plain" 'git status')"

echo ""
echo "=================================="
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ]
