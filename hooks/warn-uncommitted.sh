#!/bin/bash
# Stop hook: Warn if there are uncommitted changes in the current git repo.
# Prevents losing multi-agent work when sessions crash.

# Only run in git repos
git rev-parse --is-inside-work-tree &>/dev/null || exit 0

# Check for uncommitted changes (staged + unstaged + untracked in repo dirs)
changes=$(git status --porcelain 2>/dev/null | grep -v '^\?\? \.' | head -20)
[ -z "$changes" ] && exit 0

# Count changed files
n_changed=$(echo "$changes" | wc -l | tr -d ' ')

echo "WARNING: $n_changed uncommitted file(s) in $(basename $(git rev-parse --show-toplevel))."
echo "Consider committing and pushing to avoid losing work if the session crashes."
