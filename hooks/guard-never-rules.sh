#!/bin/bash
# guard-never-rules.sh — deterministic gates for standing NEVER rules that
# previously lived only in memory files (advisory). Blocks the command and
# explains the correct alternative; approval-neutral otherwise (no output).
#
# Wired in settings.json: PreToolUse matcher "Bash" and "Edit|Write|MultiEdit".
# Tests: ~/.claude/tests/guard-never-rules-test.sh
#
# Rules (source memory in parens):
#   stash-shared     git stash in a repo with >1 worktree (feedback_never_stash_in_shared_worktrees)
#   trust-root       mutating AXIOM_*PUBLIC_KEY org vars (feedback_never_rotate_axiom_trust_roots)
#   corpus-squash    squash-merging PRs in axiom-corpus / rulespec-* (.github#39 rule 6)
#   corpus-push      pushing directly to axiom-corpus main (.github#39 rule 6)
#   tg-getupdates    Telegram getUpdates polling (project_chief_of_staff — OpenClaw owns it)
#   local-main       branching from local main when origin/main exists (CLAUDE.md)
#   keychain-dump    security dump-keychain -d on the login keychain (CLAUDE.md)
#   hf-dest          editing upload destinations in policyengine-uk-data (safety rules)
#
# No override token by design: a blocked command stays blocked. Genuine
# exceptions are Max running it himself in a plain terminal, or editing this
# hook in a reviewed change.

input=$(cat)

tool=$(printf '%s' "$input" | jq -r '.tool_name // empty')
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')

block() {
  jq -cn --arg r "$1" '{decision: "block", reason: $r}'
  exit 0
}

# ---------- Edit/Write branch ----------
if [ "$tool" != "Bash" ]; then
  file_path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
  case "$file_path" in
    *policyengine-uk-data*)
      new_text=$(printf '%s' "$input" | jq -r '[.tool_input.new_string // empty, .tool_input.content // empty, ((.tool_input.edits // []) | map(.new_string) | join(" "))] | join(" ")')
      if printf '%s' "$new_text" | grep -qE 'repo_id|huggingface\.co/|hf://|upload_file|upload_folder'; then
        block "[hf-dest] HF upload destinations in policyengine-uk-data are frozen (standing rule: NEVER change them). If this edit is not a destination change, restructure it to avoid touching upload/repo_id lines; if it is, Max makes that change himself."
      fi
      ;;
  esac
  exit 0
fi

# ---------- Bash branch ----------
command=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
[ -z "$command" ] && exit 0

# Cheap prefilter: bail immediately unless a rule keyword appears.
printf '%s' "$command" | grep -qE 'stash|AXIOM_|getUpdates|get_updates|dump-keychain|checkout[[:space:]]+-b|switch[[:space:]]+-c|pr[[:space:]]+merge|git[[:space:]]+push' || exit 0

# --- tg-getupdates: Telegram polling steals updates from the OpenClaw gateway ---
# Match API-call contexts only (URL path, telegram host nearby, or bot-lib call),
# not prose that merely mentions the word (commit messages, docs).
if printf '%s' "$command" | grep -qE '/getUpdates|\.get_updates\(' \
   || { printf '%s' "$command" | grep -q 'getUpdates' && printf '%s' "$command" | grep -qi 'api\.telegram'; }; then
  block "[tg-getupdates] NEVER call Telegram getUpdates — the ai.openclaw.gateway launchd job owns polling on the shared bot token; a second poller steals its updates. Chief-of-staff traffic is outbound-only (sendMessage/sendDocument are fine)."
fi

# --- keychain-dump: login-keychain dumps cause macOS prompt storms ---
if printf '%s' "$command" | grep -qE 'dump-keychain' && printf '%s' "$command" | grep -qE '(^|[[:space:]])-d([[:space:]]|$)'; then
  named=$(printf '%s' "$command" | grep -oE '[^[:space:]]+\.keychain(-db)?' | grep -v 'login' | head -1)
  if [ -z "$named" ]; then
    block "[keychain-dump] Do not run 'security dump-keychain -d' against the login keychain — it triggers a macOS prompt storm and touches unrelated credentials (CLAUDE.md). Use 'agent-secret' / 'security find-generic-password -s <item>' for specific secrets."
  fi
fi

# --- trust-root: Axiom org trust anchors are rotated only via coordinated migration ---
if printf '%s' "$command" | grep -qE 'AXIOM_[A-Z_]*PUBLIC_KEY'; then
  if printf '%s' "$command" | grep -qE 'variable[[:space:]]+(set|delete)|-X[[:space:]]+(PATCH|POST|PUT|DELETE)|--method[[:space:]]+(PATCH|POST|PUT|DELETE)|-f[[:space:]]+value='; then
    block "[trust-root] NEVER mutate AXIOM_*PUBLIC_KEY org variables — they are org-wide trust anchors; all nine encoding repos verify signed release objects against them, and rotation breaks every validate CI simultaneously (7/14 incident, feedback_never_rotate_axiom_trust_roots). Rotation is a coordinated re-sign-everything migration Max authorizes, never an in-flight swap. Reading the vars is fine."
  fi
