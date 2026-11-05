#!/bin/bash
# Hook to enforce bun over npm and uv over pip

# Read the tool input from stdin
input=$(cat)

# Extract the command from the JSON
command=$(echo "$input" | jq -r '.tool_input.command // empty')

# Block GitNexus setup because upstream setup may reinstall unsafe PostToolUse hooks.
if echo "$command" | grep -qE '(^|[;&|()[:space:]])((bunx|npx)([[:space:]]+-y)?[[:space:]]+)?gitnexus(@latest)?[[:space:]]+setup\b'; then
  echo '{"decision": "block", "reason": "Do not run gitnexus setup here; it may reinstall unsafe GitNexus PostToolUse hooks. GitNexus analyze/status are OK, and the local hook is already configured for PreToolUse only."}'
  exit 0
fi

# Block floating GitNexus runners and self-update. Each release bundles a database engine, so a
# newer build writes indexes the machine's pinned build cannot open.
if echo "$command" | grep -qE '(^|[;&|()[:space:]])(bunx|npx|pnpm[[:space:]]+(--[^[:space:]]+[[:space:]]+)*dlx|yarn[[:space:]]+dlx)([[:space:]]+-[^[:space:]]+)*[[:space:]]+gitnexus(@[^[:space:]]+)?([[:space:]]|$)' \
  || echo "$command" | grep -qE '(^|[;&|()[:space:]/])gitnexus[[:space:]]+update([[:space:]]|$)'; then
  echo '{"decision": "block", "reason": "Use the pinned GitNexus build: gitnexus on PATH, and gitnexus-index refresh <repo> to rebuild an index. A floating runner or gitnexus update moves off the pin and writes databases the pinned build cannot open. To move the pin, follow the docstring in ~/.claude/hooks/gitnexus/gitnexus-index."}'
  exit 0
fi

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

# Check for pip usage (but allow uv pip and pip inside strings/heredocs)
if echo "$command" | grep -qE '(^|&&|\|\||;)\s*pip3?\s+(install|uninstall|download)\b'; then
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
