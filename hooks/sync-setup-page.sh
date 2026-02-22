#!/bin/bash
# PostToolUse hook (Bash): After a git commit to dotfiles or .claude,
# remind Claude to update the setup page at maxghenis.com.

# Read the tool input from stdin
input=$(cat)

# Check if the command was a git commit in dotfiles or .claude
command=$(echo "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$command" ] && exit 0

# Must be a git commit (not just git add, git push, etc.)
echo "$command" | grep -q 'git commit' || exit 0

# Must be in dotfiles or .claude
if echo "$command" | grep -qE '(dotfiles|\.claude)'; then
  match=true
elif [ -f "$PWD/.git/config" ]; then
  repo=$(basename "$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null)")
  [[ "$repo" == "dotfiles" || "$repo" == ".claude" ]] && match=true
fi

[ "$match" = true ] || exit 0

echo "REMINDER: You just committed to dotfiles or .claude. Check if ~/maxghenis.com/src/pages/setup.astro needs updating to stay in sync."