fi

# --- corpus-squash: signed-manifest repos merge-commit, never squash ---
if printf '%s' "$command" | grep -qE 'pr[[:space:]]+merge' && printf '%s' "$command" | grep -qE '(^|[[:space:]])(--squash|-s)([[:space:]]|$)'; then
  repo_ctx=$(printf '%s' "$command" | grep -oE '(-R|--repo)[[:space:]]+[^[:space:]]+' | awk '{print $2}')
  [ -z "$repo_ctx" ] && repo_ctx=$(git -C "$cwd" remote get-url origin 2>/dev/null)
  if printf '%s' "$repo_ctx" | grep -qiE 'TheAxiomFoundation/(axiom-corpus|rulespec-)'; then
    block "[corpus-squash] NEVER squash-merge in axiom-corpus / rulespec-* — squash orphans manifest signing commits and breaks the guard's ancestor invariant repo-wide (corpus#428: 226 manifests orphaned). Use 'gh pr merge --merge' (.github#39 rule 6)."
  fi
fi

# --- corpus-push: never push corpus main directly ---
if printf '%s' "$command" | grep -qE 'git[[:space:]]+push'; then
  origin_url=$(git -C "$cwd" remote get-url origin 2>/dev/null)
  if printf '%s' "$origin_url" | grep -qiE 'TheAxiomFoundation/axiom-corpus'; then
    # tokenize the push segment: first non-flag token = remote, second = refspec
    seg=$(printf '%s' "$command" | sed -E 's/.*git[[:space:]]+push//' | sed -E 's/[;&|].*//')
    refspec="" remote_seen=""
    for tok in $seg; do
      case "$tok" in
        -*) continue ;;
        *) if [ -z "$remote_seen" ]; then remote_seen="$tok"; else refspec="$tok"; break; fi ;;
      esac
    done
    target=""
    if [ -n "$refspec" ]; then
      case "$refspec" in
        main|master|+main|+master|*:main|*:master) target=1 ;;
        HEAD) cur=$(git -C "$cwd" branch --show-current 2>/dev/null)
              { [ "$cur" = "main" ] || [ "$cur" = "master" ]; } && target=1 ;;
      esac
    else
      # bare `git push` / `git push origin`: pushes the current branch
      cur=$(git -C "$cwd" branch --show-current 2>/dev/null)
      { [ "$cur" = "main" ] || [ "$cur" = "master" ]; } && target=1
    fi
    if [ -n "$target" ]; then
      block "[corpus-push] Never push axiom-corpus main directly — releases publish only from corpus main via the gated flow, and stray commits there broke every consumer pin once already (.github#39 rule 6, axiom-corpus#320). Push a branch and open a PR."
    fi
  fi
fi

# --- stash-shared: the stash stack is repo-global across worktrees ---
if printf '%s' "$command" | grep -qE '\bgit\b[^|;&]*\bstash\b' && ! printf '%s' "$command" | grep -qE '\bstash[[:space:]]+list\b'; then
  wt_count=$(git -C "$cwd" worktree list 2>/dev/null | wc -l | tr -d ' ')
  if [ "${wt_count:-0}" -gt 1 ]; then
    block "[stash-shared] NEVER git stash in shared-worktree repos — the stash stack lives in .git and is shared by ALL worktrees; a pop can dump another session's WIP into yours (7/17 near-miss, feedback_never_stash_in_shared_worktrees). To temporarily revert an edit: Edit tool remove/re-add, or 'git show HEAD:path > file' then restore. 'git stash list' is allowed for recovery."
  fi
fi

# --- local-main: branch from origin/main, never local main ---
if printf '%s' "$command" | grep -qE '(checkout[[:space:]]+-b|switch[[:space:]]+-c)'; then
  if git -C "$cwd" show-ref --verify --quiet refs/remotes/origin/main 2>/dev/null || git -C "$cwd" show-ref --verify --quiet refs/remotes/origin/master 2>/dev/null; then
    reason="[local-main] Branch from origin/main, never local main — local main may carry unmerged work from other sessions (CLAUDE.md). Use: git fetch origin && git checkout -b <name> origin/main"
    # explicit local start point: ... -b name main
    if printf '%s' "$command" | grep -qE '(checkout[[:space:]]+-b|switch[[:space:]]+-c)[[:space:]]+[^[:space:]]+[[:space:]]+(main|master)([[:space:]]|$|;|&|\|)'; then
      block "$reason"
    fi
    # implicit start point while sitting on main
    if printf '%s' "$command" | grep -qE '(checkout[[:space:]]+-b|switch[[:space:]]+-c)[[:space:]]+[^[:space:]]+[[:space:]]*($|;|&|\|)'; then
      cur=$(git -C "$cwd" branch --show-current 2>/dev/null)
      if [ "$cur" = "main" ] || [ "$cur" = "master" ]; then
        block "$reason"
      fi
    fi
  fi
fi

exit 0
