# Skills MCP Integration Tests

This directory contains integration tests for the Skills MCP server.

## Running Integration Tests

### Prerequisites

- Python environment with test dependencies
- Skills available in the configured location (filesystem or OCI registry)

### Running Tests

Run integration tests with pytest:

```bash
# From the skills-mcp directory
uv run pytest tests/test_integration.py -v

# Or from the workspace root
uv run pytest kubani/mcp/servers/skills/tests/test_integration.py -v
```

## Test Coverage

Integration tests cover:

- **Skill Discovery**:
  - Listing available skills
  - Getting skill details
  - Searching for skills

- **Skill Execution**:
  - Loading skill definitions
  - Validating skill schemas
  - Basic skill invocation

## Environment Variables

The integration tests use the following environment variables:

- `SKILLS_PATH` - Path to skills directory (for filesystem-based discovery)
- `OCI_REGISTRY_URL` - OCI registry URL (for OCI-based discovery)
- `OCI_REGISTRY_USERNAME` - OCI registry username (optional)
- `OCI_REGISTRY_PASSWORD` - OCI registry password (optional)

## Notes

- Skills MCP can use either filesystem or OCI registry for skill discovery
- Integration tests focus on the MCP interface, not the underlying storage
- For OCI-based tests, ensure the registry is accessible and credentials are configured
