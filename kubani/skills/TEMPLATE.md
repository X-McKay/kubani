---
# Skill Metadata (Required)
name: skill-name-here
version: "1.0.0"
description: >
  Clear description of what this skill does and when to use it.
  Include keywords that help agents identify relevant situations.

# Author Information (Recommended)
author:
  name: Author Name
  email: author@example.com

# Classification (Required)
metadata:
  domain: k8s  # k8s | news | general
  category: remediation  # remediation | diagnostic | collection | analytics
  requires-approval: false
  confidence: 0.5
  
# Dependencies (Required)
dependencies:
  mcp-servers:
    - kubernetes-mcp-server
  skills: []  # Other skills this depends on
  tools: []   # External tools required

# Execution Configuration (Optional)
execution:
  timeout: 60s
  retries: 3
  backoff: exponential
---

# Skill Display Name

## When to Use

Describe the specific situations when this skill should be applied:
- Condition 1 that triggers this skill
- Condition 2 that triggers this skill
- Keywords: keyword1, keyword2, keyword3

## Prerequisites

Before applying this skill, verify:

- [ ] First condition that must be true
- [ ] Second condition that must be true
- [ ] Required permissions or access

## Input Schema

Define the expected input format:

```json
{
  "required_field": "string - Description of this field",
  "optional_field": "number - Optional description",
  "context": {
    "nested_field": "string - Nested field description"
  }
}
```

## Actions

### 1. First Action

Description of what to do in this step.

```yaml
mcp_tool: server/tool
params:
  key: $variable
timeout: 30s
on_error: continue  # or: fail, retry
```

### 2. Second Action

Description of the second step.

```yaml
mcp_tool: server/another-tool
params:
  input: $previous_output
```

## Output Schema

Define the expected output format:

```json
{
  "status": "success | partial | failed",
  "result": {
    "field1": "Description of output field",
    "field2": "Description of another field"
  },
  "metadata": {
    "duration_ms": "number",
    "steps_completed": "number"
  }
}
```

## Success Criteria

The skill succeeds when:

- [ ] First criterion is met
- [ ] Second criterion is met
- [ ] Expected state is achieved

## Failure Handling

What to do if the skill fails:

| Error Type | Handling Strategy |
|------------|-------------------|
| Timeout | Retry with backoff |
| Permission denied | Escalate to human |
| Resource not found | Log and skip |

## Rollback Procedure

If rollback is needed:

1. First rollback step
2. Second rollback step

## Examples

### Example 1: Basic Usage

**Input:**
```json
{
  "required_field": "example_value"
}
```

**Output:**
```json
{
  "status": "success",
  "result": {
    "field1": "result_value"
  }
}
```

### Example 2: Edge Case

**Input:**
```json
{
  "required_field": "edge_case_value"
}
```

**Output:**
```json
{
  "status": "partial",
  "result": {
    "field1": "partial_result"
  },
  "warnings": ["Warning about edge case"]
}
```

## Related Skills

- [related-skill-1](../related-skill-1/SKILL.md) - When to use instead
- [related-skill-2](../related-skill-2/SKILL.md) - Can be combined with

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-01-09 | Initial version |
