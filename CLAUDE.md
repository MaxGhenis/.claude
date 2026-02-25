# Max's Global Claude Instructions

## Cookie Preferences
**Always accept cookies** when browsing. Do not reject or decline cookies on any website.

## APIs over browser automation
**Always prefer APIs over browser automation** when an API is available (e.g., Xero API, Google API, GitHub API). APIs are faster, more reliable, and don't depend on login sessions or Chrome profiles. Only fall back to browser automation when no API exists.

When browser automation is needed, **always use claude-in-chrome (`mcp__claude-in-chrome__*`) first**. NEVER use `mcp__chrome-devtools__*` unless claude-in-chrome is completely unavailable and you've exhausted all options to fix it. The chrome-devtools MCP launches a separate Chrome profile that can't access the user's logged-in sessions, tabs, or extensions.

## Autonomy preferences
**Do things yourself instead of asking Max to do them.** If a task requires visiting a website, logging in, copying a key, filling out a form, etc. — use browser automation or CLI tools to do it. Only ask Max as a last resort when tools are genuinely unavailable. If credentials are needed, check the keychain (`manage-secret.sh`) first, then try browser automation to get them, before asking.

## ⚠️ Read CLAUDE.md in repos you touch ⚠️

When working in any repo (even if not launched from there), read its CLAUDE.md.
Also check parent org folders (e.g., `CosilicoAI/CLAUDE.md`, `RulesFoundation/CLAUDE.md`).

## Fake/mock data disclosure
NEVER present fake, mock, or placeholder data without extremely explicit warnings in both the UI (prominent banner) and conversation (lead with a note). Name variables clearly (MOCK_DATA, PLACEHOLDER_VALUES). Always state the data source.

## PR readiness verification
**NEVER tell the user a PR is ready until BOTH conditions are confirmed:**
1. `gh pr checks` exits 0 (all CI checks pass) — on the LATEST run, not a stale one
2. `gh pr view --json mergeable` shows `"mergeable":"MERGEABLE"` (no merge conflicts)

Always check both after pushing. If either fails, fix the issue before reporting.

---

## Development Workflow

### Test frameworks
For JavaScript/TypeScript, use Vitest. For Python, use pytest.

### Task management
Use Claude Code's built-in Tasks (TaskCreate/TaskUpdate) for work tracking. For cross-session persistence, set `CLAUDE_CODE_TASK_LIST_ID` per project (tasks stored in `~/.claude/tasks/{id}/`). For team-visible tracking, use GitHub Issues via `gh`.

### Subagent types
- `complete:country-models:rules-engineer` — Implement tax/benefit rules
- `complete:country-models:document-collector` — Research data sources
- `complete:country-models:test-creator` — Write comprehensive tests
- `general-purpose` — Multi-step research and implementation
- `Explore` (with haiku) — Quick codebase exploration

## Model preferences

When spawning subagents with the Task tool:
- **Default (most things)**: Use `opus` (or omit model param to inherit)
- **Super simple tasks**: Use `haiku`

## Writing Style

### Sentence case for headings
Always use sentence case (only capitalize first word and proper nouns), not title case. Applies to all headings, titles, buttons, and UI text.

## Package manager preferences
- **JavaScript/TypeScript**: Use `bun` (not npm/npx). Use `bunx` instead of `npx`.
- **Python**: Use `uv` (not pip). Use `uv pip install` / `uv run` / `uvx` instead of `pip install` / `python -m` / `pipx`.

## Technology preferences
**Never use Streamlit.** For Python web apps, prefer other frameworks.

### Icons
**Never use emoji as icons** in code or UI. Use `@tabler/icons-react` (the PolicyEngine standard) or equivalent proper icon libraries.

## Frontend Design
- **General projects**: Use `frontend-design:frontend-design` skill
- **PolicyEngine projects**: Use `complete:policyengine-design-skill` skill

## Google API, Gmail, and Calendar

Use `/google-api` skill for credentials/auth code, `/gmail` skill for email patterns.

**Accounts:** max@policyengine.org (work) and mghenis@gmail.com (personal). Tokens in `~/.config/policyengine/`.
**IMAP accounts:** policyengine, personal, hivesight (app passwords in macOS Keychain via `load-secrets.sh`).
**Always send emails as HTML** (plain text renders in a narrow column in Gmail).

### Quick access via gog CLI
```bash
/opt/homebrew/bin/gog calendar events --today --account max@policyengine.org  # Today's calendar
/opt/homebrew/bin/gog gmail search "is:unread is:important" --max 10 --account max@policyengine.org  # Quick email search
```
Use Google Calendar API (via `/google-api` skill) for creating/modifying events.
