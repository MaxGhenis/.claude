#!/bin/bash
# PreToolUse hook for Bash commands.
# Blocks the two highest-risk ways agents bypass PR review:
# committing on protected branches and pushing directly to protected branches.

input=$(cat)
command=$(echo "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$command" ] && echo '{"decision":"approve"}' && exit 0

if echo "$command" | grep -qE '\bALLOW_DIRECT_PROTECTED_BRANCH=1\b'; then
  echo '{"decision":"approve"}'
  exit 0
fi

protected_regex='(main|master|develop|trunk|production|prod|gh-pages)'

current_branch=""
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  current_branch=$(git branch --show-current 2>/dev/null || true)
fi

on_protected_branch=false
if echo "$current_branch" | grep -Eq "^${protected_regex}$"; then
  on_protected_branch=true
fi

if echo "$command" | grep -qE '(^|[;&|[:space:]])git[[:space:]]+commit([[:space:]]|$)'; then
  if [ "$on_protected_branch" = true ]; then
    echo '{"decision":"block","reason":"Do not commit directly on protected branches. Create a branch from origin/main, commit there, and open a PR. Override only for an explicit emergency with ALLOW_DIRECT_PROTECTED_BRANCH=1."}'
    exit 0
  fi
fi

if echo "$command" | grep -qE '(^|[;&|[:space:]])git[[:space:]]+push([[:space:]]|$)'; then
  if echo "$command" | grep -Eq "(:|refs/heads/|[[:space:]])${protected_regex}([[:space:]]|$)"; then
    echo '{"decision":"block","reason":"Direct pushes to protected branches are blocked. Push a feature branch and open/update a PR. Override only for an explicit emergency with ALLOW_DIRECT_PROTECTED_BRANCH=1."}'
    exit 0
  fi

  if [ "$on_protected_branch" = true ] && ! echo "$command" | grep -Eq 'HEAD:|[[:space:]][^[:space:]]+:[^[:space:]]+|--set-upstream|-u'; then
    echo '{"decision":"block","reason":"Bare git push from a protected branch would push directly to that branch. Create/push a feature branch and open a PR. Override only for an explicit emergency with ALLOW_DIRECT_PROTECTED_BRANCH=1."}'
    exit 0
  fi
fi

echo '{"decision":"approve"}'
