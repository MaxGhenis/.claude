---
description: Check GitHub PRs - review requests, your open PRs, CI status
args: "[repo]"
---

# GitHub PR Dashboard

Check PRs across PolicyEngine repositories. If a specific repo is provided, focus on that one.

## Key Repos to Check

- PolicyEngine/policyengine-us
- PolicyEngine/policyengine-uk
- PolicyEngine/policyengine-app-v2
- PolicyEngine/policyengine-api
- PolicyEngine/policyengine-core
- PolicyEngine/policyengine.py
- PolicyEngine/policyengine-us-data
- CosilicoAI/cosilico-api
- CosilicoAI/rules-us

## 1. PRs Needing Your Review

```bash
for repo in PolicyEngine/policyengine-us PolicyEngine/policyengine-uk PolicyEngine/policyengine-app-v2 PolicyEngine/policyengine-api PolicyEngine/policyengine-core CosilicoAI/cosilico-api CosilicoAI/rules-us; do
  gh pr list --search "is:open review-requested:@me" --limit 10 --json repository,number,title,author,updatedAt --repo "$repo" 2>/dev/null
done
```

## 2. Your Open PRs

```bash
for repo in PolicyEngine/policyengine-us PolicyEngine/policyengine-uk PolicyEngine/policyengine-app-v2 PolicyEngine/policyengine-api CosilicoAI/cosilico-api CosilicoAI/rules-us; do
  gh pr list --search "is:open author:@me" --limit 10 --json repository,number,title,statusCheckRollup,updatedAt --repo "$repo" 2>/dev/null
done
```

## 3. If Specific Repo Requested

If $ARGUMENTS contains a repo name, focus on that:
```bash
gh pr list --search "is:open" --limit 20 --json number,title,author,statusCheckRollup,updatedAt --repo PolicyEngine/$ARGUMENTS
```

## Output Format

```
## PRs Dashboard

### Awaiting Your Review (X)
| Repo | PR | Title | Author |
|------|-----|-------|--------|

### Your Open PRs (X)
| Repo | PR | Title | CI Status |
|------|-----|-------|-----------|
| policyengine-us | #123 | Title | ✅/❌/⏳ |

### Action Needed
- [any PRs with failing CI or stale reviews]
```
