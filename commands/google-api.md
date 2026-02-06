---
description: Google API credentials, authentication, and service access for Max's work and personal accounts
---

# Google API integration

OAuth credentials are set up for the `policyengine-apps` GCP project (ID: 578039519715).

## Accounts

| Account | Token file | Env var |
|---------|-----------|---------|
| max@policyengine.org (work) | `google-token.json` | `GOOGLE_TOKEN_FILE` |
| mghenis@gmail.com (personal) | `google-token-personal.json` | `GOOGLE_PERSONAL_TOKEN_FILE` |

All tokens live in `~/.config/policyengine/`.

## Environment variables (in ~/.zshrc)

```bash
export GOOGLE_CREDENTIALS_FILE="$HOME/.config/policyengine/google-credentials.json"
export GOOGLE_TOKEN_FILE="$HOME/.config/policyengine/google-token.json"
export GOOGLE_PERSONAL_TOKEN_FILE="$HOME/.config/policyengine/google-token-personal.json"
```

## Core authentication code

```python
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    # Gmail - full access
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    # Calendar - full read/write
    "https://www.googleapis.com/auth/calendar",
    # Drive - full access
    "https://www.googleapis.com/auth/drive",
    # Docs
    "https://www.googleapis.com/auth/documents",
    # Sheets - full access
    "https://www.googleapis.com/auth/spreadsheets",
    # Slides
    "https://www.googleapis.com/auth/presentations",
    # Contacts
    "https://www.googleapis.com/auth/contacts",
    # Tasks
    "https://www.googleapis.com/auth/tasks",
    # Profile
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
]

CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", os.path.expanduser("~/.config/policyengine/google-credentials.json"))

TOKEN_PATHS = {
    "work": os.environ.get("GOOGLE_TOKEN_FILE", os.path.expanduser("~/.config/policyengine/google-token.json")),
    "personal": os.environ.get("GOOGLE_PERSONAL_TOKEN_FILE", os.path.expanduser("~/.config/policyengine/google-token-personal.json")),
}
TOKEN_PATH = TOKEN_PATHS["work"]

def get_google_credentials(account="work"):
    """Get Google OAuth credentials, refreshing if needed.
    account: 'work' (max@policyengine.org) or 'personal' (mghenis@gmail.com)
    """
    token_path = TOKEN_PATHS[account]
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds
```

## Available scopes

**Work token** (max@policyengine.org): Gmail, Calendar, Drive, Docs, Sheets, Slides, Contacts, Tasks, Profile.

**Personal token** (mghenis@gmail.com): All of the above PLUS YouTube (read/write), Google Photos Library (read), Google Chat (messages + spaces read).

Note: Google Keep API is enterprise-only (Workspace accounts) and cannot be used with personal Gmail.

## Example: Google Calendar API

```python
def list_today_events(account="work"):
    """List today's calendar events."""
    from datetime import datetime, timezone
    creds = get_google_credentials(account)
    service = build("calendar", "v3", credentials=creds)
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0).isoformat()
    end = now.replace(hour=23, minute=59, second=59).isoformat()
    events = service.events().list(
        calendarId="primary", timeMin=start, timeMax=end,
        singleEvents=True, orderBy="startTime"
    ).execute().get("items", [])
    return [{"summary": e.get("summary"), "start": e["start"].get("dateTime", e["start"].get("date")),
             "end": e["end"].get("dateTime", e["end"].get("date")), "attendees": [a["email"] for a in e.get("attendees", [])]}
            for e in events]

def create_event(summary, start, end, attendees=None, account="work"):
    """Create a calendar event. start/end are ISO datetime strings."""
    creds = get_google_credentials(account)
    service = build("calendar", "v3", credentials=creds)
    event = {"summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end}}
    if attendees:
        event["attendees"] = [{"email": e} for e in attendees]
    return service.events().insert(calendarId="primary", body=event, sendUpdates="all").execute()
```

## Example: Upload HTML as Google Doc

```python
def upload_html_as_doc(title, html_file_path):
    creds = get_google_credentials()
    drive_service = build("drive", "v3", credentials=creds)
    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document"
    }
    media = MediaFileUpload(html_file_path, mimetype="text/html")
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    return f"https://docs.google.com/document/d/{file.get('id')}/edit"
```

## Dependencies

```bash
pip install google-auth-oauthlib google-api-python-client
```

## Notes

- Token auto-refreshes; no browser login needed after initial auth
- Token has comprehensive scopes - no need to regenerate for most Google API tasks
- GCP project: `policyengine-apps` (project ID: 578039519715)
