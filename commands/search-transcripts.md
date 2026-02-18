---
description: Search Claude Code conversation transcripts by keyword
allowed-tools: Bash
---

# Search Claude Code transcripts

Search query: $ARGUMENTS

Run this command and share the results with the user:

```bash
claude-search -n $ARGUMENTS
```

If the user wants to dig into a specific session, read the JSONL file at `~/.claude/projects/*/SESSION_ID.jsonl` and extract the relevant conversation.
