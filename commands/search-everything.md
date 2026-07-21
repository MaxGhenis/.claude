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

WhatsApp imports live in OpenMessage too — the step 2 search already covers them. (The standalone whatsapp MCP server is no longer registered.)

### 4. Gmail (all 4 accounts)

Use gog for the API-connected accounts:
```bash
for a in max@policyengine.org mghenis@gmail.com max@maxghenis.com max@axiom-foundation.org; do
  /opt/homebrew/bin/gog gmail search "$ARGUMENTS" --max 5 --account "$a"
done
```

IMAP is the fallback for hivesight.ai only (app password via keychain — see the `/gmail` skill).

### 5. Granola meeting notes

Granola access is disabled by default because the CLI can trigger repeated macOS keychain prompts. Ask Max before using Granola.

### 6. Slack

Search via the `slack` CLI (no Slack MCP is registered): `slack search "$ARGUMENTS"` for PolicyEngine, `slack -w axiom search "$ARGUMENTS"` for Axiom.

### 7. Browser (last resort)

Use Chrome automation to search the web if the information isn't found locally.

## Tips

- Start broad, narrow down. If "medicaid ID" doesn't work, try "medicaid", "member ID", "insurance card"
- For people: search by name, email, phone number
- For documents: search by filename, subject line, key phrases
- Report which sources were checked and what was found at each step
