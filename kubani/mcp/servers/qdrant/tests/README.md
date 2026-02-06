# Qdrant MCP Integration Tests

This directory contains integration tests for the Qdrant MCP server that test against a real Qdrant instance.

## Running Integration Tests

### Prerequisites

- Docker and Docker Compose installed
- Python environment with test dependencies

### Setup

1. Start the Qdrant server:
```bash
cd kubani/mcp/servers/qdrant
docker-compose -f docker-compose.integration.yml up -d
```

2. Wait for Qdrant to be healthy (about 10 seconds):
```bash
docker-compose -f docker-compose.integration.yml ps
```

The qdrant service should show "healthy" status.

### Running Tests

Run integration tests with pytest:

```bash
# From the qdrant-mcp directory
uv run pytest tests/test_integration.py -v

# Or from the workspace root
uv run pytest kubani/mcp/servers/qdrant/tests/test_integration.py -v
```

### Cleanup

Stop and remove the Qdrant server:

```bash
docker-compose -f docker-compose.integration.yml down -v
```

## Test Coverage

Integration tests cover:

- **Collection Management**:
  - Creating collections
  - Listing collections
  - Getting collection info
  - Deleting collections

- **Vector Operations**:
  - Upserting vectors with payloads
  - Searching for similar vectors
  - Getting points by ID
  - Deleting points
  - Scrolling through points

- **Utility Operations**:
  - Counting points
  - Filtering by metadata
  - Health checks

## Environment Variables

The integration tests use the following environment variables (with defaults):

- `QDRANT_HOST=localhost`
- `QDRANT_PORT=6333`

These match the docker-compose configuration.

## Notes

- Qdrant Web UI is available at http://localhost:6333/dashboard
- Tests use random collection names to avoid conflicts
- All test collections are cleaned up after tests complete
