---
description: "Encode a statute into RAC format with full multi-agent workflow"
argument-hint: "<citation> (e.g., '26 USC 1', '26 USC 32(c)(2)(A)')"
---

# Encode Statute

Dispatches the Encoding Orchestrator agent to run the full multi-agent workflow.

## Usage

```
/encode 26 USC 1
/encode 26 USC 32
/encode 7 USC 2017(a)
```

## What Happens

The Encoding Orchestrator agent is spawned and runs:

1. **Analysis** - Statute Analyzer agent (predictions)
2. **Encoding** - RAC Encoder agent (writes files, fixes errors)
3. **Oracles** - Encoding Validator agent (PE/TAXSIM comparison)
4. **Review** - 4 Reviewer agents in parallel (RAC, Formula, Param, Integration)
5. **Logging** - Records to autorac experiment DB
6. **Report** - Calibration comparison (predicted vs actual)

## Invoke

```
Task(
  subagent_type="rules-foundation:Encoding Orchestrator",
  prompt="Encode $ARGUMENTS",
  model="opus"
)
```
