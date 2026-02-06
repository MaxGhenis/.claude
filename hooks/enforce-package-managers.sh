#!/bin/bash
# Hook to enforce bun over npm and uv over pip

# Read the tool input from stdin
input=$(cat)

# Extract the command from the JSON
command=$(echo "$input" | jq -r '.tool_input.command // empty')

# Check for npm usage
if echo "$command" | grep -qE '\bnpm\s+(install|i|add|remove|rm|uninstall|run|start|test|build|ci|update|upgrade|init|create)\b'; then
  echo '{"decision": "block", "reason": "Use bun instead of npm. Replace: npm install → bun install, npm run → bun run, npm add → bun add"}'
  exit 0
fi

# Check for npx usage
if echo "$command" | grep -qE '\bnpx\s+'; then
  echo '{"decision": "block", "reason": "Use bunx instead of npx. Replace: npx <package> → bunx <package>"}'
  exit 0
fi

# Check for pip usage (but allow uv pip)
if echo "$command" | grep -qE '(^|[^v]\s+)pip3?\s+(install|uninstall|download)\b'; then
  echo '{"decision": "block", "reason": "Use uv instead of pip. Replace: pip install → uv pip install or uv add"}'
  exit 0
fi

# Check for pipx usage
if echo "$command" | grep -qE '\bpipx\s+(install|uninstall|upgrade|inject)\b'; then
  echo '{"decision": "block", "reason": "Use uv tool instead of pipx. Replace: pipx install → uv tool install, pipx uninstall → uv tool uninstall"}'
  exit 0
fi

# Check for yarn usage
if echo "$command" | grep -qE '\byarn\s+(add|install|remove)\b'; then
  echo '{"decision": "block", "reason": "Use bun instead of yarn. Replace: yarn add → bun add, yarn install → bun install"}'
  exit 0
fi

# Allow the command
echo '{"decision": "approve"}'
