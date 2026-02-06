---
description: "Validate encoded policy against multiple tax/benefit systems"
argument-hint: "<citation or path> (e.g., '26 USC 32', 'rac-us/statute/26/32/tests.yaml')"
---

# Validate Policy Command

Validate encoded policies against PolicyEngine and TAXSIM.

## Arguments
- `$ARGUMENTS` - Citation or path to test cases

## Workflow

### 1. Run validation

```bash
cd ~/RulesFoundation/rac-validators
source .venv/bin/activate

python -c "
from rac_validators.cps.runner import CPSValidationRunner
runner = CPSValidationRunner(year=2024)
results = runner.run()
for name, result in results.items():
    if result.pe_comparison:
        print(f'{name}: {result.pe_comparison.match_rate:.1%} match')
"
```

### 2. Interpret results

**Consensus Levels:**
- `FULL_AGREEMENT` - All validators agree (best case)
- `MAJORITY_AGREEMENT` - >50% agree
- `DISAGREEMENT` - No consensus (investigate)
- `POTENTIAL_UPSTREAM_BUG` - High confidence but validators disagree

### 3. Report findings

Summarize:
- Total tests run
- Pass/fail rate
- Consensus levels achieved
- Potential upstream bugs detected
- Recommended actions
