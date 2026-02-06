---
description: Gmail API and IMAP access patterns for sending, drafting, and searching email across Max's accounts
---

# Gmail access

Two methods are available: Gmail API (preferred) and IMAP (fallback).

## Gmail API usage

**IMPORTANT: Always send emails as HTML**, not plain text. Plain text emails render in a narrow column in Gmail.

Requires the `google-api` skill for `get_google_credentials()`.

```python
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def _text_to_html(text):
    """Convert plain text email body to simple HTML for proper Gmail rendering.

    Handles paragraphs, indented code blocks, and inline backtick code.
    """
    import re
    paragraphs = text.split("\n\n")
    html_parts = []
    for para in paragraphs:
        lines = para.split("\n")
        if all(line.startswith("    ") or line.strip() == "" for line in lines):
            code = "\n".join(line[4:] if line.startswith("    ") else line for line in lines)
            html_parts.append(
                f'<pre style="background:#f5f5f5;padding:12px;border-radius:4px;'
                f'font-family:monospace;overflow-x:auto;">{code}</pre>'
            )
        else:
            joined = "<br>".join(lines)
            joined = re.sub(
                r'`([^`]+)`',
                r'<code style="background:#f5f5f5;padding:2px 4px;border-radius:3px;font-family:monospace;">\1</code>',
                joined,
            )
            html_parts.append(f"<p>{joined}</p>")
    return (
        '<div style="font-family:sans-serif;font-size:14px;line-height:1.5;">'
        + "".join(html_parts)
        + "</div>"
    )


def create_draft(to, subject, body, cc=None, bcc=None, reply_to_message_id=None, account="work"):
    """Create a draft email in Gmail. Body is plain text, auto-converted to HTML."""
    creds = get_google_credentials(account)
    service = build("gmail", "v1", credentials=creds)

    message = MIMEMultipart()
    message["to"] = to
    message["subject"] = subject
    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc
    if reply_to_message_id:
        message["In-Reply-To"] = reply_to_message_id
        message["References"] = reply_to_message_id
    message.attach(MIMEText(_text_to_html(body), "html"))

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    return f"https://mail.google.com/mail/u/0/#drafts?compose={draft['id']}"

def send_email(to, subject, body, cc=None, bcc=None, account="work"):
    """Send an email via Gmail API. Body is plain text, auto-converted to HTML."""
    creds = get_google_credentials(account)
    service = build("gmail", "v1", credentials=creds)

    message = MIMEMultipart()
    message["to"] = to
    message["subject"] = subject
    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc
    message.attach(MIMEText(_text_to_html(body), "html"))

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()
    return sent["id"]
```

## Gmail IMAP access (fallback)

Use IMAP when you need to search/read email without the Gmail API, or for the hivesight.ai account which has no API token.

### Environment variables (in ~/.zshrc)

```bash
export GMAIL_APP_PASSWORD="..."          # max@policyengine.org
export GMAIL_PERSONAL_APP_PASSWORD="..." # mghenis@gmail.com
export GMAIL_HIVESIGHT_APP_PASSWORD="..."# max@hivesight.ai
```

### Usage

```python
import imaplib
import email
import os

def search_email(query, account="policyengine"):
    """Search Gmail via IMAP. account: 'policyengine', 'personal', or 'hivesight'"""
    accounts = {
        "policyengine": ("max@policyengine.org", os.environ["GMAIL_APP_PASSWORD"]),
        "personal": ("mghenis@gmail.com", os.environ["GMAIL_PERSONAL_APP_PASSWORD"]),
        "hivesight": ("max@hivesight.ai", os.environ["GMAIL_HIVESIGHT_APP_PASSWORD"]),
    }
    user, password = accounts[account]

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(user, password)
    mail.select("inbox")

    # Search (use Gmail search syntax in X-GM-RAW)
    status, messages = mail.search(None, f'X-GM-RAW "{query}"')

    results = []
    for num in messages[0].split()[-10:]:  # Last 10 matches
        status, data = mail.fetch(num, "(RFC822)")
        msg = email.message_from_bytes(data[0][1])
        results.append({
            "from": msg["From"],
            "to": msg["To"],
            "subject": msg["Subject"],
            "date": msg["Date"],
        })

    mail.logout()
    return results
```

### Common operations

- Search: `search_email("from:someone@example.com subject:invoice")`
- The X-GM-RAW search supports full Gmail search syntax
- For reading full message bodies, fetch with `(RFC822)` and parse with `email.message_from_bytes()`
- IMAP can be slow for drafts folder scanning — prefer Gmail API for draft operations
