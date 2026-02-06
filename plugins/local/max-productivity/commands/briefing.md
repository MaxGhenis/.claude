---
description: Morning briefing - calendar, urgent emails, PRs needing review, and action items
---

# Daily Briefing

Generate a comprehensive morning briefing for Max. Gather and present:

## 1. Today's Calendar

Use gog to get today's events:
```bash
/opt/homebrew/bin/gog calendar events --today --account max@policyengine.org
```

## 2. Urgent/Unread Emails

Check for important unread emails (use gog, not IMAP for speed):
```bash
/opt/homebrew/bin/gog gmail search "is:unread is:important" --max 10 --account max@policyengine.org
```

## 3. GitHub PRs Needing Review

Check PRs across PolicyEngine and CosilicoAI repos:
```bash
for repo in PolicyEngine/policyengine-us PolicyEngine/policyengine-uk PolicyEngine/policyengine-app-v2 PolicyEngine/policyengine-api CosilicoAI/cosilico-api CosilicoAI/rules-us; do
  echo "--- $repo ---"
  gh pr list --search "is:open review-requested:@me" --repo "$repo" --limit 5 2>/dev/null
done
```

Also check for any failing CI on recent PRs:
```bash
for repo in PolicyEngine/policyengine-us PolicyEngine/policyengine-app-v2 CosilicoAI/cosilico-api; do
  echo "--- $repo ---"
  gh pr list --search "is:open author:@me" --repo "$repo" --limit 5 --json number,title,statusCheckRollup 2>/dev/null
done
```

## 4. Recent Meeting Notes (if Granola available)

Check recent meetings for any action items from yesterday:
```bash
# Use Granola MCP if available
```

## Output Format

Present as a concise briefing:

```
## Today: [Day, Date]

### Calendar (X events)
- HH:MM - Event Name
- ...

### Urgent Emails (X unread)
- From: Subject (brief)
- ...

### PRs Needing Review (X total)
- repo#123: Title
- ...

### Action Items
- [from meetings/emails if any]
```

Keep it scannable - Max should be able to read this in 30 seconds.
