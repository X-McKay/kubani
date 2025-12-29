---
paths:
  - agents/**/*
---

# AI Agent Development Rules

When working with AI agents in the `agents/` directory:

## Code Standards

- Use Python 3.11+ with full type annotations
- Use Pydantic models for all data structures
- Follow the patterns in `agents/core/` for shared functionality
- All agents depend on `core-agents` for base utilities

## File Structure

Each agent must have:
```
agents/<agent-name>/
├── src/<agent_name>/
│   ├── __init__.py
│   ├── worker.py        # Temporal worker entry point
│   ├── workflows.py     # Temporal workflow definitions
│   ├── activities.py    # Temporal activity definitions
│   └── models.py        # Pydantic data models
├── tests/
├── pyproject.toml       # Must include version
└── Earthfile            # Docker build definition
```

## Versioning

- Version is in `pyproject.toml`: `version = "0.1.0"`
- Image tags use `{version}-{git-sha}` format
- Bump version before deploying changes: `/bump-version <agent> patch|minor|major`

## Building

- Use Earthly for container builds: `earthly ./agents/<agent>+docker`
- Core changes trigger rebuild of ALL agents
- Always push after building: `docker push registry.almckay.io/<agent>:<tag>`

## Temporal Patterns

- Use descriptive workflow IDs: `<agent>-<action>-<timestamp>`
- Activities should be idempotent where possible
- Handle timeouts and retries appropriately
- Log important state transitions

## Testing

- Run agent tests with: `just test-agent <agent-name>`
- Include unit tests for activities
- Test workflow logic with mocks
