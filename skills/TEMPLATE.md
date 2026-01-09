---
name: skill-name-here
description: >
  Clear description of what this skill does and when to use it.
  Include keywords that help agents identify relevant situations.
metadata:
  domain: k8s  # k8s | news | general
  category: remediation  # remediation | diagnostic | collection
  requires-approval: false
  confidence: 0.5
  mcp-servers:
    - kubernetes-mcp-server
---

# Skill Display Name

## Preconditions

Before applying this skill, verify:

- [ ] First condition
- [ ] Second condition

## Actions

### 1. First Action

Description of what to do.

```yaml
mcp_tool: server/tool
params:
  key: $variable
timeout: 30s
```

## Success Criteria

- [ ] First criterion
- [ ] Second criterion

## Failure Handling

What to do if the skill fails.

## Examples

Input/output examples.
