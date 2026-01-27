# Registry as Source of Truth - Implementation Plan

**Status:** Active
**Created:** 2026-01-27
**Author:** Claude (with human review)

## Overview

This plan transforms Kubani from a Git-first architecture to a Registry-first architecture where:

- **PostgreSQL Registry** is the source of truth for all metadata, discovery, and lifecycle state
- **OCI Registry** (registry.almckay.io) stores actual content as versioned, immutable tarballs
- **Git** becomes an audit trail with periodic exports from the registry

## Why This Change?

1. **Agents as primary authors** - Cluster agents create/modify skills at runtime; humans review and approve
2. **Unified development experience** - Same workflow whether developing locally or in-cluster
3. **Dynamic skill discovery** - Agents query registry for skills at runtime rather than loading from filesystem
4. **Immutable versioning** - OCI digests guarantee exact reproducibility

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   REGISTRY (PostgreSQL)                          │
├─────────────────────────────────────────────────────────────────┤
│  skills                           │  agents                      │
│  ├── id, name, description        │  ├── id, name, version       │
│  ├── current_version              │  ├── oci_repository          │
│  ├── oci_repository               │  └── status                  │
│  ├── status (draft/prod)          │                              │
│  └── versions[]                   │  syndicates                  │
│                                   │  ├── id, name, version       │
│  skill_versions                   │  ├── oci_repository          │
│  ├── version, oci_tag, oci_digest │  └── agent_refs[]            │
│  └── status, promoted_at/by       │                              │
└─────────────────────────────────────────────────────────────────┘
                         │
                         │ metadata + pointers
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│            OCI REGISTRY (registry.almckay.io)                    │
├─────────────────────────────────────────────────────────────────┤
│  skills/{name}:{version}      → tarball (SKILL.md, scripts/, …) │
│  agents/{name}:{version}      → tarball (config, code)          │
│  syndicates/{name}:{version}  → tarball (config, orchestration) │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Phases

| Phase | Description | Duration | Plan Document |
|-------|-------------|----------|---------------|
| 1 | Schema Migration | ~1 week | [phase-1-schema.md](./phase-1-schema.md) |
| 2 | OCI Integration & CLI | ~1.5 weeks | [phase-2-oci-cli.md](./phase-2-oci-cli.md) |
| 3 | Agent Integration | ~1 week | [phase-3-agents.md](./phase-3-agents.md) |
| 4 | Migration & Cutover | ~1 week | [phase-4-migration.md](./phase-4-migration.md) |

**Total Estimated Duration: 4-5 weeks**

## Key Design Decisions

### 1. Two-Layer Storage Model

- **PostgreSQL** for queryable metadata (search, filter, relationships)
- **OCI Registry** for content (leverages existing infrastructure, immutable digests)

### 2. Version Lifecycle

```
draft ──► testing ──► staging ──► production
  │          │           │            │
  │          │           │            └── All agents use this version
  │          │           └── Canary: 10% of traffic
  │          └── Automated evaluation suite runs
  └── Only author can access
```

### 3. Filesystem as Cache

Local development pulls from registry, edits locally, pushes back:
```bash
kubani-dev pull skill investigate-pod-failure
# edit locally...
kubani-dev push skill investigate-pod-failure --version 1.1.0
```

### 4. Git Export (Not Sync)

Registry → Git is one-way export for audit trail. Git is no longer authoritative.

## Dependencies

- `oras-py` - Python SDK for OCI registry operations
- PostgreSQL 14+ (existing)
- registry.almckay.io (existing OCI registry)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| OCI registry downtime | Agents can't load skills | Local caching, retry with backoff |
| Migration corrupts data | Skills unavailable | Git backup, dry-run first, phased rollout |
| oras-py compatibility | Push/pull fails | Pin version, integration tests |
| Performance (large skills) | Slow pull times | Lazy loading, cache warm-up |

## How to Use This Plan

1. Read this overview first
2. Execute phases in order (each phase has dependencies on previous)
3. Each phase document contains:
   - Detailed tasks with acceptance criteria
   - Code locations and specific changes
   - Test requirements
   - Commit checkpoints
4. Commit frequently - the plan is designed for incremental progress

## Related Documents

- [Current Registry Schema](../../../../platform/registry/alembic/versions/)
- [Current Sync Implementation](../../../../platform/cli/src/kubani_dev/sync.py)
- [ORAS Documentation](https://oras.land/docs/)
- [Open Agent Skill Standard](https://agentskills.io/specification)
