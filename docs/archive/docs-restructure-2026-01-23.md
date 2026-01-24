# Documentation Restructure - 2026-01-23

## Overview

Complete reorganization of the `docs/` directory to align with repository structure and improve navigation.

## Goals

1. **Mirror Repository Structure**: Organize docs to match code organization (kubani/, platform/, infrastructure/)
2. **Consistent Navigation**: Standard subsections (guides/, reference/, architecture/, troubleshooting/)
3. **Easy Discovery**: Documentation co-located with the components it describes
4. **Historical Preservation**: Move completed plans to archive/

## New Structure

```
docs/
├── README.md                          # Main documentation hub
├── getting-started/                   # Quickstart and installation
│   ├── README.md
│   ├── quickstart.md
│   └── installation.md
├── kubani/                           # Core package docs
│   ├── README.md
│   ├── agents/development/
│   ├── syndicates/reference/
│   └── mcp/architecture/
├── platform/                         # Platform tools docs
│   └── cli/                         # kubani-dev CLI
│       ├── README.md
│       ├── guides/
│       ├── reference/
│       └── development/
├── infrastructure/                   # Infrastructure docs
│   ├── README.md
│   ├── cluster/troubleshooting/
│   ├── configuration/
│   ├── gitops/
│   └── operations/
├── architecture/                     # System architecture
│   ├── README.md
│   ├── core-concepts/
│   ├── subsystems/
│   └── deployment/
├── adr/                             # Architecture decisions
│   └── README.md
├── planning/                        # Current planning
│   ├── README.md
│   ├── roadmap/
│   ├── backlog.md
│   └── todo.md
├── troubleshooting/                 # Troubleshooting guides
│   ├── README.md
│   └── common-issues.md
└── archive/                         # Historical docs
    ├── README.md
    └── plans/                       # Completed plans
```

## File Moves

| Old Location | New Location |
|-------------|-------------|
| docs/QUICKSTART.md | docs/getting-started/quickstart.md |
| docs/BOOTSTRAP.md | docs/getting-started/installation.md |
| docs/AGENT_DEVELOPMENT.md | docs/kubani/agents/development/creating-agents.md |
| docs/AGENT_RUNBOOK.md | docs/kubani/syndicates/reference/operations-runbook.md |
| docs/MCP_SERVER_INTEGRATION.md | docs/kubani/mcp/architecture/mcp-design.md |
| docs/development/DEVELOPMENT_GUIDE.md | docs/platform/cli/guides/local-development.md |
| docs/local-development.md | docs/platform/cli/guides/setup.md |
| docs/CLI_REFERENCE.md | docs/platform/cli/reference/commands.md |
| docs/ERROR_HANDLING.md | docs/platform/cli/reference/error-codes.md |
| docs/TESTING.md | docs/platform/cli/guides/testing.md |
| docs/CONTRIBUTING.md | docs/platform/cli/development/contributing.md |
| docs/DEVELOPMENT.md | docs/platform/cli/guides/development-workflow.md |
| docs/DNS_CONFIGURATION.md | docs/infrastructure/configuration/dns.md |
| docs/GPU_CONFIGURATION.md | docs/infrastructure/configuration/gpu.md |
| docs/SECRETS_MANAGEMENT.md | docs/infrastructure/configuration/secrets.md |
| docs/AUTHENTICATION.md | docs/infrastructure/configuration/authentication.md |
| docs/NAS_STORAGE.md | docs/infrastructure/configuration/storage.md |
| docs/CI-CD-PLAN.md | docs/infrastructure/gitops/architecture/ci-cd.md |
| docs/GITOPS_SERVICE_DEPLOYMENT.md | docs/infrastructure/gitops/guides/deploying-services.md |
| docs/SERVICE_VALIDATION.md | docs/infrastructure/gitops/guides/service-validation.md |
| docs/GITOPS_VALIDATION.md | docs/infrastructure/gitops/guides/validation.md |
| docs/PVC_MIGRATION.md | docs/infrastructure/operations/maintenance/pvc-migration.md |
| docs/PRODUCTION_SERVICES_QUICKSTART.md | docs/infrastructure/operations/production-checklist.md |
| docs/MINECRAFT_SERVER.md | docs/infrastructure/operations/specialty/minecraft-server.md |
| docs/ARCHITECTURE.md | docs/architecture/overview.md |
| docs/federated_architecture.md | docs/architecture/core-concepts/federated-agents.md |
| docs/architecture/LEARNING_SYSTEM.md | docs/architecture/core-concepts/learning-system.md |
| docs/BACKLOG.md | docs/planning/backlog.md |
| docs/TODO.md | docs/planning/todo.md |
| docs/AI_AGENTS_ROADMAP.md | docs/planning/roadmap/ai-agents.md |
| docs/PLAN_hybrid_skills_a2a.md | docs/planning/research/hybrid-skills.md |
| docs/TROUBLESHOOTING.md | docs/troubleshooting/common-issues.md |
| docs/plans/* | docs/archive/plans/* |

## Benefits

1. **Intuitive Navigation**: Documentation mirrors code structure
2. **Better Discovery**: Related docs are co-located
3. **Consistent Patterns**: All major sections follow same structure (guides/, reference/, architecture/)
4. **Clear Scope**: Each README clearly defines what's in that section
5. **Historical Context**: Archive preserves completed work

## Breaking Changes

External links to documentation will break. Update any external references from:
- `docs/QUICKSTART.md` → `docs/getting-started/quickstart.md`
- `docs/AGENT_DEVELOPMENT.md` → `docs/kubani/agents/development/creating-agents.md`
- etc.

## Migration Guide

For developers with local documentation links:

1. Update bookmark/links to new locations (see table above)
2. Use [docs/README.md](README.md) as the new entry point
3. Each section has a README for navigation

## Implementation

- Created new directory structure
- Moved 58 files to new locations using `git mv`
- Created 9 navigation README files
- Updated main [README.md](../README.md) with new documentation section
- Archived all historical plans to `archive/plans/`

## Next Steps

### Immediate
- Move files to new structure (completed)
- Create navigation READMEs (completed)
- Update main README.md (completed)
- Update import examples in .claude/ (completed)

### Short Term
- Create placeholder "coming soon" docs for missing content
- Add frontmatter to docs for better searchability
- Create cross-reference links between related docs

### Long Term
- Split large docs into focused topics
- Add diagrams and visuals
- Create interactive tutorials
