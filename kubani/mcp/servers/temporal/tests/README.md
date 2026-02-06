# Temporal MCP Integration Tests

This directory contains integration tests for the Temporal MCP server that test against a real Temporal server.

## Running Integration Tests

### Prerequisites

- Docker and Docker Compose installed
- Python environment with test dependencies

### Setup

1. Start the Temporal server:
```bash
cd kubani/mcp/servers/temporal
docker-compose -f docker-compose.integration.yml up -d
```

2. Wait for Temporal to be healthy (about 60 seconds):
```bash
docker-compose -f docker-compose.integration.yml ps
```

The temporal service should show "healthy" status.

### Running Tests

Run integration tests with pytest:

```bash
# From the temporal-mcp directory
uv run pytest tests/test_integration.py -v

# Or from the workspace root
uv run pytest kubani/mcp/servers/temporal/tests/test_integration.py -v
```

### Cleanup

Stop and remove the Temporal server:

```bash
docker-compose -f docker-compose.integration.yml down -v
```

## Test Coverage

Integration tests cover:

- **Workflow Management**:
  - Listing workflows
  - Getting workflow details
  - Starting workflows
  - Workflow history retrieval

- **Schedule Management**:
  - Listing schedules
  - Pausing/unpausing schedules
  - Triggering schedules

- **Workflow Operations**:
  - Signaling workflows
  - Querying workflows
  - Canceling workflows
  - Terminating workflows

## Environment Variables

The integration tests use the following environment variables (with defaults):

- `TEMPORAL_HOST=localhost`
- `TEMPORAL_PORT=7233`
- `TEMPORAL_NAMESPACE=default`

These match the docker-compose configuration.

## Notes

- Temporal takes about 60 seconds to fully start up
- The Web UI is available at http://localhost:8233
- Tests use the default namespace
