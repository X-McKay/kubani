# MCP Server Test Runner

Unified test runner for all MCP servers in the Kubani platform.

## Overview

The test runner provides a standardized way to run all types of tests for MCP servers:
- **Unit tests**: Core business logic
- **Contract tests**: Tool interface validation
- **Integration tests**: Backend connectivity
- **Property tests**: Property-based testing
- **Deployment tests**: Post-deployment validation

## Quick Start

### Using Just (Recommended)

```bash
# Run all tests for all servers
just mcp-test

# Run tests for specific server
just mcp-test-server discord

# Run specific test type
just mcp-test-unit discord
just mcp-test-integration memory
just mcp-test-contract

# Run post-deployment tests
just mcp-test-deployed

# List available servers
just mcp-test-list
```

### Using Python Directly

```bash
# From kubani/mcp/servers directory
cd kubani/mcp/servers

# Run all tests for all servers
uv run python test_runner.py --all

# Run tests for specific server
uv run python test_runner.py --server discord

# Run specific test type
uv run python test_runner.py --server discord --unit
uv run python test_runner.py --server discord --integration

# Run multiple test types
uv run python test_runner.py --server memory --unit --contract

# Run post-deployment tests
uv run python test_runner.py --deployed

# Run with verbose output
uv run python test_runner.py --server discord --unit --verbose
```

## Test Types

### Unit Tests
Tests core business logic in isolation. Located in `<server>/tests/test_*.py`.

```bash
just mcp-test-unit discord
```

### Contract Tests
Validates that servers implement their contracted tool interfaces. Contracts are defined in `tests/contracts.py`.

```bash
just mcp-test-contract discord
```

### Integration Tests
Tests servers with real backend dependencies (Redis, Qdrant, Neo4j, etc.). Requires docker-compose services to be running.

```bash
# Start backend services first
cd kubani/mcp/servers/memory
docker-compose -f docker-compose.integration.yml up -d

# Run integration tests
just mcp-test-integration memory

# Stop services
docker-compose -f docker-compose.integration.yml down
```

### Property-Based Tests
Uses Hypothesis to generate diverse inputs and validate tool robustness.

```bash
just mcp-test-property discord
```

### Post-Deployment Tests
Validates deployed MCP servers are accessible and functional in the cluster.

```bash
just mcp-test-deployed
```

## Available Servers

- `discord` - Discord MCP Server
- `memory` - Memory MCP Server (Qdrant, Neo4j, Redis)
- `temporal` - Temporal MCP Server
- `qdrant` - Qdrant MCP Server
- `skills` - Skills MCP Server

## Test Output

The test runner provides clear, formatted output:

```
============================================================
Running unit tests for discord
============================================================

✓ UNIT tests: passed

============================================================
TEST SUMMARY
============================================================

discord:
  ✓ unit         passed
  ✓ contract     passed
  ⊘ integration  skipped

============================================================
Total: 3 | Passed: 2 | Failed: 0 | Skipped: 1 | Errors: 0
============================================================
```

## CI/CD Integration

The test runner is designed for CI/CD pipelines:

```yaml
# GitHub Actions example
- name: Run MCP Server Tests
  run: |
    just mcp-test

- name: Run Post-Deployment Tests
  run: |
    just mcp-test-deployed
```

## Development Workflow

1. **Write code** for your MCP server
2. **Write tests** (unit, contract, integration)
3. **Run tests locally**:
   ```bash
   just mcp-test-server myserver
   ```
4. **Fix any failures**
5. **Commit and push** - CI will run all tests

## Troubleshooting

### Tests not found
Ensure you're running from the correct directory:
```bash
cd kubani/mcp/servers
uv run python test_runner.py --server discord
```

### Integration tests fail
Make sure backend services are running:
```bash
cd kubani/mcp/servers/<server>
docker-compose -f docker-compose.integration.yml up -d
```

### Contract tests fail
Check that your server implements all contracted tools in `tests/contracts.py`.

## Requirements

- Python 3.12+
- uv package manager
- Docker (for integration tests)
- pytest, hypothesis (installed via uv)

## Related Documentation

- [MCP Server Development Guide](../../../docs/mcp-servers/development-guide.md)
- [MCP Server Testing Guide](../../../docs/mcp-servers/testing-guide.md)
- [MCP Server Deployment Guide](../../../docs/mcp-servers/deployment-guide.md)
