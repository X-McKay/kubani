---
name: workflow-monitor
version: "1.0.0"
description: >
  Monitor Temporal workflows and provide a clear, human-readable summary of their
  current state using the Temporal MCP server.
metadata:
  domain: general
  category: diagnostic
  requires-approval: false
  confidence: 0.9
dependencies:
  mcp-servers:
    - temporal-mcp-server
---

# Workflow Monitor

Monitor Temporal workflows and provide a clear, human-readable summary of their current state using the Temporal MCP server.

## When to Use
- User wants to check the status of Temporal workflows
- User asks about running, failed, or completed workflows
- User wants a health check of the workflow system
- User asks "what workflows are running?" or similar questions

## Prerequisites
- Temporal MCP server must be available and connected
- Access to the Temporal namespace

## Execution Steps

### 1. Get Workflow Overview

First, gather workflows by status using the `list_workflows` MCP tool:

```
# List running workflows
list_workflows(status="running", limit=20)

# List failed workflows (to highlight problems)
list_workflows(status="failed", limit=10)

# List recently completed workflows
list_workflows(status="completed", limit=10)
```

### 2. Analyze Results

For each status category, extract:
- `workflow_id` - Unique identifier
- `workflow_type` - The type of workflow (e.g., "k8s-monitor-workflow")
- `status` - Current state (Running, Completed, Failed, etc.)
- `start_time` - When the workflow started
- `task_queue` - Which task queue it's on

### 3. Identify Issues

Look for potential problems:
- **Failed workflows**: Any workflow with status "Failed" needs attention
- **Stuck workflows**: Running workflows that started more than 24 hours ago with no recent activity
- **High failure rate**: If failed > completed, there may be systemic issues

### 4. Present Summary

Format the output as a clear markdown summary:

```markdown
## Temporal Workflow Status

### Summary
- **Running**: X workflows
- **Completed**: Y workflows
- **Failed**: Z workflows

### Running Workflows
| Workflow ID | Type | Started | Task Queue |
|-------------|------|---------|------------|
| wf-123 | order-processing | 2 hours ago | default |

### Failed Workflows (Needs Attention)
| Workflow ID | Type | Started | Task Queue |
|-------------|------|---------|------------|
| wf-456 | payment-validation | 1 hour ago | finance |

### Health Assessment
[Provide a brief assessment: "All systems healthy" or "X failed workflows require investigation"]
```

## Output Format

Present results as human-readable markdown with:
1. **Summary counts** - Quick overview of workflow states
2. **Running workflows table** - Currently active workflows
3. **Failed workflows table** (if any) - Highlighted for attention
4. **Health assessment** - One-line summary of overall health

## Example Output

```markdown
## Temporal Workflow Status

### Summary
- **Running**: 3 workflows
- **Completed**: 15 workflows (last 24h)
- **Failed**: 1 workflow

### Running Workflows
| Workflow ID | Type | Started | Task Queue |
|-------------|------|---------|------------|
| k8s-monitor-daily-001 | k8s-health-check | 5 min ago | k8s-monitor |
| news-digest-20240115 | news-aggregation | 2 hours ago | news-monitor |
| learning-cycle-weekly | voyager-learning | 1 hour ago | learning |

### Failed Workflows
| Workflow ID | Type | Started | Error |
|-------------|------|---------|-------|
| payment-retry-abc | payment-validation | 3 hours ago | Timeout |

### Health Assessment
1 failed workflow detected (payment-retry-abc). The k8s-monitor and news-monitor workflows are running normally.
```

## Error Handling

- If Temporal MCP is not available, inform the user: "Unable to connect to Temporal MCP server. Please ensure it's running."
- If no workflows exist, report: "No workflows found in the Temporal namespace."
- If a specific query fails, skip that category and continue with available data.

## Tips

- Use `get_workflow(workflow_id)` for detailed info on specific workflows
- Use `get_workflow_history(workflow_id)` to debug failed workflows
- Failed workflows often need `cancel_workflow` or `terminate_workflow` before retry

## Related Tools
- `list_workflows` - List workflows with optional status filter
- `get_workflow` - Get details of a specific workflow
- `get_workflow_history` - Get event history for debugging
- `cancel_workflow` - Cancel a running workflow
- `terminate_workflow` - Force terminate a stuck workflow
