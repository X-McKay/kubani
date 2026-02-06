# MCP Server Testing Guide

This guide covers the comprehensive testing strategy for MCP servers in the Kubani platform. We use a multi-layered approach to ensure correctness, reliability, and robustness.

## Table of Contents

- [Overview](#overview)
- [Testing Layers](#testing-layers)
- [Unit Testing](#unit-testing)
- [Contract Testing](#contract-testing)
- [Integration Testing](#integration-testing)
- [Property-Based Testing](#property-based-testing)
- [Comprehensive Pre-Deployment Testing](#comprehensive-pre-deployment-testing)
- [Running Tests](#running-tests)
- [Test Organization](#test-organization)

## Overview

MCP servers use four complementary testing layers:

1. **Unit Tests** - Test individual functions and business logic
2. **Contract Tests** - Verify servers implement their tool contracts
3. **Integration Tests** - Test with real backend services
4. **Property-Based Tests** - Verify universal properties with generated inputs
5. **Comprehensive Tests** - Pre-deployment tests of all tools with real backends

Each layer serves a specific purpose and catches different types of bugs.

## Testing Layers

```
┌─────────────────────────────────────────────────────────┐
│  Property-Based Tests                                   │
│  - Universal properties across all inputs               │
│  - Robustness with edge cases                           │
└─────────────────────────────────────────────────────────┘
                          ▲
┌─────────────────────────────────────────────────────────┐
│  Integration Tests (Docker Compose)                     │
│  - MCP server + real backends                           │
│  - End-to-end tool execution                            │
└─────────────────────────────────────────────────────────┘
                          ▲
┌─────────────────────────────────────────────────────────┐
│  Contract Tests                                         │
│  - Verify all contracted tools exist                    │
│  - Validate tool schemas                                │
└─────────────────────────────────────────────────────────┘
                          ▲
┌─────────────────────────────────────────────────────────┐
│  Unit Tests                                             │
│  - Business logic                                       │
│  - Input validation                                     │
└─────────────────────────────────────────────────────────┘
```

## Unit Testing

Unit tests verify individual functions and business logic in isolation.

### Location

```
kubani/mcp/servers/myserver/tests/
├── test_validation.py
├── test_helpers.py
└── test_models.py
```

### Example

```python
"""Unit tests for myserver validation logic."""

import pytest
from myserver_mcp.validation import validate_input, ValidationError


def test_validate_input_success():
    """Test validation with valid input."""
    result = validate_input("valid_data", min_length=5)
    assert result is True


def test_validate_input_too_short():
    """Test validation rejects short input."""
    with pytest.raises(ValidationError, match="too short"):
        validate_input("abc", min_length=5)


def test_validate_input_empty():
    """Test validation rejects empty input."""
    with pytest.raises(ValidationError, match="empty"):
        validate_input("", min_length=1)


@pytest.mark.parametrize(
    "input_data,expected",
    [
        ("test", True),
        ("a" * 100, True),
        ("", False),
        ("a" * 1001, False),
    ],
)
def test_validate_input_parametrized(input_data, expected):
    """Test validation with multiple inputs."""
    if expected:
        assert validate_input(input_data, min_length=1, max_length=1000)
    else:
        with pytest.raises(ValidationError):
            validate_input(input_data, min_length=1, max_length=1000)
```

### Best Practices

- Test one thing per test
- Use descriptive test names
- Test both success and failure cases
- Use `pytest.mark.parametrize` for multiple similar cases
- Mock external dependencies

## Contract Testing

Contract tests verify that your MCP server implements all tools defined in its contract.

### Define a Contract

Create `kubani/mcp/servers/tests/contracts.py`:

```python
"""MCP server contracts."""

from kubani.framework.mcp.server.testing.contracts import MCPContract, ToolContract

MYSERVER_CONTRACT = MCPContract(
    server_name="myserver-mcp",
    tools=[
        ToolContract(
            name="my_tool_1",
            description="First tool",
            parameters={
                "param1": str,
                "param2": int,
            },
            required_parameters=["param1", "param2"],
        ),
        ToolContract(
            name="my_tool_2",
            description="Second tool",
            parameters={
                "data": str,
                "optional_flag": bool,
            },
            required_parameters=["data"],
        ),
    ],
)
```

### Write Contract Tests

Create `kubani/mcp/servers/myserver/tests/test_contract.py`:

```python
"""Contract tests for myserver MCP."""

import pytest
from kubani.framework.mcp.server.testing.validator import ContractValidator
from kubani.mcp.servers.tests.contracts import MYSERVER_CONTRACT
from myserver_mcp.server import MyServerMCP


def test_contract_completeness():
    """
    Verify myserver-mcp implements all contracted tools.
    
    **Feature: mcp-infrastructure-improvements, Property 3: Contract Completeness**
    """
    server = MyServerMCP()
    validator = ContractValidator(server, MYSERVER_CONTRACT)
    
    result = validator.validate()
    
    # Print errors for debugging
    if not result.passed:
        for error in result.errors:
            print(f"Error: {error.message}")
    
    assert result.passed, f"Contract validation failed with {result.error_count} errors"


def test_all_tools_exist():
    """Verify all contracted tools are registered."""
    server = MyServerMCP()
    validator = ContractValidator(server, MYSERVER_CONTRACT)
    
    errors = validator.validate_tool_existence()
    
    assert len(errors) == 0, f"Missing tools: {[e.tool_name for e in errors]}"


def test_tool_parameters_match():
    """Verify tool parameters match contract."""
    server = MyServerMCP()
    validator = ContractValidator(server, MYSERVER_CONTRACT)
    
    errors, warnings = validator.validate_parameter_schemas()
    
    # Errors are failures, warnings are informational
    assert len(errors) == 0, f"Parameter validation errors: {[e.message for e in errors]}"
```

### Contract Testing Best Practices

- Define contracts before implementation
- Keep contracts up-to-date with changes
- Include all required parameters
- Specify parameter types
- Run contract tests in CI/CD

## Integration Testing

Integration tests verify MCP servers work correctly with real backend services.

### Setup with Docker Compose

Create `kubani/mcp/servers/myserver/docker-compose.test.yml`:

```yaml
version: '3.8'

services:
  # Your backend services
  postgres:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: testpass
      POSTGRES_DB: testdb
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
```

### Write Integration Tests

Create `kubani/mcp/servers/myserver/tests/test_integration.py`:

```python
"""Integration tests for myserver MCP."""

import asyncio
import os

import pytest
from myserver_mcp.server import MyServerMCP


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def backend_services():
    """
    Ensure backend services are running.
    
    Assumes docker-compose.test.yml is running.
    """
    # Set test environment variables
    os.environ["POSTGRES_HOST"] = "localhost"
    os.environ["POSTGRES_PORT"] = "5432"
    os.environ["POSTGRES_DB"] = "testdb"
    os.environ["POSTGRES_USER"] = "postgres"
    os.environ["POSTGRES_PASSWORD"] = "testpass"
    os.environ["REDIS_URL"] = "redis://localhost:6379"
    
    # Wait for services to be ready
    await asyncio.sleep(2)
    
    yield
    
    # Cleanup if needed


@pytest.fixture
async def server(backend_services):
    """Create and initialize MCP server."""
    server = MyServerMCP()
    await server.initialize()
    yield server
    await server.shutdown()


@pytest.mark.integration
async def test_store_and_retrieve(server):
    """Test storing and retrieving data with real backend."""
    # Store data
    store_result = await server.call_tool("store_data", {
        "key": "test_key",
        "value": "test_value",
    })
    
    assert store_result["status"] == "success"
    
    # Retrieve data
    retrieve_result = await server.call_tool("retrieve_data", {
        "key": "test_key",
    })
    
    assert retrieve_result["status"] == "success"
    assert retrieve_result["value"] == "test_value"


@pytest.mark.integration
async def test_backend_connectivity(server):
    """Test that server can connect to all backends."""
    # Test database connection
    db_result = await server.call_tool("check_database", {})
    assert db_result["connected"] is True
    
    # Test cache connection
    cache_result = await server.call_tool("check_cache", {})
    assert cache_result["connected"] is True


@pytest.mark.integration
async def test_concurrent_requests(server):
    """Test handling multiple concurrent requests."""
    # Create multiple concurrent requests
    tasks = [
        server.call_tool("store_data", {"key": f"key_{i}", "value": f"value_{i}"})
        for i in range(10)
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # All should succeed
    assert all(not isinstance(r, Exception) for r in results)
    assert all(r["status"] == "success" for r in results)
```

### Running Integration Tests

```bash
# Start backend services
cd kubani/mcp/servers/myserver
docker-compose -f docker-compose.test.yml up -d

# Wait for services to be ready
sleep 5

# Run integration tests
uv run pytest tests/test_integration.py -v -m integration

# Cleanup
docker-compose -f docker-compose.test.yml down
```

### Integration Testing Best Practices

- Use docker-compose for reproducible environments
- Wait for services to be healthy before testing
- Clean up data between tests
- Test realistic scenarios
- Test error conditions (backend failures)

## Property-Based Testing

Property-based tests verify universal properties that should hold for all inputs.

### Using Hypothesis

Install Hypothesis:

```toml
[project.optional-dependencies]
test = [
    "pytest>=7.0.0",
    "hypothesis>=6.0.0",
]
```

### Write Property Tests

Create `tests/properties/test_myserver_properties.py`:

```python
"""Property-based tests for myserver MCP."""

import asyncio

import pytest
from hypothesis import given, strategies as st
from myserver_mcp.server import MyServerMCP


@pytest.fixture
async def server():
    """Create MCP server for testing."""
    server = MyServerMCP()
    await server.initialize()
    yield server
    await server.shutdown()


@given(
    key=st.text(min_size=1, max_size=100),
    value=st.text(min_size=0, max_size=1000),
)
@pytest.mark.asyncio
async def test_store_retrieve_roundtrip(server, key, value):
    """
    Property: Any stored data can be retrieved unchanged.
    
    **Feature: mcp-infrastructure-improvements, Property X: Data Persistence**
    **Validates: Requirements 1.1**
    """
    # Store data
    store_result = await server.call_tool("store_data", {
        "key": key,
        "value": value,
    })
    
    assert store_result["status"] == "success"
    
    # Retrieve data
    retrieve_result = await server.call_tool("retrieve_data", {
        "key": key,
    })
    
    # Property: Retrieved value equals stored value
    assert retrieve_result["value"] == value


@given(
    agent_id=st.text(min_size=1, max_size=50),
    data=st.text(min_size=1, max_size=500),
)
@pytest.mark.asyncio
async def test_data_namespacing(server, agent_id, data):
    """
    Property: Data is properly namespaced by agent_id.
    
    **Feature: mcp-infrastructure-improvements, Property 2: Data Namespacing**
    **Validates: Requirements 1.4**
    """
    # Store data for this agent
    await server.call_tool("store_agent_data", {
        "agent_id": agent_id,
        "data": data,
    })
    
    # Retrieve data for this agent
    result = await server.call_tool("get_agent_data", {
        "agent_id": agent_id,
    })
    
    # Property: Retrieved data matches stored data
    assert result["data"] == data
    
    # Property: Data includes agent_id namespace
    assert result["agent_id"] == agent_id


@given(
    input_str=st.text(min_size=0, max_size=100),
)
@pytest.mark.asyncio
async def test_validation_consistency(server, input_str):
    """
    Property: Validation is consistent across all inputs.
    
    **Feature: mcp-infrastructure-improvements, Property Y: Input Validation**
    **Validates: Requirements 2.1**
    """
    try:
        result = await server.call_tool("validate_input", {
            "input": input_str,
        })
        
        # If validation passes, result should be valid
        assert result["valid"] is True
        
    except ValueError as e:
        # If validation fails, error message should be clear
        assert len(str(e)) > 0
```

### Property Testing Best Practices

- Focus on universal properties, not specific examples
- Use appropriate strategies for your domain
- Configure sufficient test iterations (100+)
- Tag tests with property numbers from design doc
- Test invariants, round-trips, and metamorphic properties

### Common Property Patterns

1. **Round-Trip Properties**
   ```python
   @given(data=st.text())
   async def test_encode_decode_roundtrip(data):
       """Property: decode(encode(x)) == x"""
       encoded = await encode(data)
       decoded = await decode(encoded)
       assert decoded == data
   ```

2. **Invariant Properties**
   ```python
   @given(items=st.lists(st.integers()))
   async def test_sort_preserves_length(items):
       """Property: Sorting preserves list length"""
       sorted_items = await sort(items)
       assert len(sorted_items) == len(items)
   ```

3. **Idempotence Properties**
   ```python
   @given(data=st.text())
   async def test_operation_idempotent(data):
       """Property: f(f(x)) == f(x)"""
       result1 = await operation(data)
       result2 = await operation(result1)
       assert result1 == result2
   ```

4. **Metamorphic Properties**
   ```python
   @given(items=st.lists(st.integers()))
   async def test_filter_reduces_size(items):
       """Property: Filtering never increases size"""
       filtered = await filter_items(items)
       assert len(filtered) <= len(items)
   ```

## Comprehensive Pre-Deployment Testing

Comprehensive tests verify that every tool in every MCP server works correctly with real backends before deployment. These tests catch integration issues early and ensure production readiness.

### Overview

Comprehensive tests:
- Test **all tools** with valid inputs
- Test **error handling** with invalid inputs
- Verify **correct behavior** with real backends
- **Clean up** all test data after completion
- **Skip gracefully** when backends are unavailable

### Configuration

Comprehensive tests load credentials from `config/local.yaml`:

```yaml
# config/local.yaml
discord:
  bot_token: "your-discord-bot-token"
  guild_id: "your-guild-id"
  alerts_channel: "channel-id-for-testing"

temporal:
  enabled: true
  host: "temporal.almckay.io:7233"
  namespace: "default"
  task_queue: "kubani-tasks"

memory:
  qdrant:
    host: "qdrant.almckay.io"
    port: 6333
    https: true
    api_key: "your-qdrant-api-key"
  neo4j:
    uri: "bolt://neo4j.almckay.io:7687"
    user: "neo4j"
    password: "your-neo4j-password"
  redis:
    host: "redis.almckay.io"
    port: 6379
    password: "your-redis-password"
```

### Writing Comprehensive Tests

Create `kubani/mcp/servers/myserver/tests/test_comprehensive.py`:

```python
"""
Comprehensive pre-deployment tests for MyServer MCP.

Tests all tools with valid inputs and error handling.
Verifies correct behavior with real backends.
Cleans up all test data after completion.

Requirements: 11.1, 11.2, 11.3, 11.6
"""

import logging

import pytest

from kubani.mcp.servers.tests.comprehensive_test_utils import (
    cleanup_test_data,
    get_test_resource_prefix,
    load_test_config,
    start_mcp_server_stdio,
)

logger = logging.getLogger(__name__)

# Load configuration
config = load_test_config("myserver")

# Skip all tests if backend not configured
pytestmark = pytest.mark.skipif(
    not config.enabled,
    reason="MyServer not configured in config/local.yaml",
)


@pytest.fixture
def test_prefix():
    """Get unique prefix for test resources."""
    return get_test_resource_prefix()


@pytest.fixture
def created_resources():
    """Track created resources for cleanup."""
    return {
        "items": [],
        "collections": [],
    }


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_create_item_comprehensive(test_prefix, created_resources):
    """Test create_item tool with valid inputs."""
    async with start_mcp_server_stdio("myserver", config) as session:
        item_name = f"{test_prefix}-item"

        # Create item
        result = await session.call_tool(
            "create_item",
            {"name": item_name, "data": "test data"},
        )

        assert result["item_id"] is not None
        assert result["name"] == item_name

        # Track for cleanup
        created_resources["items"].append(result["item_id"])

        # Verify item was created
        get_result = await session.call_tool(
            "get_item",
            {"item_id": result["item_id"]},
        )

        assert get_result["item_id"] == result["item_id"]
        assert get_result["data"] == "test data"

        # Cleanup
        await cleanup_test_data("myserver", session, config, created_resources)


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_create_item_error_handling():
    """Test create_item error handling with invalid inputs."""
    async with start_mcp_server_stdio("myserver", config) as session:
        # Test with missing required field
        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "create_item",
                {"name": ""},  # Empty name should fail
            )

        error_msg = str(exc_info.value).lower()
        assert "invalid" in error_msg or "required" in error_msg


@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_list_items_comprehensive():
    """Test list_items tool."""
    async with start_mcp_server_stdio("myserver", config) as session:
        result = await session.call_tool("list_items", {})

        assert "items" in result
        assert isinstance(result["items"], list)


# Add more comprehensive tests for each tool...
```

### Test Utilities

The comprehensive test utilities provide:

1. **Configuration Loading**
   ```python
   from kubani.mcp.servers.tests.comprehensive_test_utils import load_test_config
   
   config = load_test_config("discord")
   if not config.enabled:
       pytest.skip("Discord not configured")
   ```

2. **Server Startup**
   ```python
   from kubani.mcp.servers.tests.comprehensive_test_utils import start_mcp_server_stdio
   
   async with start_mcp_server_stdio("discord", config) as session:
       result = await session.call_tool("list_channels", {})
   ```

3. **Test Data Cleanup**
   ```python
   from kubani.mcp.servers.tests.comprehensive_test_utils import cleanup_test_data
   
   created_resources = {
       "messages": [message_id],
       "message_channels": {message_id: channel_id},
   }
   
   await cleanup_test_data("discord", session, config, created_resources)
   ```

4. **Resource Prefixing**
   ```python
   from kubani.mcp.servers.tests.comprehensive_test_utils import get_test_resource_prefix
   
   prefix = get_test_resource_prefix()
   channel_name = f"{prefix}-test-channel"
   ```

### Running Comprehensive Tests

```bash
# Run comprehensive tests for all servers
just mcp-test-comprehensive

# Run comprehensive tests for specific server
just mcp-test-comprehensive discord

# Run with pytest directly
cd kubani/mcp/servers/discord
uv run pytest tests/test_comprehensive.py -v -m comprehensive
```

### Comprehensive Testing Best Practices

1. **Test All Tools** - Every tool should have at least one comprehensive test
2. **Test Error Handling** - Test each tool with invalid inputs
3. **Clean Up Data** - Always clean up test data, even if tests fail
4. **Use Real Backends** - Don't mock backends in comprehensive tests
5. **Skip Gracefully** - Skip tests when backends are unavailable
6. **Unique Prefixes** - Use unique prefixes to avoid conflicts
7. **Track Resources** - Track all created resources for cleanup

### Example: Discord Comprehensive Tests

```python
@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_discord_message_round_trip(created_resources):
    """Test sending, retrieving, and deleting a message."""
    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data["test_channel_id"]
        
        # Send message
        send_result = await session.call_tool(
            "send_message",
            {"channel_id": channel_id, "content": "Test message"},
        )
        
        message_id = send_result["message_id"]
        created_resources["messages"].append(message_id)
        created_resources["message_channels"][message_id] = channel_id
        
        # Retrieve message
        get_result = await session.call_tool(
            "get_message",
            {"channel_id": channel_id, "message_id": message_id},
        )
        
        assert get_result["content"] == "Test message"
        
        # Cleanup
        await cleanup_test_data("discord", session, config, created_resources)
```

## Running Tests

### Using the Test Runner

The unified test runner provides a single interface for all test types:

```bash
# Run all tests for all servers
just mcp-test

# Run tests for specific server
just mcp-test myserver

# Run specific test type
just mcp-test myserver --unit
just mcp-test myserver --integration
just mcp-test myserver --contract
just mcp-test myserver --property
just mcp-test myserver --comprehensive

# Run with verbose output
just mcp-test myserver --verbose
```

### Using pytest Directly

```bash
# Run all tests
uv run pytest kubani/mcp/servers/myserver/tests/

# Run specific test file
uv run pytest kubani/mcp/servers/myserver/tests/test_integration.py

# Run tests by marker
uv run pytest -m integration
uv run pytest -m "not integration"

# Run with coverage
uv run pytest --cov=myserver_mcp --cov-report=html

# Run property tests with more iterations
uv run pytest tests/properties/ --hypothesis-iterations=1000
```

### CI/CD Integration

Add to `.github/workflows/test-mcp-servers.yml`:

```yaml
name: Test MCP Servers

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install uv
        run: pip install uv
      
      - name: Install dependencies
        run: uv sync
      
      - name: Run unit tests
        run: uv run pytest kubani/mcp/servers/myserver/tests/ -m "not integration"
      
      - name: Start backend services
        run: |
          cd kubani/mcp/servers/myserver
          docker-compose -f docker-compose.test.yml up -d
          sleep 10
      
      - name: Run integration tests
        run: uv run pytest kubani/mcp/servers/myserver/tests/ -m integration
      
      - name: Run property tests
        run: uv run pytest tests/properties/test_myserver_properties.py
      
      - name: Cleanup
        if: always()
        run: |
          cd kubani/mcp/servers/myserver
          docker-compose -f docker-compose.test.yml down
```

## Test Organization

### Directory Structure

```
kubani/mcp/servers/myserver/
├── src/
│   └── myserver_mcp/
│       ├── __init__.py
│       ├── server.py
│       ├── client.py
│       └── models.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures
│   ├── test_contract.py         # Contract tests
│   ├── test_integration.py      # Integration tests
│   ├── test_validation.py       # Unit tests
│   └── test_helpers.py          # Unit tests
├── docker-compose.test.yml      # Backend services for testing
└── pyproject.toml

tests/properties/
└── test_myserver_properties.py  # Property-based tests
```

### Shared Fixtures

Create `kubani/mcp/servers/myserver/tests/conftest.py`:

```python
"""Shared test fixtures."""

import asyncio
import os

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_config():
    """Test configuration."""
    return {
        "backend_url": os.environ.get("TEST_BACKEND_URL", "http://localhost:8000"),
        "timeout": 30,
    }


@pytest.fixture
async def server():
    """Create and initialize test server."""
    from myserver_mcp.server import MyServerMCP
    
    server = MyServerMCP()
    await server.initialize()
    yield server
    await server.shutdown()
```

## Next Steps

1. Write tests following this guide
2. Run tests locally to verify
3. Add tests to CI/CD pipeline
4. Review [Deployment Guide](deployment-guide.md) for deployment testing

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [Hypothesis Documentation](https://hypothesis.readthedocs.io/)
- [Development Guide](development-guide.md)
- [Deployment Guide](deployment-guide.md)
