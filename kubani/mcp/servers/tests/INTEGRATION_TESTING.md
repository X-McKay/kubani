# MCP Server Integration Testing Infrastructure

This document describes the integration testing infrastructure for all MCP servers in the Kubani platform.

## Overview

Integration tests validate that MCP servers work correctly with their real backend dependencies (databases, APIs, etc.). Each MCP server has:

1. A `docker-compose.integration.yml` file to start backend services
2. Integration tests in `tests/test_integration.py`
3. A `tests/README.md` with setup and usage instructions

## MCP Servers with Integration Tests

### 1. Memory MCP Server

**Location**: `kubani/mcp/servers/memory/`

**Backends**:
- Qdrant (vector database)
- Neo4j (graph database)
- Redis (cache)

**Test Coverage**:
- Storing and querying learnings with semantic search
- Knowledge graph operations with Neo4j
- Cache operations with Redis
- Generic memory operations (add, search, get, link)
- Deduplication with seen keys

**Setup**:
```bash
cd kubani/mcp/servers/memory
docker-compose -f docker-compose.integration.yml up -d
uv run pytest tests/test_integration.py -v
docker-compose -f docker-compose.integration.yml down -v
```

### 2. Discord MCP Server

**Location**: `kubani/mcp/servers/discord/`

**Backends**:
- Mock Discord API (using MockServer)

**Test Coverage**:
- Sending messages to channels
- Retrieving messages
- Adding and getting reactions
- Channel operations (list, create, delete)
- Webhook operations

**Setup**:
```bash
cd kubani/mcp/servers/discord
docker-compose -f docker-compose.integration.yml up -d
uv run pytest tests/test_integration.py -v
docker-compose -f docker-compose.integration.yml down -v
```

**Note**: Discord tests use mocks since we can't easily test against the real Discord API in CI.

### 3. Temporal MCP Server

**Location**: `kubani/mcp/servers/temporal/`

**Backends**:
- Temporal server
- PostgreSQL (for Temporal)

**Test Coverage**:
- Listing workflows
- Getting workflow details
- Listing schedules
- Health checks

**Setup**:
```bash
cd kubani/mcp/servers/temporal
docker-compose -f docker-compose.integration.yml up -d
# Wait ~60 seconds for Temporal to fully start
uv run pytest tests/test_integration.py -v
docker-compose -f docker-compose.integration.yml down -v
```

**Note**: Some tests are skipped as they require workflow definitions and workers to be running.

### 4. Qdrant MCP Server

**Location**: `kubani/mcp/servers/qdrant/`

**Backends**:
- Qdrant (vector database)

**Test Coverage**:
- Creating and managing collections
- Upserting vectors with payloads
- Searching for similar vectors
- Filtering by metadata
- Getting and deleting points
- Scrolling through points
- Counting points

**Setup**:
```bash
cd kubani/mcp/servers/qdrant
docker-compose -f docker-compose.integration.yml up -d
uv run pytest tests/test_integration.py -v
docker-compose -f docker-compose.integration.yml down -v
```

### 5. Skills MCP Server

**Location**: `kubani/mcp/servers/skills/`

**Backends**:
- Filesystem or OCI registry (for skill discovery)

**Test Coverage**:
- Listing skills
- Searching for skills
- Server initialization

**Setup**:
```bash
cd kubani/mcp/servers/skills
uv run pytest tests/test_integration.py -v
```

**Note**: Skills MCP doesn't require docker-compose as it uses filesystem or OCI registry.

## Running All Integration Tests

To run integration tests for all servers:

```bash
# Start all backend services
cd kubani/mcp/servers/memory
docker-compose -f docker-compose.integration.yml up -d

cd ../discord
docker-compose -f docker-compose.integration.yml up -d

cd ../temporal
docker-compose -f docker-compose.integration.yml up -d

cd ../qdrant
docker-compose -f docker-compose.integration.yml up -d

# Wait for services to be healthy
sleep 60

# Run all integration tests
cd ../../..
uv run pytest kubani/mcp/servers/*/tests/test_integration.py -v -m integration

# Cleanup
cd kubani/mcp/servers/memory
docker-compose -f docker-compose.integration.yml down -v
cd ../discord
docker-compose -f docker-compose.integration.yml down -v
cd ../temporal
docker-compose -f docker-compose.integration.yml down -v
cd ../qdrant
docker-compose -f docker-compose.integration.yml down -v
```

## Test Markers

All integration tests are marked with `@pytest.mark.integration`. To run only integration tests:

```bash
uv run pytest -m integration
```

To skip integration tests:

```bash
uv run pytest -m "not integration"
```

## CI/CD Integration

Integration tests can be run in CI/CD pipelines:

1. Use GitHub Actions services to start backend containers
2. Run integration tests against those services
3. Cleanup is automatic when the job completes

Example GitHub Actions workflow:

```yaml
jobs:
  integration-tests:
    runs-on: ubuntu-latest
    services:
      qdrant:
        image: qdrant/qdrant:v1.7.4
        ports:
          - 6333:6333
      neo4j:
        image: neo4j:5.15.0
        ports:
          - 7687:7687
        env:
          NEO4J_AUTH: neo4j/testpassword
      redis:
        image: redis:7.2-alpine
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v3
      - name: Run integration tests
        run: uv run pytest -m integration
```

## Best Practices

1. **Isolation**: Each test should be independent and not rely on state from other tests
2. **Cleanup**: Always clean up test data after tests complete
3. **Timeouts**: Use reasonable timeouts for backend operations
4. **Markers**: Mark all integration tests with `@pytest.mark.integration`
5. **Documentation**: Keep README files up to date with setup instructions
6. **Fixtures**: Use pytest fixtures for backend connections and test data
7. **Skipping**: Skip tests that require specific setup (e.g., running workflows)

## Troubleshooting

### Backend Not Ready

If tests fail with connection errors, backends may not be fully started:
- Wait longer before running tests (especially Temporal)
- Check backend health: `docker-compose ps`
- Check backend logs: `docker-compose logs <service>`

### Port Conflicts

If backends fail to start due to port conflicts:
- Check what's using the ports: `lsof -i :<port>`
- Stop conflicting services or change ports in docker-compose

### Test Data Conflicts

If tests fail due to existing data:
- Use unique IDs (uuid4) for test data
- Clean up test data in fixtures
- Use `docker-compose down -v` to remove volumes

## Future Improvements

1. Add unified test runner script
2. Add parallel test execution
3. Add test coverage reporting
4. Add performance benchmarks
5. Add chaos testing (backend failures)
6. Add load testing for concurrent requests
