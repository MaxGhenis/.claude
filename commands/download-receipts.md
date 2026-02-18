---
description: Download PDF receipt attachments from Gmail using gog CLI and save to a local directory
---

# Download receipts from Gmail

Automates downloading PDF receipt attachments from Gmail using the `gog` CLI. Supports searching across one or both Google accounts, filtering by attachment name pattern, and deduplicating results.

## Quick start

```bash
# Download all receipts from Anthropic billing (last 200 messages)
/download-receipts "from:billing@anthropic.com subject:receipt"

# Download from both accounts with a custom output directory
/download-receipts "subject:receipt newer_than:30d" --accounts both --out ~/Downloads/receipts

# Download only files matching a pattern
/download-receipts "from:vendor@example.com" --pattern "Invoice-*.pdf"
```

## Parameters

Pass parameters as text in your message. The system will parse:

| Parameter | Format | Default | Notes |
|-----------|--------|---------|-------|
| **search query** | `"from:... subject:..."` (Gmail search syntax) | Required | Use Gmail search operators: `from:`, `subject:`, `newer_than:`, `is:unread`, etc. |
| **--accounts** | `work` \| `personal` \| `both` | `both` | Which account(s) to search. `work` = max@policyengine.org, `personal` = mghenis@gmail.com |
| **--out** | `/path/to/directory` | `/tmp/receipts/` | Where to save PDFs. Directory is created if it doesn't exist. |
| **--pattern** | `"Filename-*.pdf"` | (none) | Optional glob pattern to filter attachment names (e.g., `"Receipt-*.pdf"` matches only files starting with "Receipt-") |
| **--max** | integer | `200` | Max emails to search per account. Increase for large result sets. |

## How it works

### 1. Search emails
Uses `gog` CLI to find emails matching your query:
```bash
/opt/homebrew/bin/gog gmail search "<query>" --max <N> --account <account>
```

- Searches are **case-insensitive** and use full Gmail search syntax
- Results are paginated if > max results; the command checks for continuation
- Deduplication happens across accounts by matching subject line and message ID

### 2. Download attachments
For each found email:
- Fetches metadata: `gog gmail get <msgId> --json --account <account>`
- Filters attachments by filename pattern (if specified)
- Downloads: `gog gmail attachment <msgId> <attId> --out <dir>/<filename> --account <account>`
- Skips files already in the output directory (no overwrites)

### 3. Report results
- Lists all downloaded files with sizes
- Total count and combined size
- Reports any failures or skipped messages

## Important notes

### Google accounts
Two accounts available:
- **max@policyengine.org** (work)
- **mghenis@gmail.com** (personal)

Use `--accounts work`, `--accounts personal`, or `--accounts both`.

### gog CLI details
- Located at: `/opt/homebrew/bin/gog`
- Handles authentication via macOS Keychain (no manual token management)
- Supports JSON output for metadata: `--json` flag

### Attachment handling
- Some emails have **multiple PDF attachments** — use `--pattern` to filter
  - Example: email with "Invoice.pdf" + "Cover-Letter.pdf" — use `--pattern "Invoice*.pdf"` to get only the invoice
- Duplicates are skipped if filename already exists in output directory
- Non-PDF attachments are ignored by default (only PDFs are downloaded)

### Search best practices
- Always use **--max 200 or higher** to avoid truncating results
- Use `newer_than:30d` to limit to recent emails
- Use `is:unread` to find unseen receipts
- Use `has:attachment` to ensure emails have attachments
- Combine with `filename:pdf` to pre-filter (Gmail search supports this)

Examples:
```bash
# All unread receipts from the last 30 days
/download-receipts "is:unread subject:receipt newer_than:30d"

# All invoices from a vendor, with pattern filtering
/download-receipts "from:vendor@acme.com has:attachment" --pattern "Invoice-*.pdf"

# Search work account only, high limit
/download-receipts "subject:billing" --accounts work --max 500
```

### Pagination
If the search returns more results than `--max`, the command will check for a "Next page" token in the output and alert you. To get all results, increase `--max` or run again with pagination token (if supported).

### Error handling
- **Auth errors**: Check that `gog` is configured. Run `/opt/homebrew/bin/gog gmail search "newer_than:1d" --account max@policyengine.org` to test.
- **Download failures**: File permission errors or network issues are reported per file.
- **Empty results**: If no emails match, the command will report zero downloads (not an error).
- **Invalid pattern**: `--pattern` uses glob syntax (`*` = any chars, `?` = single char). Invalid patterns are reported before processing.

## Example workflow

1. **Find recent receipts**
   ```bash
   /download-receipts "subject:receipt newer_than:7d"
   ```

2. **Download with filtering**
   ```bash
   /download-receipts "from:billing-noreply@company.com subject:invoice" --out ~/Documents/invoices --pattern "Invoice-2026-*.pdf"
   ```

3. **Search one account only**
   ```bash
   /download-receipts "has:attachment subject:receipt" --accounts work
   ```

4. **View downloaded files**
   ```bash
   ls -lh /tmp/receipts/
   ```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "gog not found" | Ensure `/opt/homebrew/bin/gog` exists. If not, install gog CLI or check PATH. |
| No results returned | Check your search query syntax in Gmail web interface first to verify it returns results. |
| Downloads to wrong directory | Ensure `--out` path is absolute (starts with `/`). Relative paths may not work as expected. |
| Duplicate files across accounts | Use `--accounts work` or `--accounts personal` to limit to one account. |
| Pattern not filtering | Glob patterns are case-sensitive. Use `--pattern "*.pdf"` to match all PDFs, then check output. |
| "Permission denied" on output directory | Ensure you have write access to the output directory. Try `/tmp/receipts/` for testing. |

