#!/bin/bash
# Loads Claude env-style secrets into environment variables.
# Sourced by .zshrc on shell startup.
#
# Secrets are stored in the dedicated agent keychain. Use either:
#   agent-secret set VAR_NAME
#   ~/.claude/manage-secret.sh set VAR_NAME value

NAMES_FILE="${HOME}/.claude/secret-names.txt"
ACCOUNT="$(id -un)"
EXTRA_SECRET_NAMES="
OPENAI_API_KEY
ANTHROPIC_API_KEY
GOOGLE_API_KEY
GEMINI_API_KEY
XAI_API_KEY
"

while IFS= read -r name; do
  case "$name" in
    [A-Za-z_][A-Za-z0-9_]*) ;;
    *) continue ;;
  esac

  if value=$(agent-secret get "$name" "$ACCOUNT" 2>/dev/null); then
    export "${name}=${value}"
  elif value=$(security find-generic-password -s "claude-env" -a "$name" -w 2>/dev/null); then
    export "${name}=${value}"
  fi
done < <(
  {
    printf '%s\n' "$EXTRA_SECRET_NAMES"
    [ -f "$NAMES_FILE" ] && cat "$NAMES_FILE"
    agent-secret list 2>/dev/null | awk -F '\t' '{print $1}'
  } | awk 'NF && !seen[$0]++'
)

unset EXTRA_SECRET_NAMES NAMES_FILE ACCOUNT value name
