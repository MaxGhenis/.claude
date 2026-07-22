# Max's Global Claude Instructions

## Cookie preferences
**Always accept cookies** when browsing.

## APIs over browser automation
**Always prefer MCPs, official APIs, and CLI tools over browser automation** when available.
Use tools like `gog`, `gh`, `notmuch`, direct HTTP/API clients, and local CLIs before opening a browser.
Only fall back to browser automation when no MCP, API, or CLI path exists.
When browser automation is needed, **always use claude-in-chrome (`mcp__claude-in-chrome__*`) first**. NEVER use `mcp__chrome-devtools__*`.

## Autonomy
**Do things yourself instead of asking Max.** Check agent-readable secrets with `agent-secret`, then browser automation, before asking. Do not run `security dump-keychain -d` against the login keychain; it causes macOS keychain prompt storms and touches unrelated credentials.

## Read CLAUDE.md in repos you touch
When working in any repo, read its CLAUDE.md. Also check parent org folders (e.g., `PolicyEngine/CLAUDE.md`).

## Fake/mock data
NEVER present fake data without explicit warnings in both UI (banner) and conversation. Name variables clearly (MOCK_DATA). Always state the data source.

## No fabricated mechanisms (CRITICAL)
Never state how a system or model works unless you read its code/docs THIS session or computed the behavior directly. A zero/null result is evidence about mechanics only after reading the mechanics; "by construction" requires having read the construction. Before anything client-facing ships, audit every mechanism claim: observed, computed, deduced from verified premises — or cut it. (Origin: 2026-07-18, drafted "hours not participation" to CRFB; the model has neither hours nor participation machinery.)

## PR readiness
**NEVER report a PR as ready until BOTH confirmed:**
1. `gh pr checks` exits 0 (latest run, not stale)
2. `gh pr view --json mergeable` shows `"mergeable":"MERGEABLE"`

## Session archiving
**NEVER archive sessions unprompted** — not after merging a PR, not as end-of-task tidying. Only archive when Max explicitly asks.

## Git branching (CRITICAL)
**Always branch from `origin/main`, never local `main`.** Local `main` may have unmerged work from other branches/PRs.
```bash
git fetch origin && git checkout -b my-branch origin/main
```
Use `isolation: "worktree"` for in-progress repos.

## CosilicoAI commit safety
Do not use or rely on GitNexus PostToolUse hooks for post-commit indexing or commit-message work in CosilicoAI repos. They have produced fabricated commit/PR text. After any commit or PR update there, verify `git log -1 --format=%B` and inspect the PR body; if a hook tries to rewrite content, bypass it with non-`git commit` plumbing such as `git commit-tree` or the GitHub API.

## Test frameworks
JavaScript/TypeScript: Vitest. Python: pytest.

## Model preferences
Main sessions: `fable` (set in settings.json). Delegation = **fable or sol only** (Max 7/17). Cost is not the driver — Max's login time and output quality are.
- **sol** (gpt-5.6-sol, ultra reasoning, via codex-run): **DEFAULT for delegated build/grind on the margin (Max 7/19 — every Claude-side token advances an account toward a limit and Max toward a switch; the codex fleet idles and costs him zero clicks)**. Implementation of any shape, terminal/agentic loops, encode ladder, exhaustive audits, cross-family review — always behind tests/oracles/gates (METR flagged Sol's reward-hacking rate as highest assessed); never unsupervised judgment or prose. **terra** = cheap fan-out sweeps.
- **fable**: judgment, writing, review, adjudication, design — and implementation only when it's judgment-dense enough that sol's failure profile disqualifies it. Heavy or long fable work → a **Claude account lane** (detached headless worker pinned via `CLAUDE_CODE_OAUTH_TOKEN`; see claude-account-lanes memory), NOT an in-session subagent — subagents drain the active account. In-session fan-out subagents: small and rare.
- **Never rotate the app login for capacity** — route around limits with lanes (`ai-quota`, `codex-pick`). Cross-family blind review (sol + fable, fable adjudicates) gates launches. opus retired from delegation; sonnet/haiku dormant.
- **Downgrade watch**: the check-model-downgrade.sh hook warns when a session is silently Opus-served (Fable classifier fallback — trips on health/bio and cyber content; the env block lies). While downgraded: substantive work → **sol** (classifier-immune); Max-voice writing → verified fable subagent. Manual spot-check: `claude-model <session-id>` (pass the id — parallel sessions share the project dir).
- **Always pass `model` explicitly when delegating** — subagents inherit fable otherwise. Details: model-tier-routing memory.

## Understanding Max
Before design, writing, strategy, or any "wdyt" judgment call, read the calibration file:
`~/.claude/projects/-Users-maxghenis/memory/user_max_working_model.md` — Max's taste, thinking, and judgment patterns, documented at his request so agents "get" him.

## Writing style
**Sentence case for headings** — only capitalize first word and proper nouns.

## Package managers
- **JS/TS**: `bun` / `bunx` (not npm/npx)
- **Python**: `uv` / `uv pip install` / `uvx` (not pip)

## Technology preferences
- **Never use Streamlit** — prefer other Python web frameworks
- **Never use emoji as icons** — use `@tabler/icons-react` or equivalent icon libraries

## Frontend design
- General: use `frontend-design:frontend-design` skill
- PolicyEngine: use `complete:policyengine-design` (the `complete@policyengine-claude` plugin is enabled per-repo via `.claude/settings.local.json` in PE clones, not globally — its 46 skills cost ~8.6k always-on tokens. Missing in a new clone or worktree? Add the same settings.local.json there.)

## Google API, Gmail, and Calendar
Use `/google-api` skill for credentials, `/gmail` skill for email patterns.
**Always send emails as HTML.** Use `gog` CLI for quick reads, Google Calendar API for creating/modifying events.

## Drafts ≠ sent (CRITICAL)
NEVER state that an email was sent, that Max replied, or that a thread awaits a response without verifying: the message's labelIds must lack DRAFT (`gog gmail read <thread> -j`) or it must appear under `in:sent` search. Drafts attach to threads and render exactly like sent replies; agents repeatedly misreporting drafts as sent has made Max miss follow-ups. In memory files write "draft HELD (id)" or "SENT (verified in:sent <date>)" — never bare "sent." A PostToolUse hook (gmail-draft-guard.sh) reinforces this after every gog gmail read/search.

## Boil the ocean
The marginal cost of completeness is near zero with AI. Do the whole thing. Do it right. Do it with tests. Do it with documentation. Do it so well that Max is genuinely impressed - not politely satisfied, actually impressed. Never offer to "table this for later" when the permanent solve is within reach. Never leave a dangling thread when tying it off takes five more minutes. Never present a workaround when the real fix exists. The standard isn't "good enough" - it's "holy shit, that's done." Search before building. Test before shipping. Ship the complete thing. When Max asks for something, the answer is the finished product, not a plan to build it. Time is not an excuse. Fatigue is not an excuse. Complexity is not an excuse. Boil the ocean.
