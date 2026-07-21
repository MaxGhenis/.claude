---
description: Audit MEMORY.md and CLAUDE.md, move detailed reference into skills
---

# Config tidy

Audit the configuration layers and move misplaced content into the right layer.

## The layers

| Layer | File | Purpose | Loaded |
|-------|------|---------|--------|
| **Instructions** | `~/.claude/CLAUDE.md` | Behavioral rules (always/never do X) | Every session |
| **Memory** | `~/.claude/projects/-Users-maxghenis/memory/MEMORY.md` | Compact fact index (1-2 lines per topic) | Every session (first 200 lines) |
| **Memory files** | `~/.claude/projects/-Users-maxghenis/memory/*.md` | Detailed facts linked from MEMORY.md | When accessed |
| **Skills** | `~/.claude/skills/max-productivity/skills/*/SKILL.md` | Reference material with trigger-based loading | On-demand by keyword |

## Critical distinction: behavioral rules vs reference material

**Behavioral rules** (always/never do X) MUST stay in always-loaded context (CLAUDE.md or MEMORY.md). They cannot be skills because:
- Skills only load when triggered by user prompts
- Behavioral rules need to be active BEFORE the situation arises
- No user prompt reliably triggers "don't delete code before pushing" — you just need to know it

**Reference material** (how to use an API, step-by-step guides, lookup tables) should be skills because:
- They're only needed in specific contexts
- Trigger keywords are predictable ("slack", "email", "deploy")
- They're too large for always-loaded context

**Test**: "Would I need this even if the user doesn't mention the topic?" → behavioral rule (stays in MEMORY.md). "Would I only need this when working with X?" → skill.

## Procedure

1. **Read all layers** — CLAUDE.md, MEMORY.md, list all skills, list all memory/*.md files
2. **Report line counts** and flag if MEMORY.md > 100 lines
3. **Check for orphans** — memory files not linked from MEMORY.md, skills with duplicate content
4. **Identify misplaced content:**
   - MEMORY.md entries >3 lines → compress or link to a memory file
   - Reference material in MEMORY.md that has a matching skill → remove from MEMORY.md
   - Behavioral rules that were moved to skills → move back to MEMORY.md
   - Duplicates between any layers → keep in one place only
   - Stale/outdated entries
5. **Present findings** with specific recommendations
6. **After user approval**, execute the moves

## Skill file format

New skills go in `~/.claude/skills/max-productivity/skills/{skill-name}/SKILL.md` (the max-productivity plugin auto-loads from `~/.claude/skills/` as `max-productivity@skills-dir`):

```markdown
---
name: Descriptive name
description: "Use this skill when [context]. Triggers: \"keyword1\", \"keyword2\"."
version: 0.1.0
---

# Title

Content here...
```

**Always quote the `description` value.** An unquoted description containing a colon-space (e.g. `Triggers: "foo"`) is invalid YAML — the skill then loads with empty metadata and never triggers. Verify with `claude plugin validate ~/.claude/skills/max-productivity` after adding skills.

## Targets

- MEMORY.md under 100 lines
- CLAUDE.md under 70 lines
- Every MEMORY.md entry is 1-2 lines — if it needs more, link to a memory file or skill
- No orphaned memory files
- No duplicate content across layers
