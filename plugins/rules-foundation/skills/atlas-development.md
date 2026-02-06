---
description: Use when developing atlas crawlers, converters, or working with legal document archiving
---

# Atlas Development

Atlas is RF's legal document archive: statutes, regulations, IRS guidance → R2 storage.

## Architecture

```
Official Sources → Crawlers → Converters → R2 (atlas bucket)
     ↓                           ↓
  HTML/XML              Akoma Ntoso XML
```

## Key Paths

| Component | Location |
|-----------|----------|
| Crawlers | `src/arch/crawl.py`, `src/arch/crawl_playwright.py` |
| Converters | `src/arch/converters/us_states/{state}.py` |
| R2 Storage | `src/arch/storage/r2.py` |
| Source specs | `src/arch/sources/specs/` |
| CLI | `src/arch/cli.py` |

## R2 Structure

```
atlas/
├── us/statutes/states/{state}/{title}/{section}.html
├── us/statutes/federal/{title}/{section}.xml
├── us/guidance/irs/{type}/{doc_id}.pdf
└── us/regulations/cfr/{title}/{part}.xml
```

Credentials: `~/.config/rulesfoundation/r2-credentials.json`

## Adding a New State Converter

1. **Create converter**: `src/arch/converters/us_states/{st}.py`
2. **Add section pattern**: In `crawl.py` `SECTION_PATTERNS` dict
3. **Test locally**: `uv run python -m arch.crawl us-{st} --max-sections 10 --dry-run`
4. **Upload**: Remove `--dry-run` to push to R2

### Converter Template

```python
"""Convert {State} statutes to Akoma Ntoso."""

from arch.converters.base import BaseConverter
from arch.models_akoma_ntoso import AkomaNtoso, Act, Body, Article, Section

class StateConverter(BaseConverter):
    """Convert {State} HTML to AKN."""

    def convert(self, html: str, url: str) -> AkomaNtoso:
        soup = BeautifulSoup(html, 'html.parser')
        # Extract title, chapter, section structure
        # Return AkomaNtoso object
```

## Common Crawl Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| DNS failure | Site down/blocking | Use Archive.org fallback if available |
| 403 Forbidden | Bot detection | Add delays, use Playwright crawler |
| Structure changed | Site redesign | Update section pattern regex |
| Timeout | Slow server | Increase timeout, add retries |

## Archive.org Fallback

8 states have bulk data on Archive.org (see `ARCHIVE_ORG_STATES` in crawl.py):
```bash
uv run python -m arch.crawl --archive us-ky us-ga us-nc
```

## CLI Commands

```bash
# Crawl
uv run python -m arch.crawl us-ca --max-sections 500
uv run python -m arch.crawl --all --dry-run

# Ingest to SQLite
arch ingest data/uscode/usc26.xml

# Query
arch get "26 USC 32"
arch search "earned income" --title 26
```

## Testing Converters

```bash
# Run converter tests
pytest tests/converters/ -v

# Test specific state
pytest tests/converters/test_ca.py -v
```

## Cross-Repo Flow

```
atlas (crawl/store) → rac-us (encode statutes) → PolicyEngine (validate)
```

When encoding needs a statute:
1. Check if it's in atlas R2
2. If not, crawl it first
3. Then encode with RAC
