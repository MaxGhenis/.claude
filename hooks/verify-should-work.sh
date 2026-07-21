#!/bin/bash
# Stop hook: block if assistant says "should work" without verifying
# Reads JSON from stdin with last_assistant_message field

RESPONSE=$(jq -r '.last_assistant_message // ""')
PATTERN='(should (work|be working|be fixed|be good|render|load|display)|ought to work|probably (works|fixed)|likely (works|fixed))'

if printf '%s' "$RESPONSE" | grep -qiE "$PATTERN"; then
  printf '%s\n' '{"decision": "block", "reason": "You said something \"should work\" — verify it actually does before telling the user. Open the URL, run the test, or check the output yourself."}'
else
  printf '%s\n' '{"decision": "approve"}'
fi
