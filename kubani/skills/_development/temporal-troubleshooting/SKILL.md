```yaml
---
name: temporal-troubleshooting
version: "1.0.0"
description: >
  Diagnose and troubleshoot Temporal workflow issues like failures, timeouts, and stuck workflows

metadata:
  domain: temporal
  category: diagnostic
  requires-approval: false

dependencies:
  mcp-servers:
    - kubernetes-mcp-server
    - temporal-mcp-server
allowed-tools: "mcp__kubernetes-mcp-server__pods_get, mcp__kubernetes-mcp-server__pods_list, mcp__kubernetes-mcp-server__pods_log, mcp__kubernetes-mcp-server__resources_get, mcp__kubernetes-mcp-server__resources_list, mcp__temporal-mcp-server__get_workflow, mcp__temporal-mcp-server__get_workflow_history, mcp__temporal-mcp-server__list_workflows"
---
```

# Temporal Workflow Troubleshooting

## When to Use
- A Temporal workflow is stuck or unresponsive
- A workflow failed with an unclear error message
- Investigating activity timeouts or task queue issues
- Diagnosing worker unavailability or resource constraints

## Prerequisites
- Valid workflow ID and namespace
- Access to Temporal namespace (default: 'default')
- Permission to retrieve workflow history and task queue status
- Access to Kubernetes cluster for worker diagnostics

## Input Schema
```json
{
  "workflow_id": {
    "type": "string",
    "description": "Temporal workflow ID to investigate",
    "required": true
  },
  "namespace": {
    "type": "string",
    "description": "Temporal namespace (default: 'default')",
    "required": false
  },
  "symptom": {
    "type": "string",
    "description": "Brief problem description (e.g., 'stuck', 'failed')",
    "required": true
  },
  "error_message": {
    "type": "string",
    "description": "Error message from Temporal logs/UI",
    "required": false
  }
}
```

## Actions
### 1. Retrieve workflow history
Use `mcp__temporal-mcp-server__get_workflow_history` with workflow_id and namespace.

### 2. Analyze symptom and error message
Identify patterns in the error message and workflow history events.

### 3. Check task queue status
Use `mcp__temporal-mcp-server__list_workflows` to verify task queue availability.

### 4. Inspect activity timeouts
Review activity configurations and worker resource constraints.

### 5. Generate diagnosis
Compile findings into a structured diagnosis with remediation steps.

## Output Schema
```json
{
  "diagnosis": "Root cause analysis of the issue",
  "investigation_steps": ["Commands/checks performed during diagnosis"],
  "recommended_actions": ["Step-by-step remediation steps"],
  "prevention_tips": ["Preventive measures for future issues"],
  "urgency": "low/medium/high"
}
```
> CRITICAL: Return ONLY this exact JSON structure, no additional wrapper fields

## Success Criteria
- Diagnosis field contains clear root cause
- Investigation_steps reflects all diagnostic actions
- Recommended_actions provides actionable solutions
- Prevention_tips includes at least 2 preventive measures
- Urgency is correctly categorized as low/medium/high

## Failure Handling
| Error Type                  | Handling Strategy                                  |
|-----------------------------|------------------------------------------------------|
| Invalid workflow_id         | Return 'Workflow not found' error                   |
| Permission denied           | Log error and return generic diagnosis                |
| Unavailable logs            | Fallback to workflow history analysis               |

## Examples
- [Example 1: Stuck Workflow](examples/example-1.md)  
  Diagnose a workflow stuck waiting for activity task
- [Example 2: Timeout Error](examples/example-2.md)  
  Diagnose activity execution timeout

## Output Template
This skill uses `template.md` with the following structure:
```markdown
{{diagnosis}}
{{investigation_steps}}
{{recommended_actions}}
{{prevention_tips}}
{{urgency}}
```

The output must follow this template with Mustache-style placeholders:
- `{{diagnosis}}`: Root cause analysis
- `{{investigation_steps}}`: Array of diagnostic steps
- `{{recommended_actions}}`: Array of remediation steps
- `{{prevention_tips}}`: Array of preventive measures
- `{{urgency}}`: Severity level (low/medium/high)