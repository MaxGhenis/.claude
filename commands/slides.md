---
description: Create presentation slides from a brief or topic. Uses Next.js + Tailwind slide framework.
args: "<brief file or topic description>"
---

# Presentation slides

Create slides using Max's Next.js slide framework. The canonical template is `~/nextladder-2026-slides/`.

## Framework

- **Stack**: Next.js 14 + React 18 + Tailwind CSS + D3 (for data viz)
- **Structure**: Each slideshow lives in `slideshows/{name}/` with slide components
- **Dev**: `bun run dev` to preview, Playwright for screenshot tests

## Creating a new slideshow

### 1. Copy the template

Start from an existing slideshow in `~/nextladder-2026-slides/` or another recent slides repo (check `~/arnold-2026-slides/`, `~/talk-georgetown-*`).

```bash
# List existing slideshows for reference
ls ~/nextladder-2026-slides/slideshows/
ls ~/arnold-2026-slides/slideshows/ 2>/dev/null
```

### 2. If starting from a brief

Read the brief file provided as $ARGUMENTS. Extract:
- Key messages (3-5 main points)
- Data points that need visualization
- Audience context
- Time constraints

### 3. Slide structure

Each slide is a React component. Common patterns:
- **Title slide**: Event name, date, speaker, logo
- **Section headers**: Bold statement + supporting context
- **Data slides**: D3 or Plotly charts with clear takeaways
- **Quote slides**: Key statistic or quote, large text
- **Closing slide**: Call to action, contact info

### 4. Design principles

- **Dark backgrounds** with light text (professional, projector-friendly)
- **One idea per slide** — no walls of text
- **Large font sizes** — minimum 24px for body, 48px+ for headlines
- **PolicyEngine brand**: Use teal #319795 as accent color when relevant
- **Data-forward**: Lead with numbers, not paragraphs

### 5. Testing

```bash
cd ~/[slides-repo] && bun run test
```

Playwright tests capture screenshots of each slide for visual review.

## Existing repos for reference

| Repo | Event | Date |
|------|-------|------|
| `~/nextladder-2026-slides` | NextLadder presentation | 2026 |
| `~/arnold-2026-slides` | Arnold Foundation | 2026 |
| `~/talk-georgetown-ppol6362-2026-01-12` | Georgetown lecture | Jan 2026 |
| `~/policyengine-uk-event-2025` | UK event | 2025 |
