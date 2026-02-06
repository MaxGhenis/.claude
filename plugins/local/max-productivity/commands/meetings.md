---
description: Show today's or upcoming meetings with details
args: "[today|tomorrow|week]"
---

# Meetings Overview

Show calendar events. Default is today, but can show tomorrow or the week.

## Today's Meetings (default)

```bash
/opt/homebrew/bin/gog calendar events --today --account max@policyengine.org
```

## Tomorrow

If $ARGUMENTS is "tomorrow":
```bash
/opt/homebrew/bin/gog calendar events --tomorrow --account max@policyengine.org
```

## This Week

If $ARGUMENTS is "week":
```bash
/opt/homebrew/bin/gog calendar events --from today --to 2026-02-01 --account max@policyengine.org
```

## Meeting Prep

For each meeting, consider:
1. Who's attending? Any prep needed?
2. Any related emails to review?
3. Any PRs or issues to discuss?

## Granola Notes

If there are recent meetings, check Granola for notes:
- Use `mcp__granola__list_meetings` for recent meeting history
- Use `mcp__granola__get_meeting_notes` for specific meeting notes

## Output Format

```
## Meetings: [Today/Tomorrow/This Week]

### [Time] - [Meeting Title]
- Duration: X min
- Attendees: (if available)
- Prep: (any suggested prep)

### [Time] - [Meeting Title]
...

**Total: X meetings, Y hours**
```
