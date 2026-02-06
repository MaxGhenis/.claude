---
description: Use when working on Rules Foundation repos to understand architecture, repo layout, and cross-repo relationships
---

# Rules Foundation

Open infrastructure for encoded law. 501(c)(3) nonprofit.

## Repos (all at ~/RulesFoundation/)

| Repo | Purpose |
|------|---------|
| **atlas** | Legal document archive (statutes, regulations, IRS guidance) → R2 |
| **rac** | Rules as Code DSL parser/executor |
| **rac-us** | US federal statute encodings |
| **rac-us-ca**, **rac-us-ny**, **rac-us-tx** | State encodings |
| **rac-ca** | Canada encodings |
| **rac-validators** | PE/TAXSIM validation infrastructure |
| **rac-compile**, **rac-syntax** | Tooling |
| **autorac** | AI-powered encoding automation (Agent SDK) |
| **rules.foundation** | Website |

## Pipeline

```
atlas (crawl/store) → rac-us (encode) → rac-validators (validate) → autorac (automate)
```

## Infrastructure

- **R2 Bucket**: `atlas` (Cloudflare R2) for legal documents
- **Credentials**: `~/.config/rulesfoundation/r2-credentials.json`
- **Supabase**: arch.rules table (1.2M+ parsed statutes)

## Style

- Sentence case for headings
- Say "tools" and "open-source software", not "APIs"
