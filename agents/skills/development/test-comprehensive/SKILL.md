```yaml
---
name: test-comprehensive
version: "1.0.0"
description: >
  Generate a Kubernetes cluster health report with pod status, node metrics, and resource utilization

metadata:
  domain: k8s
  category: remediation
  requires-approval: false

dependencies:
  mcp-servers:
    - kubernetes-mcp-server
allowed-tools: "Bash, mcp__kubernetes-mcp-server__pods_get, mcp__kubernetes-mcp-server__pods_list, mcp__kubernetes-mcp-server__pods_log, mcp__kubernetes-mcp-server__resources_get, mcp__kubernetes-mcp-server__resources_list"
---
```

# Kubernetes Cluster Health Report Generator

## When to Use
- Monitoring Kubernetes cluster health
- Troubleshooting pod/node failures
- Generating resource utilization reports
- Pre-deployment cluster validation
- Post-upgrade verification

## Prerequisites
- Kubernetes cluster access via MCP server
- Valid user permissions for pod/node metrics
- Running `kubernetes-mcp-server` instance
- Cluster must be in stable state (no ongoing evictions)

## Input Schema
```json
{
  "inputs": {}
}
```

## Actions
### 1. First Action
Use `mcp__kubernetes-mcp-server__pods_list` to retrieve all pod statuses and `mcp__kubernetes-mcp-server__resources_list` to gather node metrics.

### 2. Second Action
Query resource utilization data using `mcp__kubernetes-mcp-server__resources_get` for detailed CPU/memory metrics.

### 3. Third Action
Validate pod logs with `mcp__kubernetes-mcp-server__pods_log` if any pods show critical status.

## Output Schema
```json
{
  "cluster_status": "healthy|unhealthy|degraded",
  "pod_status": {
    "running": 0,
    "pending": 0,
    "failed": 0,
    "succeeded": 0
  },
  "node_metrics": {
    "cpu_usage_percent": 0.0,
    "memory_usage_percent": 0.0,
    "average_latency_ms": 0.0
  },
  "resource_utilization": {
    "total_cpu_cores": 0,
    "used_cpu_cores": 0,
    "total_memory_gb": 0,
    "used_memory_gb": 0
  },
  "timestamp": "ISO8601"
}
```

## Success Criteria
- ✅ Report contains all required metrics
- ✅ No critical errors in pod/node status
- ✅ Resource utilization within normal thresholds
- ✅ Output format matches schema exactly
- ✅ Timestamp within 5 minutes of generation

## Failure Handling
| Error Type                | Handling Strategy                          |
|--------------------------|--------------------------------------------|
| API timeout              | Retry with exponential backoff            |
| MCP server failure       | Switch to backup MCP endpoint             |
| Permission denied        | Request elevated permissions              |
| Invalid cluster state    | Return degraded status with error details |
| Missing metrics          | Mark as "N/A" in report                   |

## Examples
### Input Example
```json
{}
```

### Output Example
```json
{
  "cluster_status": "healthy",
  "pod_status": {
    "running": 24,
    "pending": 0,
    "failed": 0,
    "succeeded": 3
  },
  "node_metrics": {
    "cpu_usage_percent": 68.2,
    "memory_usage_percent": 72.4,
    "average_latency_ms": 15.3
  },
  "resource_utilization": {
    "total_cpu_cores": 16,
    "used_cpu_cores": 11.2,
    "total_memory_gb": 64,
    "used_memory_gb": 46.5
  },
  "timestamp": "2023-09-15T14:30:00Z"
}
```

## Output Template
The report must follow the structure defined in `template.md`. This template uses Mustache-style placeholders like `{{cluster_status}}` and `{{timestamp}}`. Although the output_fields list is empty, the template expects the exact JSON structure shown in the Output Schema section. No additional fields should be added beyond those explicitly defined.