#!/bin/bash
# Loads secrets from macOS Keychain into environment variables.
# Sourced by .zshrc on shell startup.
#
# Secrets are stored in the login keychain with service="claude-env".
# Use manage-secret.sh to add/update/delete/list secrets.

SERVICE="claude-env"

# Get all account names stored under our service
_secret_names=$(security dump-keychain 2>/dev/null \
  | awk -F'"' '/svce.*claude-env/{found=1} found && /acct/{print $4; found=0}')

for name in $_secret_names; do
  value=$(security find-generic-password -s "$SERVICE" -a "$name" -w 2>/dev/null) || continue
  export "$name"="$value"
done

unset _secret_names SERVICE
