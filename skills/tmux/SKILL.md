---
name: tmux
description: Use when interacting with tmux — sending commands to panes, creating panes, resuming sessions, checking pane status, or any tmux operation. Triggers on "tmux", "pane", "resume session in tmux", "new pane", "send to pane", "grid", "split".
---

# tmux skill

Max runs Claude Code sessions in tmux. This skill ensures safe, correct tmux operations.

## Max's setup

- **Session**: `c` with window `claude` (index 1), typically 8 panes
- **Pane numbering**: starts at 1 (`pane-base-index 1`)
- **Config**: `~/dotfiles/.tmux.conf`
- **Helper**: `~/bin/cc [name]` — creates a new pane with Claude Code
- **Keybindings**: `prefix-c` new Claude pane, `prefix-g` tile grid, `prefix-r` reload config

## Safety rules

### NEVER send keys to an occupied pane

Before sending any command to a pane, check what's running:

```bash
tmux list-panes -t c:1 -F '#{pane_index} #{pane_current_command}'
```

- Only send to panes where command is `zsh` or `bash` (idle shell)
- Claude Code shows as `node` or a version like `2.1.50` — these are OCCUPIED
- **Blank visible output does NOT mean empty** — Claude Code's TUI can show blank areas
- If no pane is free, **create a new one** instead

### Creating a new pane

```bash
# Simple: new pane running a command
tmux split-window -t c:1 "command here"

# With name (using the cc helper):
~/bin/cc session-name

# Manual with name:
pane=$(tmux split-window -c ~ -P -F '#{pane_index}')
tmux send-keys -t "$pane" "claude --resume SESSION_ID" Enter
tmux select-pane -t "$pane" -T "name"
tmux select-layout tiled
```

### Sending keys to a verified-free pane

```bash
# First verify it's free:
tmux list-panes -t c:1 -F '#{pane_index} #{pane_current_command}' | grep -E '(zsh|bash)$'

# Then send:
tmux send-keys -t c:1.$PANE "command" Enter
```

## Common operations

| Task | Command |
|------|---------|
| List sessions | `tmux list-sessions` |
| List panes with status | `tmux list-panes -t c:1 -F '#{pane_index} #{pane_title} #{pane_current_command}'` |
| See pane content | `tmux capture-pane -t c:1.$N -p \| tail -5` |
| Resume CC session | `claude --resume SESSION_ID` |
| Re-tile grid | `tmux select-layout -t c:1 tiled` |
| Rename pane | `tmux select-pane -t c:1.$N -T "name"` |
| New named CC pane | `~/bin/cc name` |
