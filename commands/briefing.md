---
description: Daily briefing and monthly task reminders
---

# Daily briefing

Gets today's calendar, unread emails, and monthly task reminders (first week of month).

## Calendar

```bash
/opt/homebrew/bin/gog calendar events --today --account max@policyengine.org
```

## Email summary

```bash
# Unread and important
/opt/homebrew/bin/gog gmail search "is:unread" --max 5 --account max@policyengine.org
```

## Monthly tasks (first week only)

Check current date and run only if it's the first week of the month (1-7):

```bash
# Get day of month
DAY=$(date +%d | sed 's/^0//')

if [ "$DAY" -le 7 ]; then
  echo "🔔 MONTHLY TASK: Have you filed this month's Anthropic expenses on OpenCollective?"
  echo "   Use: /expense command to search emails, download receipts, and submit"
  echo "   Status: Check /Users/maxghenis/opencollective-py for recent submissions"
fi
```

### Anthropic expense workflow

If filing is needed:
1. Run `/expense` command (or shorthand: use expense.md)
2. Search for invoices from anthropic.com, api.anthropic.com, credits, billing
3. Download PDF/PNG receipts to ~/Downloads
4. Submit via OpenCollective policyengine collective
5. Tag with: `["anthropic", "api-credits"]` or `["anthropic", "subscriptions"]`
6. Set incurred_at to charge date (not filing date)

See ~/.claude/commands/expense.md for full CLI and MCP options.
