---
description: File OpenCollective expenses for PolicyEngine - find invoices, gather billing data, and submit reimbursements
---

# OpenCollective expense filing

## 1. Find invoices and receipts

### Email (gog CLI, quick)

```bash
# GCP billing invoices
/opt/homebrew/bin/gog gmail search "from:billing-noreply@google.com subject:invoice" --max 5 --account max@policyengine.org

# Google Workspace invoices
/opt/homebrew/bin/gog gmail search "from:payments-noreply@google.com subject:invoice policyengine.org" --max 5 --account max@policyengine.org

# General recent invoices/receipts
/opt/homebrew/bin/gog gmail search "subject:(invoice OR receipt) newer_than:30d" --max 10 --account max@policyengine.org
```

### Downloads folder

```bash
ls -lt ~/Downloads/*.pdf ~/Downloads/*.png ~/Downloads/*.jpg 2>/dev/null | head -20
```

## 2. GCP billing

- **Billing account**: `0160DF-370818-B14FEA`
- **Currency**: GBP
- **Auth**: max@policyengine.org

```bash
# List recent invoices
gcloud billing accounts describe 0160DF-370818-B14FEA --format=json

# List billing for a project
gcloud billing projects describe policyengine-apps --format=json
```

Alternatively, download invoices from [Cloud Console billing](https://console.cloud.google.com/billing/0160DF-370818-B14FEA/payment?organizationId=).

## 3. Submit to OpenCollective

### Option A: MCP tools (if opencollective MCP server is running)

Use `submit_reimbursement` or `submit_invoice` MCP tools directly. They handle file upload, payee auto-detection, and payout method selection.

### Option B: Python API (fallback)

```python
from opencollective import OpenCollectiveClient

client = OpenCollectiveClient.from_token_file()
```

Run with: `uv run --project /Users/maxghenis/opencollective-py python -c "..."`

Or use the CLI: `uv run --project /Users/maxghenis/opencollective-py oc reimbursement "Description" 42.00 /path/to/receipt.pdf -c policyengine`

### Key client methods

| Method | Use for |
|--------|---------|
| `from_token_file()` | Create client from saved token (classmethod) |
| `submit_reimbursement(...)` | Out-of-pocket expenses with receipt |
| `submit_multi_item_reimbursement(...)` | Multi-line-item expense with receipts |
| `submit_invoice(...)` | Billing for services (no receipt needed) |
| `upload_file(path)` | Upload receipt/invoice to OC S3 |
| `create_expense(...)` | Low-level expense creation |
| `approve_expense(id_or_legacyId)` | Approve pending expense (accepts int legacyId or string id) |
| `get_expense(legacy_id)` | Get single expense by legacy ID |
| `get_expenses(slug)` | List/filter expenses (includes `createdByAccount`) |
| `get_me()` | Current user info + payout methods |

## 4. Defaults and conventions

| Field | Value |
|-------|-------|
| Collective slug | `policyengine` |
| Collective currency | USD |
| Payee slug | `max-ghenis` |
| Token file | `~/.config/opencollective/token.json` |
| Project path | `/Users/maxghenis/opencollective-py` |

### Required fields for every expense

- **description**: Clear, specific (e.g., "GCP January 2026 invoice")
- **amount_cents**: Integer cents (e.g., 4200 for $42.00)
- **currency**: Set explicitly if not USD (GCP is GBP)
- **incurred_at**: ISO date of the charge (e.g., "2026-01-31")
- **receipt_file**: Path to PDF/PNG/JPG (HTML auto-converts to PDF)
- **tags**: Relevant categories (e.g., `["cloud", "gcp"]`, `["workspace"]`, `["membership"]`)

### Currency notes

- GCP bills in **GBP** -- set `currency="GBP"` on those expenses
- Google Workspace bills in **USD**
- OC collective is USD; non-USD expenses show converted amount

## 5. After submission

- Show the expense URL: `https://opencollective.com/policyengine/expenses/{legacyId}`
- Ask the user if they want to approve (requires admin; use `approve_expense(id)`)
- Expense starts as PENDING until approved
