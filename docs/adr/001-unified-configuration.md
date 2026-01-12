# ADR-001: Unified Configuration System

## Status
Accepted

## Context

The Kubani project had configuration scattered across multiple files and modules:
- `agents/core/src/core_agents/config.py` - Agent configuration
- `agents/core/src/core_agents/memory/config.py` - Memory configuration
- `registry/src/kubani_registry/config.py` - Registry configuration
- `tools/kubani-dev/src/kubani_dev/config.py` - CLI configuration
- Various `.env` files and environment variables

This led to:
- Inconsistent configuration patterns across components
- Difficulty understanding what configuration options exist
- Duplication of configuration loading logic
- No clear hierarchy for configuration overrides
- Hard to switch between local development and production

## Decision

Implement a unified configuration system using `pydantic-settings` with hierarchical YAML loading:

```
config.default.yaml    → Base defaults (committed)
config.{env}.yaml      → Environment-specific (committed)
config.local.yaml      → Local overrides (gitignored)
Environment variables  → Runtime overrides (KUBANI_ prefix)
```

All configuration is defined in `agents/core/src/core_agents/config_unified.py` with:
- Type-safe Pydantic models for all configuration sections
- Computed fields for derived values
- Helper methods for common configuration patterns (mem0, MCP servers)
- Singleton pattern with reload capability

## Consequences

### Positive
- Single source of truth for all configuration
- Type safety and validation at load time
- IDE autocomplete for configuration access
- Easy to switch between environments
- Clear hierarchy for overrides
- Testable with mock configurations

### Negative
- All components depend on core_agents package
- Migration effort for existing code
- Learning curve for pydantic-settings patterns

### Neutral
- Configuration files must follow YAML format
- Environment variables must use `KUBANI_` prefix with `__` nesting

## Alternatives Considered

### 1. Keep Separate Configuration Files
- **Rejected**: Leads to inconsistency and duplication

### 2. Use Environment Variables Only
- **Rejected**: Hard to manage complex nested configuration

### 3. Use a Configuration Service
- **Rejected**: Adds complexity and external dependency for simple use case

### 4. Use Dynaconf
- **Rejected**: pydantic-settings provides better type safety and integration with existing Pydantic models
