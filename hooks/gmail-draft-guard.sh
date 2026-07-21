#!/bin/bash
# gmail-draft-guard: fires after Bash commands that read Gmail via gog.
# Injects a reminder that thread messages labeled DRAFT are NOT sent mail.
# Agents (incl. Claude) have repeatedly reported drafts as sent, causing Max
# to miss follow-ups (recurred 2026-07-18, OCPP/Tyler thread). A draft created
# with `gog gmail drafts create --reply-to-message-id` attaches to the thread
# and renders with a plausible From/Date, indistinguishable from a sent reply
# in gog's human-readable output.
cmd=$(jq -r '.tool_input.command // ""' 2>/dev/null)
if printf '%s' "$cmd" | grep -qE 'gog +(gmail|mail|email) +(read|search|find|query|ls|list|thread|messages|msgs|msg)'; then
  cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"DRAFTS ARE NOT SENT MAIL: Gmail threads include DRAFT messages that render like real sent replies (plausible From/Date). Before stating that any message was sent, that you replied, or that a thread is 'awaiting response', verify one of: (a) the message's labelIds lack DRAFT (check with gog gmail read <thread-id> -j), or (b) the message appears under gog gmail search 'in:sent to:<recipient>'. Creating a draft with drafts create attaches it to the thread and it LOOKS sent. Never claim an email was sent from thread presence, memory files, or a draft-creation timestamp."}}
EOF
fi
exit 0
