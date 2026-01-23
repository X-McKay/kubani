# Cluster Health Check

## Overview

This SOP performs a comprehensive health check of the Kubernetes cluster. It collects events, pod status, and node metrics, uses AI analysis to identify issues, reports findings to Discord, and triggers remediation workflows for detected problems. The SOP is designed for the K8s Monitor syndicate and orchestrates the EventClassifierAgent and RemediatorAgent.

## Parameters

- **namespaces** (optional, default: all): List of namespaces to check, or "all" for cluster-wide
- **max_event_age** (optional, default: "1h"): Maximum age of events to consider
- **severity_threshold** (optional, default: "medium"): Minimum severity to report (low, medium, high, critical)
- **auto_remediate** (optional, default: true): Whether to automatically trigger remediation for detected issues
- **discord_channel** (optional, default: "kubani-k8s"): Discord channel for health reports

**Constraints for parameter acquisition:**
- You MUST use sensible defaults for unspecified parameters
- You MUST validate that namespaces exist before proceeding
- You MUST normalize severity_threshold to one of: low, medium, high, critical

## Mode Behavior

**Scheduled Mode (default):**
- Execute autonomously without user interaction
- Document all findings in the health report
- Auto-remediate issues based on the decision matrix
- Post summary to Discord upon completion

**Manual Mode:**
- Present findings and ask for confirmation before remediation
- Allow user to select which issues to remediate
- Provide detailed explanations of detected issues

## Steps

### 1. Collect Cluster Data

Gather comprehensive information from across the cluster using collection skills.

**Constraints:**
- You MUST invoke `k8s/collection/list-recent-events` to get cluster events
- You MUST invoke `k8s/collection/list-pods-in-namespace` for each target namespace
- You MUST invoke `k8s/diagnostic/check-node-resources` for node health
- You MUST collect events from the last `max_event_age` period
- You MUST capture pod status, restart counts, and resource usage
- You SHOULD collect deployment status for any failing pods
- You SHOULD gather node CPU and memory utilization metrics

**Data to collect:**
- Recent Warning and Error events
- Pods not in Running state
- Pods with high restart counts (>3)
- Node resource pressure indicators
- Failing deployments or ReplicaSets

### 2. Classify Events

Use the EventClassifierAgent to analyze and classify collected data.

**Constraints:**
- You MUST classify each issue by severity (critical, high, medium, low)
- You MUST categorize issues by type (resource, pod_health, node_health, network, storage)
- You MUST filter out benign patterns (DNSConfigForming, Killing, Preempting, etc.)
- You MUST deduplicate events within a correlation window
- You SHOULD correlate related events (e.g., OOMKilled followed by CrashLoopBackOff)
- You SHOULD use LLM classification for unknown patterns

**Severity classification:**
- **CRITICAL**: OOMKilled, NodeNotReady - immediate action required
- **HIGH**: CrashLoopBackOff, ImagePullBackOff, FailedScheduling - requires attention
- **MEDIUM**: Unhealthy probes, BackOff states - should be monitored
- **LOW**: Informational events - no action needed

**Overall health status:**
- HEALTHY: No issues found
- DEGRADED: Minor issues, no immediate action needed
- UNHEALTHY: Issues requiring attention
- CRITICAL: Immediate action required

### 3. Report to Discord

Post findings to the monitoring Discord channel.

**Constraints:**
- You MUST post a health report with the overall status
- You MUST include timestamp and namespace coverage
- You MUST list all detected issues with severity
- You SHOULD include an AI-generated summary of findings
- You SHOULD format the report for readability with markdown
- You MAY include trend information if historical data is available

**Report format:**
```
🏥 **Cluster Health Report**

Status: [HEALTHY|DEGRADED|UNHEALTHY|CRITICAL]
Time: [timestamp]
Namespaces: [list or "all"]

**Summary:**
[AI-generated summary of findings]

**Issues Found:**
- [🔴|🟠|🟡] [Issue description] - [namespace/resource]

**Actions Taken:**
- [Action 1]
- [Action 2]
```

### 4. Trigger Remediation

For each detected issue, trigger appropriate remediation using the RemediatorAgent.

**Constraints:**
- You MUST only remediate issues at or above `severity_threshold`
- You MUST skip remediation if `auto_remediate` is false
- You MUST use the decision matrix to select the appropriate skill
- You MUST record the outcome of each remediation attempt
- You MUST NOT remediate the same issue twice within 1 hour (cooldown)
- You SHOULD escalate to human if no matching skill is found

**Decision matrix:**

| Issue Type | Skill to Invoke | Approval Required |
|------------|-----------------|-------------------|
| CrashLoopBackOff | `k8s/remediation/restart-crashloop` | No |
| ImagePullBackOff | `k8s/remediation/restart-imagepullbackoff` | No |
| OOMKilled | `k8s/diagnostic/check-pod-resources` | No |
| Resource Pressure | `k8s/diagnostic/check-node-resources` | No |
| Unknown | Escalate to human | Yes |

**For each issue:**
1. Look up matching skill in decision matrix
2. Check cooldown period (skip if recently remediated)
3. Execute skill with issue context
4. Record outcome (success/failure)
5. Update Discord with result

### 5. Summary Report

Post final summary with all actions taken.

**Constraints:**
- You MUST include total issues found by severity
- You MUST include remediation statistics (attempted, succeeded, failed, escalated)
- You MUST include execution time
- You SHOULD include recommendations for persistent issues
- You MAY suggest configuration changes for recurring problems

## Success Criteria

- Data collection completed without errors
- Analysis produced valid health status
- Discord notification posted successfully
- All detected issues have remediation triggered or escalated
- No unhandled exceptions during execution

## Rollback Procedure

This SOP is primarily read-only analysis plus targeted remediation. Individual remediation skills have their own rollback procedures.

If remediation causes issues:
1. Check the specific skill's rollback procedure
2. If needed, manually revert changes via kubectl
3. Update skill confidence based on outcome
4. Report the failure in Discord

## Related SOPs

- [Incident Response](./incident-response.sop.md)
