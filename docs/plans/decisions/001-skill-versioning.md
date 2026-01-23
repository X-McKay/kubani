# ADR-001: Skill Versioning Strategy

**Status**: Accepted
**Date**: 2026-01-22
**Context**: Kubani Restructuring Phase 0

## Context

Skills are executable units that agents invoke via the Skills MCP Server. We need a versioning strategy to:
- Track skill evolution over time
- Enable rollback to previous versions
- Measure performance changes between versions
- Support A/B testing of skill variants

## Decision

We will use **semantic versioning in SKILL.md frontmatter**.

```yaml
---
name: restart-crashloop
version: "1.0.0"
description: Restart a pod stuck in CrashLoopBackOff
metadata:
  domain: k8s
  category: remediation
---
```

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **Frontmatter version** (chosen) | Simple, self-contained, easy to parse | Single version per file |
| Directory-based (`skill/v1.0.0/`) | Multiple versions coexist | Complex paths, code duplication |
| Git tags (`skill/k8s/.../v1.0.0`) | Immutable history | Clutters tag namespace |
| Registry metadata | Centralized tracking | Requires registry to be running |

## Rationale

Frontmatter versioning was chosen because it:

1. **Self-contained**: Version lives with the skill definition
2. **Simple to implement**: Just a YAML field, no infrastructure changes
3. **Easy to parse**: Standard frontmatter parsing extracts version
4. **Matches agent pattern**: Agents version via pyproject.toml, skills via SKILL.md
5. **Git-trackable**: `git log -- skills/k8s/remediation/restart-crashloop/SKILL.md` shows version history
6. **Extensible**: Can add registry sync later without changing format

## Implementation

1. Add `version` field to all SKILL.md files
2. Skills MCP Server reads version from frontmatter
3. Version is included in skill execution metadata for learning system
4. Registry can sync skill versions for discovery

## Versioning Rules

Follow semantic versioning:
- **MAJOR** (1.0.0 → 2.0.0): Breaking changes to skill interface
- **MINOR** (1.0.0 → 1.1.0): New capabilities, backward compatible
- **PATCH** (1.0.0 → 1.0.1): Bug fixes, performance improvements

## Example

Before:
```yaml
---
name: restart-crashloop
description: Restart a pod stuck in CrashLoopBackOff
metadata:
  domain: k8s
  category: remediation
---
```

After:
```yaml
---
name: restart-crashloop
version: "1.0.0"
description: Restart a pod stuck in CrashLoopBackOff
metadata:
  domain: k8s
  category: remediation
---
```

## Future Considerations

- **A/B Testing**: Can support via separate skill files with different versions
- **Multiple Active Versions**: If needed, can evolve to directory-based with symlinks
- **Registry Integration**: Skills MCP Server can publish versions to registry
