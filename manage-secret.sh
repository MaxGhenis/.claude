#!/bin/bash
# Manage secrets in macOS Keychain (service="claude-env").
#
# Usage:
#   manage-secret.sh set   VAR_NAME value    # Add or update a secret
#   manage-secret.sh get   VAR_NAME          # Print a secret's value
#   manage-secret.sh del   VAR_NAME          # Delete a secret
#   manage-secret.sh list                    # List all secret names

set -euo pipefail

SERVICE="claude-env"

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
    security delete-generic-password -s "$SERVICE" -a "$name" 2>/dev/null || true
    security add-generic-password -s "$SERVICE" -a "$name" -w "$value" -U
    echo "Stored: $name"
    ;;
  get)
    name="${1:-}"
    [ -z "$name" ] && { echo "Error: get requires VAR_NAME"; usage; }
    security find-generic-password -s "$SERVICE" -a "$name" -w 2>/dev/null || {
      echo "Not found: $name" >&2; exit 1
    }
    ;;
  del)
    name="${1:-}"
    [ -z "$name" ] && { echo "Error: del requires VAR_NAME"; usage; }
    security delete-generic-password -s "$SERVICE" -a "$name" 2>/dev/null && echo "Deleted: $name" || {
      echo "Not found: $name" >&2; exit 1
    }
    ;;
  list)
    security dump-keychain 2>/dev/null \
      | awk -F'"' '/svce.*claude-env/{found=1} found && /acct/{print $4; found=0}' \
      | sort
    ;;
  *)
    usage
    ;;
esac
