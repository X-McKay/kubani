---
name: sop-name-here
description: >
  Clear description of this Standard Operating Procedure.
  SOPs are multi-step procedures that may invoke multiple skills.
metadata:
  domain: k8s  # k8s | news | general
  category: runbook  # runbook | incident-response | maintenance
  schedule: "0 * * * *"  # Optional: cron schedule for periodic execution
  requires-approval: false
  timeout: 30m
---

# SOP Display Name

## Overview

Brief description of what this SOP accomplishes.

## Triggers

When to execute this SOP:

- Trigger 1
- Trigger 2

## Prerequisites

- [ ] Prerequisite 1
- [ ] Prerequisite 2

## Steps

### Step 1: First Step

Description of what this step does.

**Skills to invoke:**
- `k8s/collection/list-recent-events`

**Context to gather:**
- Item 1
- Item 2

### Step 2: Second Step

Description of what this step does.

**Skills to invoke:**
- `k8s/diagnostic/investigate-pod-failure`

**Decision point:**
- If condition A: proceed to Step 3
- If condition B: skip to Step 4

### Step 3: Third Step

...

## Success Criteria

- [ ] Criterion 1
- [ ] Criterion 2

## Rollback Procedure

If the SOP fails:

1. Rollback step 1
2. Rollback step 2

## Notifications

- **On start**: Notify channel X
- **On success**: Post summary to Discord
- **On failure**: Page on-call via PagerDuty

## Related SOPs

- [Related SOP 1](../related-sop-1/)
- [Related SOP 2](../related-sop-2/)
