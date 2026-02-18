# Max's Global Claude Instructions

## Cookie Preferences
**Always accept cookies** when browsing. Do not reject or decline cookies on any website.

## ⚠️ Read CLAUDE.md in repos you touch ⚠️

When working in any repo (even if not launched from there), read its CLAUDE.md.
Also check parent org folders (e.g., `CosilicoAI/CLAUDE.md`, `RulesFoundation/CLAUDE.md`).

## Fake/mock data disclosure
NEVER present fake, mock, or placeholder data without extremely explicit warnings in both the UI (prominent banner) and conversation (lead with a note). Name variables clearly (MOCK_DATA, PLACEHOLDER_VALUES). Always state the data source.

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
- **Never use `sonnet`** — always prefer opus or haiku

## Writing Style

### Sentence case for headings
Always use sentence case (only capitalize first word and proper nouns), not title case. Applies to all headings, titles, buttons, and UI text.

## Frontend Design

### General Projects
When creating new frontend designs, invoke the **frontend-design** skill:
```
Use Skill tool with skill: "frontend-design:frontend-design"
```
This creates distinctive, production-grade interfaces that avoid generic AI aesthetics.

### PolicyEngine projects
For PolicyEngine products, use the **policyengine-design-system** skill (in policyengine-claude plugin):
```
Use Skill tool with skill: "complete:policyengine-design-skill"
```

## Google API, Gmail, and Calendar

Use `/google-api` skill for credentials/auth code, `/gmail` skill for email patterns.

**Accounts:** max@policyengine.org (work) and mghenis@gmail.com (personal). Tokens in `~/.config/policyengine/`.
**IMAP accounts:** policyengine, personal, hivesight (app passwords in `~/.zshrc`).
**Always send emails as HTML** (plain text renders in a narrow column in Gmail).

### Quick access via gog CLI
```bash
/opt/homebrew/bin/gog calendar events --today --account max@policyengine.org  # Today's calendar
/opt/homebrew/bin/gog gmail search "is:unread is:important" --max 10 --account max@policyengine.org  # Quick email search
```
Use Google Calendar API (via `/google-api` skill) for creating/modifying events.
