---
description: File Anthropic API/subscription expenses on OpenCollective - searches emails, deduplicates, downloads receipts, and submits
---

# Anthropic expense filing

File all Anthropic receipts as OpenCollective reimbursements for PolicyEngine. Both work and personal Anthropic charges are PE expenses.

## Step 1: Search both email accounts for Anthropic receipts

Search for receipts and refunds across both Google accounts. Use `--max 200` to avoid pagination caps.

```bash
# Work account (default gog account)
/opt/homebrew/bin/gog gmail search "from:invoice+statements@mail.anthropic.com subject:receipt" --max 200 --account max@policyengine.org

# Personal account
/opt/homebrew/bin/gog gmail search "from:invoice+statements@mail.anthropic.com subject:receipt" --max 200 --account mghenis@gmail.com

# Also search for refunds (both accounts)
/opt/homebrew/bin/gog gmail search "from:invoice+statements@mail.anthropic.com subject:refund" --max 200 --account max@policyengine.org
/opt/homebrew/bin/gog gmail search "from:invoice+statements@mail.anthropic.com subject:refund" --max 200 --account mghenis@gmail.com
```

Collect all message IDs from the results. Note which account each came from (needed for `--account` in later steps).

## Step 2: Check existing OC expenses for duplicates

Query existing expenses to avoid resubmitting receipts already filed.

```python
import json, os, sys
sys.path.insert(0, "/Users/maxghenis/opencollective-py/src")
from opencollective.client import OpenCollectiveClient

TOKEN_FILE = os.path.expanduser("~/.config/opencollective/token.json")
with open(TOKEN_FILE) as f:
    token = json.load(f)["access_token"]
client = OpenCollectiveClient(access_token=token)
```

Run with: `uv run --project /Users/maxghenis/opencollective-py python -c "..."`

To get expenses with their item-level details, use a custom GraphQL query via `client._request()`:

```python
query = """
query GetExpenses($account: AccountReferenceInput!, $fromAccount: AccountReferenceInput!, $limit: Int!) {
    expenses(account: $account, fromAccount: $fromAccount, limit: $limit, orderBy: {field: CREATED_AT, direction: DESC}) {
        totalCount
        nodes {
            id
            legacyId
            description
            amount
            currency
            status
            createdAt
            tags
            items {
                id
                description
                amount
                url
                incurredAt
            }
            attachedFiles {
                id
                url
                name
            }
        }
    }
}
"""
variables = {
    "account": {"slug": "policyengine"},
    "fromAccount": {"slug": "max-ghenis"},
    "limit": 200
}
data = client._request(query, variables)
existing_expenses = data["expenses"]["nodes"]
```

**Deduplication strategy**: Extract receipt numbers from existing expense item descriptions or attached file names. The receipt number (from the PDF filename pattern `Receipt-XXXX-XXXX-XXXX.pdf`) is the dedup key. Build a set of already-filed receipt numbers to skip.

## Step 3: Parse receipt details from emails

For each email message, extract the receipt details:

```bash
# Get email details as JSON (use appropriate --account for each message)
/opt/homebrew/bin/gog gmail get <message_id> --json --account max@policyengine.org
/opt/homebrew/bin/gog gmail get <message_id> --json --account mghenis@gmail.com
```

From each email, extract:
- **Amount**: The charge amount in USD (from the email body or subject)
- **Date**: The date of the charge (for `incurred_at`)
- **Receipt number**: From the attachment filename (e.g., `Receipt-1234-5678-9012.pdf`)

**Important**: Skip any refund emails (negative amounts). OC does not support negative expense amounts.

## Step 4: Download receipt PDFs

Create a directory and download only Receipt PDFs (skip Invoice PDFs):

```bash
mkdir -p /tmp/anthropic-receipts
```

For each email with an attachment:

```bash
# Get the message JSON to find attachment IDs
/opt/homebrew/bin/gog gmail get <message_id> --json --account <account>

# Download only Receipt-*.pdf files (NOT Invoice-*.pdf)
/opt/homebrew/bin/gog gmail attachment <message_id> <attachment_id> --out /tmp/anthropic-receipts/Receipt-XXXX-XXXX-XXXX.pdf --account <account>
```

Only download receipts that are NOT in the existing-expenses dedup set from step 2.

## Step 5: Upload PDFs and build expense items

Upload each receipt PDF to OpenCollective and build the items list:

```python
items = []
attached_file_urls = []

for receipt_file in sorted(os.listdir("/tmp/anthropic-receipts")):
    if not receipt_file.startswith("Receipt-") or not receipt_file.endswith(".pdf"):
        continue

    path = f"/tmp/anthropic-receipts/{receipt_file}"

    # Upload the file
    file_info = client.upload_file(path, kind="EXPENSE_ITEM")
    url = file_info["url"]

    # Build item (amount_cents, description, incurred_at, url come from step 3 parsing)
    items.append({
        "description": f"Anthropic {receipt_file.replace('.pdf', '')}",
        "amount": amount_cents,  # from parsed email data
        "incurredAt": f"{incurred_date}T00:00:00Z",  # ISO datetime
        "url": url,
    })
```

## Step 6: Confirm with user before submitting

Before creating the expense, show a summary and ask for confirmation:

- Number of new receipt items
- Total amount (sum of all items)
- List each item: receipt number, amount, date
- Note any skipped items (already filed or refunds)

**Wait for explicit user approval before proceeding.**

## Step 7: Submit multi-item expense

Create a single RECEIPT expense with all items using a raw GraphQL mutation (since `create_expense` only supports single items):

```python
mutation = """
mutation CreateExpense($expense: ExpenseCreateInput!, $account: AccountReferenceInput!) {
    createExpense(expense: $expense, account: $account) {
        id
        legacyId
        description
        amount
        status
    }
}
"""

# Get payee and payout method
me = client.get_me()
payee_slug = me["slug"]
methods = client.get_payout_methods(payee_slug)
payout_method_id = methods[0]["id"] if methods else None

expense_input = {
    "description": "Anthropic API/subscription charges",
    "type": "RECEIPT",
    "payee": {"slug": payee_slug},
    "items": items,  # all the items built in step 5
    "tags": ["anthropic", "ai-subscriptions", "api-credits"],
}
if payout_method_id:
    expense_input["payoutMethod"] = {"id": payout_method_id}

variables = {
    "account": {"slug": "policyengine"},
    "expense": expense_input,
}

data = client._request(mutation, variables)
expense = data["createExpense"]
```

Run all Python with: `uv run --project /Users/maxghenis/opencollective-py python -c "..."`

## Step 8: Report results

After submission, show:
- Expense URL: `https://opencollective.com/policyengine/expenses/{legacyId}`
- Total amount filed
- Number of receipt items
- Ask if user wants to approve the expense (requires admin; use `client.approve_expense(expense["id"])`)

## Reference

| Field | Value |
|-------|-------|
| Collective slug | `policyengine` |
| Payee slug | `max-ghenis` |
| Token file | `~/.config/opencollective/token.json` |
| Project path | `/Users/maxghenis/opencollective-py` |
| Receipt sender | `invoice+statements@mail.anthropic.com` |
| Work email | `max@policyengine.org` (gog default) |
| Personal email | `mghenis@gmail.com` |
| Receipt PDF pattern | `Receipt-XXXX-XXXX-XXXX.pdf` |
| Tags | `anthropic`, `ai-subscriptions`, `api-credits` |
| Currency | USD |
