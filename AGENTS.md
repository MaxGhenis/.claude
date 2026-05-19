# Global agent rules

## PR-backed changes

- All substantive code, config, CI, documentation, and generated-artifact changes must go through a pull request.
- Start branches from the remote default branch, not a possibly dirty local branch: `git fetch origin && git checkout -b <branch> origin/main`.
- Do not commit on or push directly to protected branches: `main`, `master`, `develop`, `trunk`, `production`, `prod`, or `gh-pages`.
- If the user says "push this", interpret that as "push a branch and open/update a PR" unless they explicitly request a direct protected-branch push.
- Do not leave meaningful fixes as local dirty state. If a local patch affects a reported result, reproduction, or teammate workflow, publish it on a branch/PR before treating the result as reproducible.
- For Axiom repos, never hand-edit generated RuleSpec as the final workflow. Fix the generator/encoder/oracle path and publish that change by PR.
- Prefer GitHub branch protection/rulesets on shared repos: block direct default-branch pushes and require stable PR checks. Local hooks are only a backstop.

## CI strategy

- Code changes need unit tests and lint/type/format checks appropriate to the repo.
- CLI and workflow changes need a fast PR smoke test for the changed command, script, registry, or config.
- Scheduled or manually dispatched workflows must also have a pull-request validation path; do not leave them untested until the next schedule.
- Generated outputs should either be regenerated in CI or have the exact generation command and source revision documented in the PR body.
- Before reporting a PR as ready, confirm both latest checks and mergeability: `gh pr checks <pr>` and `gh pr view <pr> --json mergeStateStatus,mergeable`.
- If a PR has no new CI after a push, check mergeability first; conflicts or dirty merge state are often the real cause.

## Changelogs and release notes

- Add release notes only for user-visible behavior, public API/CLI changes, generated artifacts, deployment/ops changes, or published package behavior.
- Use the repo's existing changelog system.
- For Python packages with releases, prefer Towncrier (`changelog.d/`).
- For versioned JavaScript/TypeScript packages, prefer Changesets.
- For apps, dashboards, infra, one-off scripts, and docs-only repos, use the PR body instead of adding changelog machinery.
- Do not introduce Towncrier or Changesets just to satisfy a one-off internal change.

## Existing global preferences

- Do not put `[codex]` in PR titles.
- Prefer APIs, MCPs, and CLIs over browser automation when available.
- Use `uv` for Python and `bun`/`bunx` for JavaScript/TypeScript.
- Use pytest for Python tests and Vitest for JavaScript/TypeScript tests.
