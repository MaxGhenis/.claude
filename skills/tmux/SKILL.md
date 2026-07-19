---
name: tmux
description: Use when interacting with tmux — sending commands to panes, creating panes, resuming sessions, checking pane status, or any tmux operation. Triggers on "tmux", "pane", "resume session", "restore session", "new pane", "send to pane", "grid", "split", "restore", "sessions went away", "lost sessions", "recover sessions".
---

# tmux skill

Max runs Claude Code sessions in tmux. This skill ensures safe, correct tmux operations.

## Max's setup

- **Session**: `c`
- **Pane numbering**: starts at 1 (`pane-base-index 1`)
- **Config**: `~/dotfiles/.tmux.conf`
- **Plugin**: [tmux-claude-code](https://github.com/MaxGhenis/tmux-claude-code) (TPM plugin for session management)
- **Keybindings**: `prefix+c` new Claude pane, `prefix+C` new named pane, `prefix+Ctrl-r` resume by keyword, `prefix+Ctrl-b` browse sessions, `prefix+g` tile grid

### Window layout

| Key | Window | Purpose |
|-----|--------|---------|
| `0` | meta | **Single pane only** — persistent Claude Code session for managing other windows/panes |
| `1` | policyengine | All PolicyEngine work |
| `2` | other | Rules Foundation, Cosilico, Eggnest, outreach, decks |
| `3` | personal | Side projects, personal errands, life stuff |

## Window numbers (CRITICAL)

Always run `tmux list-windows -t c -F '#{window_index}:#{window_name}'` before targeting a window — never assume the index.

## Safety rules

### NEVER create panes in 0:meta

Window 0 (meta) is a single-pane control plane. **Never** `split-window`, `join-pane`, or `cc` into it. When creating new panes for resumed sessions or new work, target the appropriate thematic window (1, 2, or 3).

### NEVER claim success without verification (CRITICAL — HARD LESSON)

**Every** resume/restore/split/create operation MUST be followed by verification before reporting to Max. Never say "Resumed", "Done", "Created", or "It's in pane X" without proof.

**Anti-patterns from real failures — NEVER do these:**
- "Resumed the session in a new pane" — without checking any pane exists
- "Should be in window 3, the newest pane" — "should be" = guessing = lying
- "It's in window X pane Y" — without running `tmux list-panes` and `capture-pane` first
- Saying the session is restored, then when asked "which pane?" not being able to find it
- Running `cc resume` via `tmux run-shell` and assuming it worked — `run-shell` gives no feedback on where the pane landed or whether it succeeded
- Claiming a JSONL file "matches" based on one keyword without reading actual content

**Where `cc resume` actually creates panes:**
- `tmux run-shell` runs in the tmux server context, NOT in any specific window
- `cc resume` calls `tmux split-window` without `-t`, so it splits whatever tmux considers the "current" pane — which is UNPREDICTABLE when called from `run-shell`
- If split fails (no space), it falls back to `tmux new-window`
- **You cannot predict where it lands. You MUST search all windows after.**

**Preferred approach — use `split-window -t` directly instead of `cc resume`:**
```bash
# This is deterministic — you control exactly where it goes
tmux split-window -t c:other -c ~ "env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT claude --resume 'SESSION_ID' --dangerously-skip-permissions; exec zsh"
tmux select-layout -t c:other tiled
```

### NEVER send keys to an occupied pane

Before sending any command to a pane, check what's running:

```bash
tmux list-panes -t c:1 -F '#{pane_index} #{pane_current_command}'
```

- Only send to panes where command is `zsh` or `bash` (idle shell)
- Claude Code shows as `claude`, `node`, or a version like `2.1.68` — these are OCCUPIED
- **`pane_current_command` can show `zsh` even when CC is running** — CC runs inside zsh. Always `capture-pane` and look for the `❯` prompt/TUI before assuming a pane is an idle shell.
- **Blank visible output does NOT mean empty** — Claude Code's TUI can show blank areas
- If no pane is free, **create a new one** instead
- **If you send keys to a CC pane by mistake**, the text goes into CC's input bar. Use `Cmd+A` then `Backspace` or `C-a C-k` to clear it. Always `capture-pane` after to verify it's clean.

### Replacing a session in an existing pane

Prefer creating a new pane. If you must reuse one: exit CC first (`/exit`), wait for `pane_current_command` to return `zsh`, then resume.

### Creating a new pane

Always target the right thematic window. Never window 0 (meta). Use window name, not index:

```bash
tmux split-window -t c:policyengine -c ~ "env -u CLAUDECODE claude --resume SESSION_ID; exec zsh"
tmux select-layout -t c:policyengine tiled
```

### Window categorization

Target the correct window based on context. When in doubt, use `other`.

- **policyengine**: PolicyEngine repos, PE meetings, PE social/marketing, PE data work
- **other**: Rules Foundation, Cosilico, Eggnest, academic papers, outreach, decks, conferences, OpenMessage product work
- **personal**: Personal errands, health (Whoop), relationships, side projects (farness, manifold-cli), personal finance

## Resuming a session — MANDATORY protocol

### Step 1: Find the session

**`claude-search` is NOT comprehensive** — it only returns ONE result per query and only indexes the first 3 user messages. NEVER rely on it alone. Always follow up with a direct grep:

```bash
# Comprehensive search — finds ALL sessions mentioning keyword
find ~/.claude/projects/ -name "*.jsonl" -not -path "*/subagents/*" -type f | xargs grep -l "keyword" 2>/dev/null | while read f; do
  echo "born=$(stat -f '%SB' -t '%Y-%m-%d %H:%M' "$f") mod=$(stat -f '%Sm' -t '%Y-%m-%d %H:%M' "$f") $f"
done | sort
```

**Always check BIRTH time, not just mod time.** A session created yesterday but continued today will have today's mod time. When the user says "yesterday's session," filter by birth time:
```bash
stat -f '%SB' -t '%Y-%m-%d %H:%M' "$file"  # birth time (creation)
stat -f '%Sm' -t '%Y-%m-%d %H:%M' "$file"  # mod time (last write)
```

When multiple results come back, read the first few user messages from each JSONL to confirm you have the right one — don't just pattern-match on one keyword.

### Step 1.5: Check if already open

**Before resuming, ALWAYS check if the session is already running in a pane.** Use the fingerprint script:

```bash
python3 ~/tmux-claude-code/scripts/find_session_pane.py SESSION_ID
```

If it exits 0, it prints `PANE_ID WINDOW_NAME` — the session is already open. Just navigate Max there instead of creating a duplicate. If it exits 1, proceed with Step 2.

### Step 2: Launch it

`cc resume` splits a pane in the **current window** (or creates a new window if no space). It does NOT navigate Max there. The pane is created wherever tmux's focus currently is, which may differ from where Claude Code's Bash tool runs.

```bash
tmux run-shell "unset CLAUDECODE && ~/bin/cc resume keywords"
```

Or target a specific window explicitly:

```bash
tmux split-window -t c:other -c ~ "env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT claude --resume 'SESSION_ID' --dangerously-skip-permissions; exec zsh"
tmux select-layout -t c:other tiled
```

### Step 3: VERIFY (non-negotiable — do ALL of these or say nothing)

You MUST complete ALL 4 checks before saying ANYTHING to Max. If you skip even one, you are lying.

**Check 1: Find the pane.** Search ALL windows — don't assume which window it landed in:
```bash
for w in $(tmux list-windows -t c -F '#{window_index}'); do
  tmux list-panes -t c:$w -F "c:$w.#{pane_index} #{pane_id} cmd=#{pane_current_command}" 2>/dev/null
done
```
Look for the session ID in `pane_start_command`:
```bash
tmux display -t %PANE_ID -p '#{pane_start_command}'
```

**Check 2: Confirm CC is actually running.** `pane_current_command` must be `claude`, `node`, or a version like `2.1.68`. If it's `zsh`, CC already exited — tell Max it failed.

**Check 3: Read the pane content** to confirm it's the RIGHT session, not just any session:
```bash
tmux capture-pane -t %PANE_ID -p -S -50 | tail -30
```

**Check 4: Only THEN tell Max** the exact window and pane. Use verified facts only — "It's running in c:3.2" not "should be in window 3".

**If ANY check fails:** Say "The resume didn't work" or "I can't find where it landed." NEVER guess. NEVER say "should be." Honesty about failure is infinitely better than a false claim of success.

### Step 4: Navigate Max there

```bash
tmux select-window -t c:WINDOW && tmux select-pane -t %PANE_ID
```

## Stagger pane creation

When restoring many sessions at once, **stagger launches** with `sleep 0.5` between each `split-window` to avoid a tmux segfault from fork pressure during mass simultaneous spawning.

## Recovering from a crash

Search all sessions from today (`-mtime -1`) — idle sessions killed by a crash have old mtimes. Create windows (`meta`, `policyengine`, `other`, `personal`) first, then categorize and stagger launches.

```bash
# Find all today's sessions
find ~/.claude/projects/ -name "*.jsonl" -not -path "*/subagents/*" -mtime -1 -type f

# Resume into the right window (stagger with sleep 0.5):
tmux split-window -t c:policyengine -c ~ "claude --resume SESSION_ID"
tmux select-layout -t c:policyengine tiled
```

## Common operations

| Task | Command |
|------|---------|
| List all windows | `tmux list-windows -t c -F '#{window_index}:#{window_name} (#{window_panes} panes)'` |
| List panes in a window | `tmux list-panes -t c:1 -F '#{pane_index} #{pane_id} #{pane_title} #{pane_current_command}'` |
| See pane content | `tmux capture-pane -t c:1.$N -p \| tail -5` |
| Move pane between windows | `tmux join-pane -d -s %ID -t %TARGET_ID` then `tmux select-layout -t c:WINDOW tiled` |
| Break pane to new window | `tmux break-pane -d -s %ID -n window-name` |
| Re-tile a window | `tmux select-layout -t c:1 tiled` |
| Rename pane | `tmux select-pane -t c:1.$N -T "name"` |
| Kill idle pane | `tmux kill-pane -t %ID` |
| Resume CC session | `tmux run-shell "unset CLAUDECODE && ~/bin/cc resume keywords"` |

## How `cc resume` works internally

1. Runs `session_search.py` to find matching JSONL by keyword (searches first 3 user messages)
2. Copies the JSONL to the correct project dir if needed
3. Tries `tmux split-window` in the **current window** — falls back to `tmux new-window` if no space
4. Sets pane title to the keyword, runs `select-layout tiled`
5. Does NOT switch Max's focus to the new pane

Key implication: when called via `tmux run-shell` from a Bash tool, "current window" is wherever tmux's server context is, not necessarily where Max is looking. This is why verification is essential.
