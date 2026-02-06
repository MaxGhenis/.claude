---
description: Prepare for an upcoming meeting - gather context, emails, PRs, and notes
args: "<meeting name or attendee>"
---

# Meeting Prep

Gather all relevant context for an upcoming meeting.

## 1. Find the Meeting

Search calendar for the meeting:
```bash
/opt/homebrew/bin/gog calendar events --from today --account max@policyengine.org | grep -i "$ARGUMENTS"
```

## 2. Search Related Emails

Find recent email threads with the person/organization:
```bash
/opt/homebrew/bin/gog gmail search "from:$ARGUMENTS OR to:$ARGUMENTS newer_than:30d" --max 10 --account max@policyengine.org
```

## 3. Check Related PRs/Issues

If it's a team member, check their recent PRs:
```bash
gh pr list --search "is:open author:$ARGUMENTS" --limit 5 --repo PolicyEngine/policyengine-us
gh issue list --search "mentions:$ARGUMENTS" --limit 5 --repo PolicyEngine/policyengine-us
```

## 4. Previous Meeting Notes

Check Granola for previous meetings with this person:
- Use `mcp__granola__search_meetings` with participant filter

## 5. Compile Prep Document

```
## Meeting Prep: [Meeting Name]

### Meeting Details
- Time: [from calendar]
- Attendees: [list]

### Recent Email Threads
- [summary of relevant emails]

### Open Items
- [any PRs, issues, or action items involving this person]

### Previous Meeting Notes
- [key points from last meeting]

### Suggested Talking Points
1. [based on context gathered]
2.
3.
```
