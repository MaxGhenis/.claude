---
description: Repeatedly review, fix, verify, and re-review the current change until clean
argument-hint: <target change or review instructions>
allowed-tools: [Bash, Task, Read, Edit, MultiEdit, Grep, Glob]
---

# Cycle

Run a review-fix cycle on the current repository state.

Use the `cycle` skill.

## Arguments

- `$ARGUMENTS`: The target change, commit, council, PR, or extra instructions. If blank, infer the target from the latest commit and current branch.

## Required workflow

1. Inspect branch, latest commits, and worktree status.
2. Identify the target change from `$ARGUMENTS` or the latest local commit.
3. Request an independent review:
   - Prefer `/codex` if available; otherwise use `codex exec` directly from the current working directory with stdin redirected (`</dev/null`) — codex otherwise reads the inherited stdin and can exit 0 without running the prompt.
   - Ask for concrete actionable findings only: bugs, source-fidelity issues, missing tests, and residual risk.
   - Scope Codex to the latest council/change and changed files only.
   - Time-box Codex to 10-12 minutes. If it produces no output, kill it, record the timeout, and do not retry automatically.
4. Fix actionable findings directly.
5. Add or update tests for each fix where practical.
6. Run focused tests and relevant lint/import/smoke checks.
7. Commit review fixes separately from the first-pass implementation.
8. Repeat review and fix cycles until clean.

## Stop and report

Stop only when the latest review is clean, remaining issues are non-actionable/blocked, or a user decision is needed.
If Codex times out once and Claude subagent review is clean, stop and report the Codex timeout instead of spending more Codex time.

Report:

- Reviews run.
- Findings fixed.
- Commits created.
- Verification commands and results.
- Whether anything remains blocked or intentionally deferred.
