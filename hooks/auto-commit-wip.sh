#!/bin/bash
# PreCompact hook: Auto-commit WIP before context compression.
# Context compression often precedes crashes/context exhaustion,
# so this ensures agent work is saved to git before it's lost.

# Only run in git repos
git rev-parse --is-inside-work-tree &>/dev/null || exit 0

# Check for uncommitted changes
changes=$(git status --porcelain 2>/dev/null)
[ -z "$changes" ] && exit 0

n_changed=$(echo "$changes" | wc -l | tr -d ' ')
branch=$(git branch --show-current 2>/dev/null || echo "detached")
repo=$(basename "$(git rev-parse --show-toplevel)")

# Auto-commit everything (prefer --fixup=HEAD for easier squashing via rebase --autosquash)
git add -A
git commit --fixup=HEAD -a --no-verify 2>/dev/null || git commit -m "WIP: auto-save before context compact ($n_changed files on $branch)" -a --no-verify 2>/dev/null

echo "Auto-committed $n_changed file(s) in $repo on branch $branch before context compact."
