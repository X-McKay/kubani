# Kubani Deployment Architecture Design

**Date:** 2025-01-22
**Status:** Approved
**Author:** Claude + Al

## Overview

This document defines the deployment architecture for the kubani restructuring project. The goal is to enable rapid iterative development while maintaining isolation between components.

## Design Principles

1. **Syndicates are independently deployable** - k8s-monitor and news-monitor can be modified, versioned, and deployed in isolation
2. **Framework is shared** - Common code (framework, agents) lives in one package imported by syndicates
3. **Skills are data, not code** - Skills are versioned via frontmatter and synced to registry, no rebuild needed
4. **Single lockfile** - uv workspace ensures consistent dependencies across all components

## Architecture

### Component Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                        kubani/ (uv workspace)                    │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              kubani-framework (package)                  │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │   │
│  │  │ framework/  │  │ agents/     │  │ skills/         │  │   │
│  │  │             │  │             │  │ (files only,    │  │   │
│  │  │ - events    │  │ - classifier│  │  not in package)│  │   │
│  │  │ - config    │  │ - remediator│  │                 │  │   │
│  │  │ - base      │  │ - learner   │  │ Versioned via   │  │   │
│  │  │   classes   │  │ - collector │  │ frontmatter,    │  │   │
│  │  │             │  │ - analyst   │  │ synced to       │  │   │
│  │  │             │  │ - publisher │  │ registry        │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ▲                                  │
│                              │ depends on                       │
│         ┌────────────────────┴────────────────────┐            │
│         │                                         │            │
│  ┌──────┴──────┐                          ┌──────┴──────┐     │
│  │ k8s-monitor │                          │ news-digest │     │
│  │ syndicate   │                          │ syndicate   │     │
│  │             │                          │             │     │
│  │ v0.4.0      │                          │ v0.2.0      │     │
│  │             │                          │             │     │
│  │ Earthfile   │                          │ Earthfile   │     │
│  │ pyproject   │                          │ pyproject   │     │
│  └─────────────┘                          └─────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
kubani/
├── pyproject.toml                 # Workspace root + kubani-framework package
├── uv.lock                        # Single lockfile for workspace
│
├── framework/                     # Core framework code
│   ├── __init__.py
│   ├── events.py                  # Event bus
│   ├── config.py                  # Configuration
│   └── base.py                    # Base classes
│
├── agents/                        # Shared agents (part of framework package)
│   ├── __init__.py
│   ├── _base/                     # KubaniAgent base class
│   ├── event_classifier/
│   ├── remediator/
│   ├── skill_learner/
│   ├── feed_collector/
│   ├── content_analyst/
│   └── digest_publisher/
│
├── skills/                        # Skill definitions (NOT in package)
│   ├── k8s/
│   │   ├── diagnostic/
│   │   └── remediation/
│   └── general/
│       ├── memory/
│       └── notifications/
│
└── syndicates/
    ├── _base/                     # Syndicate base class (part of framework)
    │
    ├── k8s_monitor/               # K8s Monitor Syndicate
    │   ├── pyproject.toml         # Independent package
    │   ├── Earthfile              # Builds k8s-monitor image
    │   ├── src/
    │   │   └── k8s_monitor_syndicate/
    │   │       ├── __init__.py
    │   │       ├── worker.py      # Temporal worker entry point
    │   │       └── syndicate.py   # K8sMonitorSyndicate class
    │   └── tests/
    │
    └── news_digest/               # News Digest Syndicate
        ├── pyproject.toml         # Independent package
        ├── Earthfile              # Builds news-monitor image
        ├── src/
        │   └── news_digest_syndicate/
        │       ├── __init__.py
        │       ├── worker.py
        │       └── syndicate.py
        └── tests/
```

### pyproject.toml Examples

**Root (kubani/pyproject.toml):**
```toml
[project]
name = "kubani-framework"
version = "0.5.0"
description = "Kubani AI agent framework"
dependencies = [
    "pydantic>=2.0.0",
    "pyyaml>=6.0.0",
    "structlog>=24.0.0",
    "temporalio>=1.0.0",
]

[tool.uv.workspace]
members = ["syndicates/k8s_monitor", "syndicates/news_digest"]

[tool.uv.sources]
# Local development sources if needed
```

**Syndicate (kubani/syndicates/k8s_monitor/pyproject.toml):**
```toml
[project]
name = "k8s-monitor-syndicate"
version = "0.4.0"
description = "Kubernetes cluster health monitoring syndicate"
dependencies = [
    "kubani-framework",
]

[tool.uv.sources]
kubani-framework = { workspace = true }

[project.scripts]
k8s-monitor-worker = "k8s_monitor_syndicate.worker:main"
```

## Versioning Strategy

### Version Locations

| Component | Version Location | Bump Trigger |
|-----------|------------------|--------------|
| Framework | `kubani/pyproject.toml` | Agent or framework code changes |
| k8s-monitor | `syndicates/k8s_monitor/pyproject.toml` | Syndicate-specific changes |
| news-digest | `syndicates/news_digest/pyproject.toml` | Syndicate-specific changes |
| Skills | `skills/**/SKILL.md` frontmatter | Skill content changes |

### Version Commands

```bash
# Bump framework version
just bump-framework patch|minor|major

