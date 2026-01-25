# Skill Auto: Registry-Centric Architecture

**Status**: Future Enhancement
**Priority**: Medium
**Related**: Option B from skill-auto workflow redesign discussion

## Problem Statement

The current skill-auto workflow stores developing skills on the local filesystem, which:
1. Violates Temporal sandbox requirements (no I/O in workflows)
2. Doesn't work in cluster deployments where workers lack shared filesystem access
3. Conflicts with the Registry-Centric Architecture principle

## Current State

Developing skills are stored at:
```
kubani/skills/_development/<skill-name>/
├── SKILL.md
├── test_cases.yaml
└── metadata.json
```

The workflow reads these files directly, which fails in the Temporal sandbox.

## Proposed Solution: Registry-Centric Storage

Store developing skills in the registry database during iterations, only syncing to git on promotion.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Registry Database                                          │
│  skills table: id, name, status="development"               │
│  skill_versions table: content, test_cases, metrics         │
└─────────────────────────────────────────────────────────────┘
         │                                           │
         ▼                                           ▼
┌─────────────────┐                        ┌─────────────────┐
│  store_skill    │  ← New activity        │  load_skill     │
│  (MCP → registry)                        │  (MCP → content)│
└─────────────────┘                        └─────────────────┘
         │
         ▼ On promotion
┌─────────────────┐
│ sync_to_git     │  ← Create PR from registry content
│ (registry → git)│
└─────────────────┘
```

### Database Schema Changes

Add content fields to `skill_versions` table:

```sql
ALTER TABLE skill_versions ADD COLUMN content TEXT;
ALTER TABLE skill_versions ADD COLUMN test_cases JSONB;
ALTER TABLE skill_versions ADD COLUMN iteration_number INTEGER;
ALTER TABLE skill_versions ADD COLUMN development_status TEXT DEFAULT 'iterating';
```

### New API Endpoints

```
POST /skills/{skill_id}/versions
  - Store new version with content
  - Input: { content, test_cases, iteration_number }

GET /skills/{skill_id}/versions/{version}
  - Retrieve version with content
  - Returns: { content, test_cases, metrics, created_at }

PUT /skills/{skill_id}/promote
  - Promote development skill to production
  - Creates PR to sync content to git
```

### Skills MCP Server Tools

```python
@mcp.tool()
async def store_skill_version(
    skill_name: str,
    content: str,
    test_cases: str,
    iteration: int,
    metrics: dict | None = None,
) -> dict:
    """Store a skill version in the registry."""
    ...

@mcp.tool()
async def load_skill_version(
    skill_name: str,
    version: str | None = None,  # None = latest
) -> dict:
    """Load skill content from the registry."""
    ...
```

### Workflow Changes

```python
# Instead of:
skill_content = Path(self._state.skill_path, "SKILL.md").read_text()

# Use activity:
skill_content = await workflow.execute_activity(
    load_skill_from_registry,
    args=[self._state.skill_name],
    ...
)
```

## Benefits

1. **Works in cluster**: Workers read from shared database, not local files
2. **Audit trail**: Full version history in database
3. **Cross-agent collaboration**: Multiple agents can work on skills
4. **Consistent with architecture**: Aligns with Registry-Centric principle
5. **Better observability**: Query database for skill development status

## Migration Path

1. Implement Option A (content-passing) first for immediate fix
2. Add registry storage endpoints
3. Add Skills MCP tools
4. Migrate workflow to use registry
5. Deprecate filesystem-based storage for development skills

## Dependencies

- Registry API updates
- Skills MCP server enhancements
- Database migrations
- kubani-dev CLI updates for registry sync

## Estimated Effort

- Registry API: 2-3 days
- Skills MCP: 1-2 days
- Workflow migration: 1-2 days
- Testing: 2-3 days
- Total: ~1-2 weeks
