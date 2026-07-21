---
description: Clean up tmux panes - kill idle shells, fix layout
allowed-tools: Bash
---

# Kill empty tmux panes

Find and kill all panes running an idle shell (zsh/bash) across all windows except meta (window 0/meta is the control plane).

```bash
cc clean
```

After cleaning, re-tile affected windows:

```bash
for win in $(tmux list-windows -t c -F '#{window_index}'); do
  tmux select-layout -t "c:$win" tiled 2>/dev/null
done
```

Report how many panes were killed.
