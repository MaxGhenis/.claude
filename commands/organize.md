---
description: Organize tmux CC sessions into windows by similar content
allowed-tools: Bash, Read
arguments:
  - name: width
    description: Grid width (2 for 2x2=4 panes/window, 3 for 3x3=9, default 3)
    required: false
---

# Organize tmux panes into themed windows

**Width: $ARGUMENTS** (default 3 → max 9 panes/window; 2 → max 4 panes/window)

## Step 1: Read all panes

Capture content from every pane across all windows. For each pane, capture the last 30 lines of scrollback:

```bash
for pid in $(tmux list-panes -a -F '#{pane_id}'); do
  win=$(tmux display -t "$pid" -p '#{window_name}')
  idx=$(tmux display -t "$pid" -p '#{pane_index}')
  cmd=$(tmux display -t "$pid" -p '#{pane_current_command}')
  echo "═══ $win:$idx ($pid) [$cmd] ═══"
  tmux capture-pane -t "$pid" -p -S -30
  echo ""
done
```

## Step 2: Classify each pane

Based on the content you just read, assign each pane to a short group name. Use names like:
- `pe-us`, `pe-uk`, `pe-app`, `pe-api`, `pe-core`, `pe-data`, `pe-web` (PolicyEngine repos)
- `rf` (Rules Foundation, Atlas, RAC)
- `cosilico` (Cosilico, microplex)
- `teamverse` (CRM)
- `personal` (dating, health, personal life)
- `tools` (Claude Code tooling, tmux, skills, plugins)
- `comms` (email, slack, messaging)
- `grants` (grant applications)
- Or invent a fitting short name.

Skip the `meta` window — it stays as window 0.
Skip truly empty shell panes (no CC history in scrollback at all).

## Step 3: Apply with helper script

Write a JSON file mapping pane IDs to target window names, then run the helper:

```bash
cat > /tmp/organize-plan.json << 'EOF'
{"%123": "pe-us", "%456": "rf", ...}
EOF
python3 ~/tmux-claude-code/scripts/organize.py --apply /tmp/organize-plan.json --max-panes WIDTH_SQUARED
```

## Constraints

- **Max 9 non-meta windows** (so prefix+0 through prefix+9 all work, with meta=0)
- **Max panes per window = width²** (2→4, 3→9, 4→16). Parse the width from $ARGUMENTS (default 3 if empty/missing).
- If you have more than 9 groups, merge the smallest related groups together
- After moves, the script auto-cleans empty windows and renumbers 0-N with meta at 0
- Show the user the plan (which panes go where) before applying

## Step 4: Verify

After the helper script finishes, ALWAYS verify the result by capturing the last 5 lines from every pane and confirming each pane is in the right window. This is non-negotiable — never skip verification.

```bash
for pid in $(tmux list-panes -a -F '#{pane_id}'); do
  win=$(tmux display -t "$pid" -p '#{window_name}')
  idx=$(tmux display -t "$pid" -p '#{pane_index}')
  echo "--- $win:$idx ($pid) ---"
  tmux capture-pane -t "$pid" -p -S -5 | tail -5
done
```
