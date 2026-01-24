# Kubani Skills

Skills are isolated, executable units with clear objectives. They follow the [AgentSkills.io](https://agentskills.io) standard with Kubani-specific extensions.

## Directory Structure

```
skills/
├── k8s/                          # Domain
│   ├── diagnostic/               # Category
│   │   └── check-pod-health/     # Individual skill
│   │       ├── SKILL.md          # Skill definition
│   │       ├── scripts/          # Executable scripts (optional)
│   │       ├── references/       # Additional docs (optional)
│   │       └── test.yaml         # Test scenarios (optional)
│   ├── remediation/
│   └── collection/
├── news/
├── general/
└── _development/                 # Skills in development
```

## SKILL.md Format

```yaml
---
name: restart-crashloop
version: "1.0.0"
description: >
  Restart a pod stuck in CrashLoopBackOff. Use when pod has crashed 3+ times
  and a restart might resolve transient issues.
metadata:
  domain: k8s
  category: remediation
  requires-approval: false
  confidence: 0.85
  mcp-servers:
    - kubernetes-mcp-server
---

# Restart CrashLoopBackOff Pod

## Preconditions

Before applying this skill, verify:
- Pod status is CrashLoopBackOff
- Pod has restarted more than 3 times

## Actions

### 1. Delete Pod to Trigger Recreation

Use the kubernetes-mcp-server to delete the pod.

```yaml
mcp_tool: kubernetes-mcp-server/pods_delete
params:
  name: $pod_name
  namespace: $namespace
timeout: 30s
```

## Success Criteria

- New pod created within 30 seconds
- New pod reaches Running state within 2 minutes

## Failure Handling

If the pod does not reach Running state:
1. Check events for the new pod
2. Escalate to human if pattern repeats
```

## Versioning

Skills use semantic versioning in the SKILL.md frontmatter:

- **MAJOR** (1.0.0 → 2.0.0): Breaking changes to skill interface
- **MINOR** (1.0.0 → 1.1.0): New capabilities, backward compatible
- **PATCH** (1.0.0 → 1.0.1): Bug fixes, performance improvements

See [ADR-001: Skill Versioning](../../docs/archive/plans/decisions/001-skill-versioning.md) for details.

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique skill identifier |
| `version` | string | Semantic version |
| `description` | string | What the skill does, with keywords for discovery |

## Optional Metadata

| Field | Type | Description |
|-------|------|-------------|
| `domain` | string | Top-level domain (k8s, news, general) |
| `category` | string | Category within domain |
| `requires-approval` | bool | Whether human approval is needed |
| `confidence` | float | Skill's self-reported confidence (0-1) |
| `mcp-servers` | list | MCP servers this skill uses |

## Testing Skills

Create a `test.yaml` in the skill directory:

```yaml
scenarios:
  - name: successful-restart
    context:
      pod_name: nginx-abc123
      namespace: default
    mocks:
      kubernetes-mcp-server.pods_delete: { success: true }
    expected:
      success: true

  - name: skip-if-oom
    context:
      recent_oomkill: true
    expected:
      skipped: true
      reason: "OOMKilled in last 10 minutes"
```

Run tests with:
```bash
kubani-dev test-skill k8s/remediation/restart-crashloop
```
