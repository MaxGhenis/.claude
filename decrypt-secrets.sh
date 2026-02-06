#!/bin/bash
# Decrypt and source Claude Code secrets
# Usage: source ~/.claude/decrypt-secrets.sh
# Or add to .zshrc: eval "$(~/.claude/decrypt-secrets.sh)"

age -d -i ~/.config/age/key.txt ~/.claude/secrets.env.age 2>/dev/null
