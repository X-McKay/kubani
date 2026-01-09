---
name: incident-response
description: >
  Respond to a detected Kubernetes incident. Investigates the issue,
  attempts automated remediation, and escalates if needed.
metadata:
  domain: k8s
  category: incident-response
  requires-approval: false
  timeout: 15m
  temporal-workflow: IssueRemediationWorkflow
---

# Incident Response

## Overview

This SOP handles detected Kubernetes incidents:
1. Acknowledges the incident
2. Investigates root cause
3. Attempts remediation using matching skills
4. Verifies resolution
5. Escalates if automated remediation fails

## Triggers

Execute this SOP when:

- Event: `K8S_ISSUE_DETECTED` event published
- Child workflow from cluster health check
- Manual: Incident reported by human

## Prerequisites

- [ ] Issue context provided (pod, namespace, reason)
- [ ] Skill library available
- [ ] Temporal worker running

## Steps

### Step 1: Acknowledge Incident

Log receipt of incident and notify.

**Actions:**
- Log incident details
- Publish `K8S_REMEDIATION_STARTED` event
- (Optional) Notify Discord if severity is high

**Context to capture:**
- Pod name
- Namespace
- Issue reason
- Message
- Original event timestamp

### Step 2: Investigate

Use diagnostic skills to understand the issue.

**Skills to invoke:**
- `k8s/diagnostic/investigate-pod-failure`

**Gather:**
- Pod logs (current and previous container)
- Recent events for the pod
- Pod spec and status
- Related deployment status

### Step 3: Match Skill

Find the best remediation skill for this issue.

**Search process:**
1. Check for exact skill ID match in event
2. Semantic search in unified library (markdown skills)
3. Fall back to legacy Qdrant search
4. If no match: escalate

**Skill selection criteria:**
- Domain: k8s
- Category: remediation
- Minimum confidence: 0.5
- Preconditions match issue context

### Step 4: Request Approval (if required)

For high-risk actions, request human approval.

**Skills requiring approval:**
- `k8s/remediation/scale-deployment`
- Any skill with `requires-approval: true`

**Approval flow:**
1. Post request to Discord with action details
2. Wait for reaction (✅ approve, ❌ deny)
3. Timeout after 5 minutes → deny
4. Log approval decision

### Step 5: Execute Remediation

Run the matched skill.

**For markdown skills:**
1. Load skill body
2. Create execution context with pod details
3. Use LLM executor to follow skill instructions
4. Call MCP tools as directed by skill

**For legacy Python skills:**
1. Resolve parameter templates
2. Execute each action in order
3. Call MCP tools directly

### Step 6: Verify Resolution

Check if the issue is actually fixed.

**Verification methods:**
1. LLM critic (Voyager pattern): Evaluate success criteria
2. Rule-based fallback: Check pod status

**Success criteria examples:**
- Pod is now Running
- No CrashLoopBackOff within 5 minutes
- Restart count stable

### Step 7: Record Outcome

Update skill confidence and publish results.

**On success:**
- Increment skill success count
- Update confidence score
- Publish `K8S_REMEDIATION_COMPLETED` event

**On failure:**
- Increment skill failure count
- Update confidence score
- Publish `K8S_REMEDIATION_FAILED` event
- Escalate if not already escalated

## Success Criteria

- [ ] Incident acknowledged and logged
- [ ] Investigation completed
- [ ] Remediation attempted OR escalated
- [ ] Outcome recorded

## Rollback Procedure

If remediation makes things worse:

1. Check skill's rollback_actions (if defined)
2. For pod restart skills: No rollback needed (self-healing)
3. For scale changes: Revert to original replica count
4. For other changes: Follow skill-specific rollback

## Notifications

- **On start**: Log only (parent already notified Discord)
- **On success**: Update Discord thread with resolution
- **On failure**: Post failure and escalate

## Related SOPs

- [Cluster Health Check](../cluster-health-check/)
- [Escalation Procedure](../escalation/)
