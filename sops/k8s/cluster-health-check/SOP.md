---
name: cluster-health-check
description: >
  Perform a comprehensive cluster health check. Analyzes all namespaces
  for issues, reports findings to Discord, and triggers remediation
  for any detected problems.
metadata:
  domain: k8s
  category: runbook
  schedule: "0 * * * *"  # Every hour
  requires-approval: false
  timeout: 10m
  temporal-workflow: ClusterHealthCheckWorkflow
---

# Cluster Health Check

## Overview

This SOP performs a comprehensive health check of the Kubernetes cluster:
1. Collects events, pod status, and node metrics
2. Uses AI analysis to identify issues
3. Reports findings to Discord
4. Triggers remediation workflows for detected issues

## Triggers

Execute this SOP when:

- Scheduled: Every hour via Temporal
- Manual: On-demand health check request
- Alert: Prometheus alert for cluster issues

## Prerequisites

- [ ] kubeconfig is configured
- [ ] Metrics server is available
- [ ] Discord webhook is configured
- [ ] Temporal worker is running

## Steps

### Step 1: Collect Cluster Data

Gather information from across the cluster.

**Skills to invoke:**
- `k8s/collection/list-recent-events`
- `k8s/collection/list-pods-in-namespace` (for each namespace)
- `k8s/diagnostic/check-node-resources`

**Data to collect:**
- Recent events (last 1 hour)
- Pod status across all namespaces
- Node CPU and memory usage
- Any failing deployments

### Step 2: Analyze Findings

Use the Sentinel agent to analyze collected data.

**Analysis focus:**
- Pods not in Running state
- High restart counts (>3)
- Resource pressure on nodes
- Warning/Error events

**Severity classification:**
- HEALTHY: No issues found
- DEGRADED: Minor issues, no immediate action needed
- UNHEALTHY: Issues requiring attention
- CRITICAL: Immediate action required

### Step 3: Report to Discord

Post findings to the monitoring Discord channel.

**Report format:**
```
🏥 **Cluster Health Report**

Status: [HEALTHY|DEGRADED|UNHEALTHY|CRITICAL]
Time: [timestamp]

**Summary:**
[AI-generated summary of findings]

**Issues Found:**
- [Issue 1]
- [Issue 2]

**Actions Taken:**
- [Action 1]
- [Action 2]
```

### Step 4: Trigger Remediation

For each detected issue, trigger appropriate remediation.

**Decision matrix:**

| Issue Type | Skill to Invoke | Approval Required |
|------------|-----------------|-------------------|
| CrashLoopBackOff | `k8s/remediation/restart-crashloop` | No |
| ImagePullBackOff | `k8s/remediation/restart-imagepullbackoff` | No |
| Resource Pressure | `k8s/diagnostic/check-pod-resources` | No |
| Unknown | Escalate to human | Yes |

**For each issue:**
1. Look up matching skill
2. Execute skill with issue context
3. Record outcome
4. Update Discord with result

### Step 5: Summary Report

Post final summary with all actions taken.

**Include:**
- Number of issues found
- Number of issues resolved
- Number of issues escalated
- Time taken

## Success Criteria

- [ ] Data collection completed without errors
- [ ] Analysis produced valid health status
- [ ] Discord notification posted successfully
- [ ] All detected issues have remediation triggered or escalated

## Rollback Procedure

This SOP is read-only analysis plus targeted remediation.
Individual remediation skills have their own rollback procedures.

If remediation causes issues:
1. Check the remediation skill's rollback procedure
2. If needed, manually revert changes via kubectl
3. Update skill confidence based on outcome

## Notifications

- **On start**: Log workflow start (no Discord notification)
- **On success**: Post health report to Discord (via Sentinel agent)
- **On failure**: Post error message to Discord, log details

## Related SOPs

- [Incident Response](../incident-response/)
- [Node Maintenance](../node-maintenance/)
