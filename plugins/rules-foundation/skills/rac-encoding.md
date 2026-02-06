---
description: Use when encoding tax/benefit statutes into RAC format, creating test cases for policy rules, or understanding the encoding pipeline
---

# RAC Encoding Patterns

RAC (Rules as Code) is RF's DSL for encoding statutes into executable code.

## Filepath = Citation

The most important rule. The filepath IS the legal citation:

```
statute/26/32/c/3/D/i.rac  =  26 USC 32(c)(3)(D)(i)
statute/26/121/a.rac        =  26 USC 121(a)
```

One subsection per file. Never mix content from adjacent subsections.

## Repository Map

| Repo | Purpose | Encodings? |
|------|---------|------------|
| `rac` | DSL parser/executor | No |
| `rac-us` | US federal statute encodings | **Yes** |
| `rac-us-ca`, `rac-us-ny` | State encodings | **Yes** |
| `rac-ca` | Canada encodings | **Yes** |
| `autorac` | AI encoding automation | No |
| `atlas` | Source document archive | No |

## RAC File Structure

```yaml
# statute/26/1411/a.rac
# 26 USC 1411(a) - General Rule

text: """
(a) General rule.-- Except as provided in this section...
"""

parameter niit_rate:
  description: "Tax rate on net investment income"
  unit: rate
  values:
    2013-01-01: 0.038

variable net_investment_income_tax:
  imports:
    - 26/1411/c#net_investment_income
    - 26/1411/b#threshold_amount
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: |
    excess_magi = max(0, modified_adjusted_gross_income - threshold_amount)
    return niit_rate * min(net_investment_income, excess_magi)
  tests:
    - name: "MAGI below threshold"
      period: 2024-01
      inputs:
        net_investment_income: 50_000
        modified_adjusted_gross_income: 180_000
        threshold_amount: 200_000
      expect: 0
```

## Critical Rules

1. **Never use `syntax: python`** - native DSL only
2. **Never hardcode brackets** - use `marginal_agg()` for tax brackets
3. **Never hardcode dollar amounts** - all values go in parameters with effective dates
4. **Always fetch statute text first** - from atlas or Cornell LII
5. **Every variable needs tests** - basic case, edge cases, zero case

## Validation

All encodings validate against PolicyEngine and TAXSIM on full CPS microdata:
```bash
# In rac-validators
python -c "
from rac_validators.cps.runner import CPSValidationRunner
runner = CPSValidationRunner(year=2024)
results = runner.run()
"
```

Target: >99% match rate. Never validate with just hand-crafted tests.

## Phase-In/Phase-Out Credits

For credits with phase-in and phase-out (EITC, CTC):
- Phase-in rate = max_credit / earned_income_threshold
- These are usually DIFFERENT rates (e.g., EITC 1 child: 34% in, 15.98% out)
- Always verify reference points: credit = max at phase-in threshold, credit = 0 at phase-out end

## Completion Checklist

- [ ] File path matches statute subsection number
- [ ] `text:` quotes the EXACT subsection
- [ ] No hardcoded dollar amounts (use parameters)
- [ ] Parent file imports new child variables
- [ ] Every import resolves to existing definition
- [ ] No circular references
- [ ] Tests cover basic, edge, and zero cases
- [ ] CPS validation >99% match
