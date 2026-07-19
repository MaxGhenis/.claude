---
description: Gmail API and IMAP access patterns for sending, drafting, and searching email across Max's accounts
---

# Gmail access

Use `gog` CLI for all email operations. IMAP is a fallback for the hivesight.ai account only.

## Sending email (gog CLI)

**CRITICAL: Always use `--body-html`, NEVER `--body` with HTML tags.** Using `--body` with HTML sends raw `<p>` tags as visible text. This actually happened — sent an email to Code for America with raw HTML tags visible.

**Always write HTML to a temp file for anything longer than one sentence:**

```bash
# Write body to temp file, then send
cat > /tmp/email-body.html << 'EMAILEOF'
<div style="font-family:sans-serif;font-size:14px;line-height:1.5;">
<p>Hi Name,</p>
<p>Your message here.</p>
<p>Best,<br>Max</p>
</div>
EMAILEOF

/opt/homebrew/bin/gog gmail send \
  --to "recipient@example.com" \
  --subject "Subject line" \
  --body-html "$(cat /tmp/email-body.html)" \
  --account work
```

### Reply to a thread

```bash
/opt/homebrew/bin/gog gmail send \
  --to "recipient@example.com" \
  --subject "Re: Original subject" \
  --body-html "$(cat /tmp/email-body.html)" \
  --reply-to-message-id "GMAIL_MESSAGE_ID" \
  --account work
```

### Other flags

```
--cc "cc@example.com"         # CC recipients
--bcc "bcc@example.com"       # BCC recipients
--attach /path/to/file        # Attachments (repeatable)
--account work                # work = max@policyengine.org
--account personal            # personal = mghenis@gmail.com
```

## Reading/searching email (gog CLI)

```bash
# Search
/opt/homebrew/bin/gog gmail search "search query" --account work --max 20

# Read a message
/opt/homebrew/bin/gog gmail read MESSAGE_ID --account work

# Read full message (no truncation)
/opt/homebrew/bin/gog gmail read MESSAGE_ID --account work --full
```

## IMAP (hivesight.ai only)

Use IMAP only for the hivesight.ai account which has no API token. App password in macOS Keychain as `GMAIL_HIVESIGHT_APP_PASSWORD` (loaded by `load-secrets.sh`).

```python
import imaplib, email, os

def search_email(query, account="hivesight"):
    accounts = {
        "hivesight": ("max@hivesight.ai", os.environ["GMAIL_HIVESIGHT_APP_PASSWORD"]),
    }
    user, password = accounts[account]
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(user, password)
    mail.select("inbox")
    status, messages = mail.search(None, f'X-GM-RAW "{query}"')
    results = []
    for num in messages[0].split()[-10:]:
        status, data = mail.fetch(num, "(RFC822)")
        msg = email.message_from_bytes(data[0][1])
        results.append({"from": msg["From"], "subject": msg["Subject"], "date": msg["Date"]})
    mail.logout()
    return results
```
