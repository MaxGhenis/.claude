---
description: Check and manage expenses - unfiled, pending approval, reconciliation
args: "[check|reconcile|search]"
---

# Expense Management

Use Max's expense scripts in ~/PolicyEngine/ to manage expenses.

## Check for Unfiled Expenses

```bash
cd ~/PolicyEngine && python find_unfiled_expenses.py
```

## Search Expense Emails

```bash
cd ~/PolicyEngine && python search_expense_emails.py
```

## Search Travel Expenses

```bash
cd ~/PolicyEngine && python search_travel_expenses.py
```

## Reconcile Expenses

```bash
cd ~/PolicyEngine && python reconcile_expenses.py
```

## Fetch Latest Expenses

From Open Collective:
```bash
cd ~/PolicyEngine && python fetch_oc_expenses_v2.py
```

From GCP:
```bash
cd ~/PolicyEngine && python fetch_gcp_invoice.py
```

## Output

Summarize what was found:
```
## Expense Status

### Unfiled (X items)
- [list any unfiled expenses]

### Pending Approval
- [list pending]

### Recent Activity
- [summary of recent expense activity]

**Action needed:** [any items requiring attention]
```
