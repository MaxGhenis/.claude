#!/bin/bash
# Backward-compatible wrapper for Claude env-style secrets.
# New storage is the dedicated agent keychain managed by `agent-secret`.
#
# Usage:
#   manage-secret.sh set   VAR_NAME value    # Add or update a secret
#   manage-secret.sh get   VAR_NAME          # Print a secret's value
#   manage-secret.sh del   VAR_NAME          # Delete a secret
#   manage-secret.sh list                    # List all secret names

set -euo pipefail

NAMES_FILE="${HOME}/.claude/secret-names.txt"
ACCOUNT="$(id -un)"
OLD_SERVICE="claude-env"

ensure_names_file() {
  mkdir -p "$(dirname "$NAMES_FILE")"
  touch "$NAMES_FILE"
}

add_name() {
  local name="$1"
  ensure_names_file
  if ! grep -Fxq "$name" "$NAMES_FILE"; then
    printf '%s\n' "$name" >> "$NAMES_FILE"
  fi
}

remove_name() {
  local name="$1"
  if [ -f "$NAMES_FILE" ]; then
    grep -Fxv "$name" "$NAMES_FILE" > "${NAMES_FILE}.tmp" || true
    mv "${NAMES_FILE}.tmp" "$NAMES_FILE"
  fi
}

usage() {
  echo "Usage:"
  echo "  $0 set  VAR_NAME value   # Add or update"
  echo "  $0 get  VAR_NAME         # Print value"
  echo "  $0 del  VAR_NAME         # Delete"
  echo "  $0 list                  # List all names"
  exit 1
}

cmd="${1:-}"
shift || true

case "$cmd" in
  set)
    name="${1:-}"
    value="${2:-}"
    [ -z "$name" ] || [ -z "$value" ] && { echo "Error: set requires VAR_NAME and value"; usage; }
    printf '%s\n' "$value" | agent-secret set "$name" "$ACCOUNT" >/dev/null
    add_name "$name"
    echo "Stored: $name"
    ;;
  get)
    name="${1:-}"
    [ -z "$name" ] && { echo "Error: get requires VAR_NAME"; usage; }
    agent-secret get "$name" "$ACCOUNT" 2>/dev/null ||
      security find-generic-password -s "$OLD_SERVICE" -a "$name" -w 2>/dev/null || {
        echo "Not found: $name" >&2
        exit 1
      }
    ;;
  del)
    name="${1:-}"
    [ -z "$name" ] && { echo "Error: del requires VAR_NAME"; usage; }
    deleted=0
    if agent-secret delete "$name" "$ACCOUNT" >/dev/null 2>&1; then
      deleted=1
    fi
    security delete-generic-password -s "$OLD_SERVICE" -a "$name" 2>/dev/null || true
    if [ "$deleted" -eq 1 ]; then
      remove_name "$name"
      echo "Deleted: $name"
    else
      echo "Not found: $name" >&2
      exit 1
    fi
    ;;
  list)
    {
      [ -f "$NAMES_FILE" ] && cat "$NAMES_FILE"
      agent-secret list 2>/dev/null | awk -F '\t' '{print $1}'
    } | awk 'NF && !seen[$0]++' | sort
    ;;
  *)
    usage
    ;;
esac
