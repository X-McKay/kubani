# Claude Code Skills

This directory contains skills that guide Claude Code's behavior and provide documentation for the Kubani project.

## Directory Structure

### Documentation Skills
These skills provide guidance, principles, and patterns:
- `architecture/` - Architecture principles and design decisions
- `code-patterns/` - Standard code patterns and conventions
- `local-development/` - Local development setup and workflow
- `mcp-servers/` - MCP server documentation
- `testing/` - Testing guidelines and best practices

### Meta Skills
These skills help create other skills and tools:
- `skill-developer/` - LLM-integrated skill development, evaluation, and improvement
- `mcp-builder/` - Guide for building MCP servers

### Development Workspace
- `development/` - Symlink to `../../skills/development/`
  - This is the active workspace for developing new skills
  - Accessible from both `.claude/skills/development` and `skills/development`
  - Skills here are temporary and should be promoted to production when ready

## Executable Skills

**Executable skills have been migrated to the new system:**

All executable skills are now in `skills/core/` or `skills/agents/` with versioning:
- `skills/core/<skill-name>/v<version>/` - General-purpose skills
- `skills/agents/<agent-name>/<skill-name>/v<version>/` - Agent-specific skills

To work with executable skills, use the `kubani skill` CLI:

```bash
# Create a new skill
kubani skill draft my-skill --description "Does something"

# Evaluate locally
kubani skill eval my-skill --local

# Promote to production (auto-increments version)
kubani skill promote my-skill --category core

# List all skills
kubani skill list

# View evaluation history
kubani skill eval-history my-skill
```

## Skill Development Workflow

1. **Draft**: Create a new skill in `development/`
2. **Implement**: Write the skill logic and test cases
3. **Evaluate**: Run evaluations locally to verify functionality
4. **Iterate**: Fix issues and re-evaluate until all tests pass
5. **Promote**: Move to production with automatic version bumping
6. **Deploy**: Commit to Git and deploy to cluster

## Migration Notes

Executable skills were migrated from `.claude/skills/` to `skills/core/` on 2026-01-20:
- `add-node` → `skills/core/add-node/v1.0.0`
- `agent-evaluation` → `skills/core/agent-evaluation/v1.0.0`
- `agents` → `skills/core/agents/v1.0.0`
- `bootstrap-node` → `skills/core/bootstrap-node/v1.0.0`
- `bump-version` → `skills/core/bump-version/v1.0.0`
- `cluster-health` → `skills/core/cluster-health/v1.0.0` (consolidated from cluster-status, validate, troubleshoot)
- `continuous-learning` → `skills/core/continuous-learning/v1.0.0`
- `deployment` → `skills/core/deployment/v1.0.0`
- `new-agent` → `skills/core/new-agent/v1.0.0`
- `rollback` → `skills/core/rollback/v1.0.0`

Documentation and meta skills remain in `.claude/skills/` for Claude Code guidance.

## See Also

- [Skill Development Workflow Documentation](../../skills/README.md)
- [Implementation Summary](../../IMPLEMENTATION_SUMMARY.md)
- [Decision Records](../../docs/adr/)
