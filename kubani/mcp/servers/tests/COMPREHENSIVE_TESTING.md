# Comprehensive Pre-Deployment Testing for MCP Servers

## Overview

Comprehensive pre-deployment testing ensures that every tool of every MCP server works correctly with real backends before deploying to the cluster. This catches bugs early and provides confidence that deployments will succeed.

## Testing Approach

### 1. Test Every Tool

For each MCP server, we test:
- **Basic Functionality**: Can the tool be called without errors?
- **Correct Results**: Does the tool produce correct results with real backends?
- **Error Handling**: Does the tool handle invalid inputs gracefully?

### 2. Use Real Backends

Tests connect to real backend services (Discord API, Temporal, Qdrant, Neo4j, Redis) using credentials from `config/local.yaml`. This ensures tests validate actual behavior, not mocked behavior.

### 3. Configurable Testing

Tests are configurable via `config/local.yaml`:
- If a backend is not configured, tests skip gracefully
- Credentials are loaded from config, never hardcoded
- Test data (channel IDs, namespaces, etc.) comes from config

### 4. Automatic Cleanup

Tests create and clean up their own data:
- Messages, channels, webhooks (Discord)
- Workflows, schedules (Temporal)
- Collections, points (Qdrant)
- Learnings, knowledge, cache entries (Memory)

This ensures tests are idempotent and don't leave artifacts.

### 5. Stdio Transport

Tests use stdio transport to run servers locally:
- No need for deployed servers
- Fast startup and teardown
- Easy debugging with local logs

## Configuration

### config/local.yaml Structure

```yaml
# Discord Configuration
discord:
  bot_token: "YOUR_BOT_TOKEN"
  guild_id: "YOUR_GUILD_ID"
  alerts_channel: "CHANNEL_ID_FOR_TESTING"

# Temporal Configuration
temporal:
  host: "localhost:7233"
  namespace: "default"
  enabled: true

# Qdrant Configuration
memory:
  qdrant:
    host: "qdrant.almckay.io"
    port: 443
    api_key: "YOUR_API_KEY"
    https: true

# Neo4j Configuration
memory:
  neo4j:
    uri: "bolt://neo4j.almckay.io:7687"
    user: "neo4j"
    password: "YOUR_PASSWORD"

# Redis Configuration
memory:
  redis:
    host: "redis.almckay.io"
    port: 6379
    password: "YOUR_PASSWORD"
```

## Test Organization

### Per-Server Test Files

Each server has a comprehensive test file:

```
kubani/mcp/servers/
├── discord/
│   └── tests/
│       └── test_comprehensive.py
├── temporal/
│   └── tests/
│       └── test_comprehensive.py
├── qdrant/
│   └── tests/
│       └── test_comprehensive.py
├── memory/
│   └── tests/
│       └── test_comprehensive.py
└── skills/
    └── tests/
        └── test_comprehensive.py
```

### Shared Utilities

Common testing utilities are shared:

```
kubani/mcp/servers/tests/
└── comprehensive_test_utils.py
    ├── load_test_config()
    ├── start_mcp_server_stdio()
    ├── cleanup_test_data()
    └── skip_if_not_configured()
```

## Test Patterns

### Pattern 1: Basic Tool Test

```python
@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_tool_basic(server_config):
    """Test basic tool functionality."""
    if not server_config.enabled:
        pytest.skip("Server not configured")
    
    async with start_mcp_server_stdio("server_name", server_config) as session:
        result = await session.call_tool("tool_name", {
            "param1": "value1",
            "param2": "value2"
        })
        
        assert result["expected_field"] is not None
```

### Pattern 2: Create and Cleanup Test

```python
@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_tool_with_cleanup(server_config):
    """Test tool with automatic cleanup."""
    if not server_config.enabled:
        pytest.skip("Server not configured")
    
    async with start_mcp_server_stdio("server_name", server_config) as session:
        # Create test data
        create_result = await session.call_tool("create_something", {
            "name": "test-item"
        })
        
        item_id = create_result["id"]
        
        try:
            # Verify creation
            get_result = await session.call_tool("get_something", {
                "id": item_id
            })
            
            assert get_result["name"] == "test-item"
            
        finally:
            # Clean up
            await session.call_tool("delete_something", {
                "id": item_id
            })
```

