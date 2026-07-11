---
name: codex-accounts
description: >
  Codex CLI multi-account quota management: detect/diagnose usage-limit and auth
  failures, rotate CODEX_HOME lanes across Max's ChatGPT accounts, and run the
  re-login flow (Claude drives, Max clicks). Use whenever a codex/codex-run job
  fails with "usage limit", 401, "refresh token was revoked", or when
  parallelizing codex workers across accounts. Triggers: "codex limit",
  "out of codex", "codex 401", "codex login", "rotate codex accounts".
---

# Codex multi-account quota management

## FIRST: check quota/auth state and pick a lane with ai-quota

The ai-quota monitor (~/chief-of-staff/ai-quota, launchd-refreshed every 30
min) replaces manual probing. Before dispatching or diagnosing:

```bash
ai-quota                    # live per-home table: 5h/weekly %, resets, auth verdicts
ai-quota status --cached    # instant, from the last watchdog snapshot
CODEX_HOME=$(codex-pick) codex-run ...   # best live lane (distinct-account + window aware)
codex-pick --json --all     # full ranking + why homes were excluded
ai-quota errors --hours 12  # observed usage-limit/revoked errors (rollouts + Claude transcripts)
```

`codex-pick` exits 1 when no lane is dispatchable (stderr says the earliest
reset) — treat that as "wait or ask Max to re-login", never dispatch blind.
By default it handicaps ~/.codex by 10 points to spare the primary account
backing Max's interactive apps (`--no-handicap` to rank raw). The watchdog
Telegram-alerts Max on revoked tokens, duplicate account bindings, fleet
exhaustion, and Claude session limits; it never auto-relogins.

## Account topology (ground rules)

- **One `CODEX_HOME` dir = one distinct ChatGPT account.** The binding lives in
  `$CODEX_HOME/auth.json`; `tokens.account_id` is ground truth (NOT the dir name).
- **Same account in two homes = revocation trap.** Each home stores its own token
  copy; when one refreshes, the account's refresh token rotates and the *other*
  home's copy is **revoked** ("Your access token could not be refreshed because
  your refresh token was revoked"). Never assume a long-dated local `exp` claim
  means the token works — revocation is server-side.
- **N concurrent agents on the SAME home is fine** (they share one token file).
  Parallelism within an account costs only that account's rate/usage window.
- Verify distinctness across all homes before spreading lanes:
  ```bash
  for h in ~/.codex ~/.codex-2 ~/.codex-3 ~/.codex-4; do
    printf "%s : " "$h"
    python3 -c "import json;print(json.load(open('$h/auth.json'))['tokens']['account_id'])" 2>/dev/null || echo "(no auth)"
  done
  ```
  Any duplicate account_id across homes → treat the extra home as dead until re-login.

## Quota model + failure signatures

- Each account has a **5-hour rolling window** and a weekly cap. They are
  **per-account**, with independent reset times.
- The ChatGPT app's usage display does NOT refresh from CLI usage — trust the
  server error, not the app gauge.
- Signatures (from stderr / codex-run err.log):
  - `You've hit your usage limit ... try again at H:MM` → window exhausted on
    that account. In-flight sessions continue; NEW sessions are refused at
    handshake. Rotate to another account or wait for the stated reset.
  - `refresh token was revoked` → home is dead; needs `codex login` (below).
  - Bare persistent `401 Unauthorized` on `wss://chatgpt.com/...responses` with
    no revocation message → account not entitled / binding dead; re-login it.
- codex-run (`~/bin/codex-run`) retries transient failures but a usage-limit
  error will burn all retries — don't re-dispatch to the same account.

## Rotation protocol (when a lane dies mid-program)

1. Read the failure signature (`<out>.err.log`, codex-run prints the tail).
2. Run `codex-pick --json --all` — it builds the availability map live
   (distinct accounts, blocked-until times, exclusion reasons). Manual
   fallback: the account_id one-liner above.
3. Re-dispatch to `$(codex-pick)`. If it exits 1 (no lane): run the re-login
   flow on dead homes, or wait for the earliest reset it reports.
4. Check salvage side-effects: codex-run's EXIT trap runs `git add -A` + commit
   in the workdir on ANY exit — after a failed lane, inspect the worktree for a
   `WIP salvage` commit sweeping junk (build artifacts, caches) and reset it off.

## Re-login flow (Claude drives, Max clicks — ~30s/account)

Claude runs the mechanics; Max only picks the account and clicks Allow.
Port 1455 is fixed → **one login at a time**, chained.

For each home needing (re)binding:

```bash
mkdir -p ~/.codex-N                        # required for brand-new homes
rm -f /tmp/codex-login-N.log
(CODEX_HOME=~/.codex-N codex login > /tmp/codex-login-N.log 2>&1 &)
# wait ~15s max, then:
grep -oE 'https://auth[^ ]+' /tmp/codex-login-N.log | head -1
```

1. Open that URL in Max's REAL Chrome (Control Chrome MCP `open_url`; the
   claude-in-chrome extension is often unpaired — don't block on it).
2. Tell Max which slot this is and to click **"Use another account"** if the
   page offers "Continue as" an account already bound to another home.
3. Watch for completion (background):
   `until grep -qiE 'success|logged in' /tmp/codex-login-N.log; do sleep 2; done`
4. On success, verify the new `account_id` is distinct from every other home.
   If it duplicates one → that pair is now a revocation trap; redo with the
   right account.
5. Chain the next home's login immediately.

Claude never types credentials or clicks Allow — sign-in is Max's action.

## Dispatch hygiene (cross-refs)

- Dispatch via `~/bin/codex-run` (retries, sandbox-safe git, salvage). On
  PUBLIC repos omit `-b` (salvage push fires even on success). Audits/gates:
  `-s read-only`. Implementation: `-s workspace-write`, commit-local, no push.
- Model notes: gpt-5.6-sol = reviews/reasoning; gpt-5.6-terra = encoder default;
  plain gpt-5.6/-codex fail rc=1. codex CLI ≥0.144 for 5.6 models.
- Content-filter blocks (rc=3): rewrite the prompt defensively (audit/verify
  framing, not construct/exploit framing) — do not retry verbatim.
