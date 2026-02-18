---
description: Check email inbox - unread messages, filter by sender or topic
args: "[query]"
---

# Email Inbox Check

Check Max's email inbox. If a query argument is provided, search for it. Otherwise show unread/important.

## Without Query - Show Unread Important

```bash
/opt/homebrew/bin/gog gmail search "is:unread is:important" --max 15 --account max@policyengine.org
```

## With Query - Search

If the user provided a search term, use it:
```bash
/opt/homebrew/bin/gog gmail search "$ARGUMENTS" --max 15 --account max@policyengine.org
```

## Common Searches

Help the user with these patterns:
- From someone: `from:person@email.com`
- Subject: `subject:keyword`
- Has attachment: `has:attachment`
- Recent: `newer_than:7d`
- Unread: `is:unread`
- Starred: `is:starred`

## Multiple Accounts

If user asks about personal email:
```bash
/opt/homebrew/bin/gog gmail search "$ARGUMENTS" --max 15 --account mghenis@gmail.com
```

## Output

Present emails concisely:
```
## Inbox: [query or "Unread Important"]

| Date | From | Subject |
|------|------|---------|
| ... | ... | ... |

[X] emails found. Reply with email ID to read full content.
```
