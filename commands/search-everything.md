---
description: Cross-platform search across local files, SMS/texts (OpenMessage), WhatsApp, Gmail, Granola meetings, and browser. Use when looking for a specific piece of information that could be anywhere.
args: "<search query>"
---

# Cross-platform search

Search across all available sources to find information. Work through sources in order of speed, stopping when found.

## Search order

### 1. Local files (fastest)

Search home directory and common locations:
```bash
# Search common document locations
grep -r "$ARGUMENTS" ~/Documents/ ~/Desktop/ ~/Downloads/ --include="*.txt" --include="*.md" --include="*.pdf" -l 2>/dev/null | head -10
```

Also try Glob/Grep tools for structured search across files.

### 2. SMS/texts (OpenMessage)

Search SMS/RCS/iMessage via OpenMessage MCP (load with `ToolSearch query: "+openmessage"` first):
```
mcp__openmessage__search_messages(query="$ARGUMENTS")
```
Or HTTP fallback: `curl -s 'http://localhost:7007/api/search?q=$ARGUMENTS'`

### 3. WhatsApp messages

Search WhatsApp via MCP:
```
mcp__whatsapp__list_messages(query="$ARGUMENTS", limit=10)
```

### 4. Gmail (all 3 accounts)

Search all accounts via IMAP using the `/gmail` skill pattern. Use `X-GM-RAW` for Gmail search syntax:

```python
# Search all three accounts
for account in ["policyengine", "personal", "hivesight"]:
    results = search_email("$ARGUMENTS", account=account)
```

Or use gog for quick search:
```bash
/opt/homebrew/bin/gog gmail search "$ARGUMENTS" --max 5 --account max@policyengine.org
/opt/homebrew/bin/gog gmail search "$ARGUMENTS" --max 5 --account mghenis@gmail.com
```

### 5. Granola meeting notes

Search meeting transcripts and notes:
```
mcp__granola__search_meetings(query="$ARGUMENTS", from_date="90d")
```

### 6. Slack

Search Slack workspace messages if relevant:
```
mcp__slack__slack_get_channel_history (check relevant channels)
```

### 7. Browser (last resort)

Use Chrome automation to search the web if the information isn't found locally.

## Tips

- Start broad, narrow down. If "medicaid ID" doesn't work, try "medicaid", "member ID", "insurance card"
- For people: search by name, email, phone number
- For documents: search by filename, subject line, key phrases
- Report which sources were checked and what was found at each step
