#!/bin/bash
# Loads Claude env-style secrets into environment variables.
# Sourced by .zshrc on shell startup.
#
# Secrets are stored in the dedicated agent keychain. Use either:
#   agent-secret set VAR_NAME
#   ~/.claude/manage-secret.sh set VAR_NAME value

NAMES_FILE="${HOME}/.claude/secret-names.txt"
EXTRA_SECRET_NAMES="
OPENAI_API_KEY
ANTHROPIC_API_KEY
GOOGLE_API_KEY
GEMINI_API_KEY
XAI_API_KEY
"

while IFS= read -r name; do
  # The keychain also holds non-env entries (account-lane tokens keyed
  # by email, agent/* CLI secrets); their names can never be env vars,
  # so skip them before fetching. Negated-class glob, NOT a regex:
  # [A-Za-z_][A-Za-z0-9_]* silently matched anything past two chars.
  case "$name" in
    ''|[0-9]*|*[!A-Za-z0-9_]*) continue ;;
  esac

  # In zsh a failed export (invalid or readonly name) is FATAL to the
  # whole sourced file (rc 126) and no `||` can catch it — probe in a
  # throwaway subshell, the only place the abort is containable.
  ( export "${name}=" ) 2>/dev/null || {
    printf 'load-secrets: skipping unexportable name: %s\n' "$name" >&2
    continue
  }

  # No account arg: entries are stored under varying accounts
  # (maxghenis, policyengine-auto, axiom-foundation, ...) and service
  # names are unique, so match on service alone.
  value=$(agent-secret get "$name" 2>/dev/null) ||
    value=$(security find-generic-password -s "claude-env" -a "$name" -w 2>/dev/null) ||
    continue

  export "${name}=${value}"
done < <(
  {
    printf '%s\n' "$EXTRA_SECRET_NAMES"
    [ -f "$NAMES_FILE" ] && cat "$NAMES_FILE"
    agent-secret list 2>/dev/null | awk -F '\t' '{print $1}'
  } | awk 'NF && !seen[$0]++'
)

unset EXTRA_SECRET_NAMES NAMES_FILE value name
