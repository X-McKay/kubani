# Memory MCP Integration Tests

This directory contains integration tests for the Memory MCP server that test against real backend services.

## Running Integration Tests

### Prerequisites

- Docker and Docker Compose installed
- Python environment with test dependencies

### Setup

1. Start the backend services:
```bash
cd kubani/mcp/servers/memory
docker-compose -f docker-compose.integration.yml up -d
```

2. Wait for services to be healthy (about 30 seconds):
```bash
docker-compose -f docker-compose.integration.yml ps
```

All services should show "healthy" status.

### Running Tests

Run integration tests with pytest:

```bash
# From the memory-mcp directory
uv run pytest tests/test_integration.py -v

# Or from the workspace root
uv run pytest kubani/mcp/servers/memory/tests/test_integration.py -v
```

### Cleanup

Stop and remove the backend services:

```bash
docker-compose -f docker-compose.integration.yml down -v
```

The `-v` flag removes the volumes, ensuring a clean state for the next test run.

## Test Coverage

Integration tests cover:

- **Qdrant (Vector Backend)**:
  - Storing and querying learnings with semantic search
  - Vector similarity search
  - Metadata filtering

- **Neo4j (Graph Backend)**:
  - Storing knowledge with relationships
  - Graph traversal and relationship queries
  - Knowledge graph construction

- **Redis (Cache Backend)**:
  - Cache set/get/delete operations
  - TTL expiration
  - Deduplication with seen keys

## Environment Variables

The integration tests use the following environment variables (with defaults):

- `QDRANT_HOST=localhost`
- `QDRANT_PORT=6333`
- `NEO4J_URI=bolt://localhost:7687`
- `NEO4J_USER=neo4j`
- `NEO4J_PASSWORD=testpassword`
- `REDIS_HOST=localhost`
- `REDIS_PORT=6379`

These match the docker-compose configuration.