### Pattern 3: Error Handling Test

```python
@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_tool_error_handling(server_config):
    """Test tool error handling."""
    if not server_config.enabled:
        pytest.skip("Server not configured")
    
    async with start_mcp_server_stdio("server_name", server_config) as session:
        # Try invalid input
        try:
            await session.call_tool("tool_name", {
                "invalid_param": "bad_value"
            })
            assert False, "Expected error"
        except Exception as e:
            # Verify error is informative
            assert "invalid" in str(e).lower() or "error" in str(e).lower()
```

## Running Tests

### Run All Comprehensive Tests

```bash
# All servers
uv run python kubani/mcp/servers/test_runner.py --all --comprehensive

# Specific server
uv run python kubani/mcp/servers/test_runner.py --server discord --comprehensive
```

### Run via Justfile

```bash
# All servers
just mcp-test-comprehensive

# Specific server
just mcp-test-comprehensive discord
```

### Run Directly with Pytest

```bash
# All comprehensive tests
uv run pytest kubani/mcp/servers/*/tests/test_comprehensive.py -v -m comprehensive

# Specific server
uv run pytest kubani/mcp/servers/discord/tests/test_comprehensive.py -v -m comprehensive
```

## CI/CD Integration

Comprehensive tests should run before deployment:

```yaml
# .github/workflows/mcp-pre-deployment.yml
name: MCP Pre-Deployment Tests

on:
  push:
    paths:
      - 'kubani/mcp/servers/**'

jobs:
  comprehensive-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install uv
          uv sync
      
      - name: Run comprehensive tests
        env:
          DISCORD_BOT_TOKEN: ${{ secrets.DISCORD_BOT_TOKEN }}
          DISCORD_GUILD_ID: ${{ secrets.DISCORD_GUILD_ID }}
          # ... other secrets
        run: |
          uv run python kubani/mcp/servers/test_runner.py --all --comprehensive
```

## Benefits

1. **Early Bug Detection**: Catch issues before deployment
2. **Real Backend Validation**: Test with actual services, not mocks
3. **Confidence**: Know that tools work correctly
4. **Fast Feedback**: Run locally before pushing
5. **Comprehensive Coverage**: Every tool tested
6. **Clean Tests**: Automatic cleanup prevents pollution

## Best Practices

1. **Always Clean Up**: Use try/finally to ensure cleanup
2. **Skip Gracefully**: Don't fail if backend not configured
3. **Use Test Data**: Never use production data
4. **Informative Errors**: Verify error messages are helpful
5. **Idempotent Tests**: Tests should be runnable multiple times
6. **Fast Tests**: Keep tests focused and quick

## Example: Discord MCP

See `scratch/test_comprehensive_example.py` for a complete example of comprehensive testing for Discord and Temporal MCP servers.

## Troubleshooting

### Tests Skip Due to Missing Config

**Problem**: Tests skip with "Server not configured"

**Solution**: Add credentials to `config/local.yaml`

### Tests Fail to Connect to Backend

**Problem**: Connection errors to backend services

**Solution**: 
- Verify backend is running and accessible
- Check credentials in config/local.yaml
- Verify network connectivity (Tailscale, port forwarding)

### Tests Leave Artifacts

**Problem**: Test data not cleaned up

**Solution**:
- Ensure cleanup code is in `finally` block
- Check that cleanup tools work correctly
- Manually clean up if needed

### Tests Are Slow

**Problem**: Tests take too long to run

**Solution**:
- Run tests for specific server only
- Use `--comprehensive` flag to run only comprehensive tests
- Optimize test data size (smaller messages, fewer items)

## Future Enhancements

1. **Parallel Execution**: Run tests for different servers in parallel
2. **Test Data Generators**: Use Hypothesis for property-based testing
3. **Performance Benchmarks**: Track tool execution time
4. **Coverage Reports**: Measure tool coverage
5. **Visual Reports**: Generate HTML test reports
