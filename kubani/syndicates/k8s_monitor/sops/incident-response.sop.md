# Incident Response

## Overview

This SOP handles detected Kubernetes incidents. It acknowledges the incident, investigates root cause using diagnostic skills, attempts automated remediation using matching skills, verifies resolution, and escalates if automated remediation fails. The SOP is designed for the K8s Monitor syndicate and orchestrates the EventClassifierAgent and RemediatorAgent.

## Parameters

- **pod_name** (required): Name of the affected pod
- **namespace** (required): Kubernetes namespace of the pod
- **issue_reason** (required): Reason code from the event (e.g., CrashLoopBackOff, OOMKilled)
- **message** (optional): Additional context from the event
- **severity** (optional, default: "medium"): Incident severity (low, medium, high, critical)
- **skip_approval** (optional, default: false): Bypass approval for skills that require it
- **discord_channel** (optional, default: "kubani-k8s"): Discord channel for notifications

**Constraints for parameter acquisition:**
- You MUST have pod_name, namespace, and issue_reason before proceeding
- You MUST validate the namespace exists in the cluster
- You MUST normalize severity to one of: low, medium, high, critical

## Mode Behavior

**Scheduled Mode (default):**
- Execute autonomously without user interaction
- Request approval via Discord for high-risk actions (unless skip_approval is true)
- Document all actions in the incident timeline
- Post resolution summary to Discord upon completion

**Manual Mode:**
- Present investigation findings before remediation
- Allow user to select which remediation skill to use
- Provide detailed explanations of each step

## Steps

### 1. Acknowledge Incident

Log receipt of incident and notify relevant channels.

**Constraints:**
- You MUST log incident details including timestamp, pod, namespace, and reason
- You MUST publish a `K8S_REMEDIATION_STARTED` event to Temporal
- You MUST notify Discord if severity is high or critical
- You SHOULD capture the original event timestamp for timeline tracking

**Context to capture:**
- Pod name
- Namespace
- Issue reason
- Message
- Original event timestamp
- Severity level

### 2. Investigate Root Cause

Use diagnostic skills to understand the issue before attempting remediation.

**Constraints:**
- You MUST invoke `k8s/diagnostic/investigate-pod-failure` skill
- You MUST gather pod logs (current container)
- You MUST gather previous container logs if restart count > 0
- You MUST collect recent events for the pod (last 1 hour)
- You SHOULD collect the pod spec and current status
- You SHOULD check related deployment/replicaset status
- You MAY correlate with node-level metrics if resource-related

**Investigation output:**
- Root cause hypothesis
- Supporting evidence from logs/events
- Recommended remediation approach

### 3. Match Remediation Skill

Find the best remediation skill for this issue.

**Constraints:**
- You MUST first check for exact skill ID if provided in the event context
- You MUST perform semantic search in the unified skill library
- You MUST filter results by domain=k8s and category=remediation
- You MUST require minimum confidence of 0.5 for skill selection
- You MUST verify skill preconditions match the issue context
- You MUST escalate to human if no matching skill found
- You SHOULD prefer skills with higher success rates

**Skill selection criteria:**
- Domain: k8s
- Category: remediation
- Minimum confidence: 0.5
- Preconditions match issue context

### 4. Request Approval (if required)

For high-risk actions, request human approval via Discord.

**Constraints:**
- You MUST check if skill has `requires-approval: true` in metadata
- You MUST request approval for these specific skills:
  - `k8s/remediation/scale-deployment`
  - `k8s/remediation/rollback-deployment`
  - Any skill with `requires-approval: true`
- You MUST skip approval if `skip_approval` parameter is true
- You MUST post approval request to Discord with full action details
- You MUST wait for reaction (✅ approve, ❌ deny) with 5-minute timeout
- You MUST treat timeout as denial
- You MUST log the approval decision with approver information

**Approval message format:**
```
🔐 **Remediation Approval Required**

Issue: [issue_reason] in [namespace]/[pod_name]
Proposed Action: [skill_name]
Description: [skill_description]

React with ✅ to approve or ❌ to deny.
```

### 5. Execute Remediation

Run the matched skill with appropriate context.

**Constraints:**
- You MUST NOT execute if approval was required but denied
- You MUST create execution context with all pod details
- You MUST load the skill body and follow its instructions
- You MUST call MCP tools as directed by the skill
- You MUST capture execution trace for learning system
- You MUST enforce skill timeout (default 5 minutes)
- You SHOULD log each action taken during execution

**Execution context:**
```json
{
  "pod_name": "<pod_name>",
  "namespace": "<namespace>",
  "issue_reason": "<issue_reason>",
  "message": "<message>",
  "investigation_results": "<from step 2>"
}
```

### 6. Verify Resolution

Check if the issue is actually fixed using the Critic Agent pattern.

**Constraints:**
- You MUST verify resolution within 2 minutes of remediation completion
- You MUST use LLM critic (Voyager pattern) as primary verification
- You MUST fall back to rule-based verification if LLM unavailable
- You MUST check that the original issue is no longer present
- You SHOULD monitor for issue recurrence for 5 minutes
- You MAY extend monitoring for critical issues

**Rule-based verification criteria:**
- Pod status is Running
- No CrashLoopBackOff within 5 minutes
- Restart count stable (not increasing)
- No new Warning events for this pod

### 7. Record Outcome

Update skill confidence and publish results to the learning system.

**Constraints:**
- You MUST update skill success/failure count
- You MUST recalculate skill confidence score
- You MUST publish outcome event to Temporal:
  - On success: `K8S_REMEDIATION_COMPLETED`
  - On failure: `K8S_REMEDIATION_FAILED`
- You MUST store execution trace in learning system
- You MUST escalate if remediation failed and not already escalated
- You SHOULD update Discord thread with resolution summary

**On success:**
- Increment skill success count
- Update confidence score: `new_confidence = (successes / total) * 0.9 + base_confidence * 0.1`
- Close incident

**On failure:**
- Increment skill failure count
- Update confidence score
- Create escalation ticket
- Notify on-call if severity is critical

## Success Criteria

- Incident acknowledged and logged with full context
- Investigation completed with root cause identified
- Remediation skill matched OR escalation created
- Remediation executed (if approved) OR denial logged
- Resolution verified OR failure recorded
- Outcome recorded in learning system
- Discord notifications sent appropriately

## Rollback Procedure

If remediation makes things worse:

1. Check skill's rollback_actions (if defined)
2. For pod restart skills: No rollback needed (pods self-heal)
3. For scale changes: Revert to original replica count
4. For rollback-deployment: Rollback again to previous-previous version
5. For other changes: Follow skill-specific rollback procedure

**Emergency rollback:**
- Use `kubectl rollout undo` for deployment changes
- Use `kubectl delete pod` to force pod recreation
- Document all manual interventions for post-incident review

## Related SOPs

- [Cluster Health Check](./cluster-health-check.sop.md)