# Bump syndicate version
just bump-syndicate k8s-monitor patch|minor|major
just bump-syndicate news-digest patch|minor|major

# Sync skills to registry (no version bump needed for registry)
kubani sync --skills
```

### Dependency Pinning

Syndicates should pin framework versions to allow independent deployment:

```toml
# During active development (loose)
dependencies = ["kubani-framework>=0.5.0"]

# For stable releases (strict)
dependencies = ["kubani-framework>=0.5.0,<0.6.0"]
```

## Build & Deploy Flow

### Building Images

Each syndicate builds its own Docker image:

```bash
# Build k8s-monitor image
earthly ./syndicates/k8s_monitor/+docker --VERSION=0.4.0

# Build news-digest image
earthly ./syndicates/news_digest/+docker --VERSION=0.2.0

# Or via kubani
kubani build k8s-monitor
kubani build news-digest
```

### Image Contents

Each syndicate image contains:
- The syndicate package (`k8s-monitor-syndicate`)
- The framework package (`kubani-framework`)
- All Python dependencies (from shared `uv.lock`)

Skills are NOT in the image - they're loaded from the registry at runtime.

### Deployment

```bash
# Deploy specific syndicate
kubani deploy k8s-monitor --version 0.4.0

# GitOps updates
infrastructure/gitops/apps/ai-agents/k8s-monitor/deployment.yaml
infrastructure/gitops/apps/ai-agents/news-monitor/deployment.yaml
```

## Skill Management

Skills are versioned separately and synced to the registry:

```yaml
# skills/k8s/remediation/restart-crashloop/SKILL.md
---
name: restart-crashloop
version: "1.2.0"  # Bump when skill changes
description: Restart pods in CrashLoopBackOff
---
```

### Skill Workflow

1. Edit skill markdown
2. Bump version in frontmatter
3. Run `kubani sync --skills`
4. Skills are available immediately (no image rebuild)

### Skill Loading

Agents load skills from the registry at runtime:

```python
# In agent code
skill = await skill_registry.get("k8s/remediation/restart-crashloop")
# Returns latest version, or specific version if pinned
```

## Development Workflow

### Local Development

```bash
cd kubani/

# Install all workspace packages in dev mode
uv sync

# Run specific syndicate locally
uv run --package k8s-monitor-syndicate k8s-monitor-worker

# Run tests for specific syndicate
uv run --package k8s-monitor-syndicate pytest

# Run all tests
uv run pytest
```

### Making Changes

**Framework/Agent change:**
1. Edit code in `framework/` or `agents/`
2. Run tests: `uv run pytest`
3. Bump framework version: `just bump-framework patch`
4. Commit and push
5. Syndicates rebuild on next deploy (pick up new framework)

**Syndicate change:**
1. Edit code in `syndicates/k8s_monitor/`
2. Run tests: `uv run --package k8s-monitor-syndicate pytest`
3. Bump syndicate version: `just bump-syndicate k8s-monitor patch`
4. Build and deploy: `kubani build k8s-monitor && kubani deploy k8s-monitor`

**Skill change:**
1. Edit `skills/**/SKILL.md`
2. Bump version in frontmatter
3. Sync to registry: `kubani sync --skills`
4. No rebuild needed - agents load from registry

## Migration Plan

### Phase 7: Implement Workspace Structure

1. Update `kubani/pyproject.toml` to be workspace root
2. Create `syndicates/k8s_monitor/pyproject.toml`
3. Create `syndicates/news_digest/pyproject.toml`
4. Move syndicate entry points (worker.py) to syndicate packages
5. Create Earthfiles for each syndicate
6. Test builds

### Phase 8: Cutover

1. Build new syndicate images
2. Update GitOps manifests to use new images
3. Deploy in shadow mode
4. Validate functionality
5. Promote to primary
6. Deprecate old `agents/k8s-monitor/` and `agents/news-monitor/`

## Trade-offs

### Pros
- Independent syndicate versioning and deployment
- Shared lockfile ensures dependency consistency
- Skills iterate without rebuilds
- Clear separation of concerns
- Modern uv workspace tooling

### Cons
- More pyproject.toml files to maintain
- Framework changes affect all syndicates (need to rebuild)
- Initial migration complexity

## References

- [uv Workspaces Documentation](https://docs.astral.sh/uv/concepts/projects/workspaces/)
- [Monorepo Versioning Strategies](https://medium.com/streamdal/monorepos-version-tag-and-release-strategy-ce26a3fd5a03)
- [Temporal + Kubernetes Pattern](https://temporal.io/blog/prototype-to-prod-ready-agentic-ai-grid-dynamics)
