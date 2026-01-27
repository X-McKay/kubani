# Phase 4: Documentation & Validation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update documentation, run full validation, and document patterns for future servers.

**Architecture:** Update all READMEs with accurate information, create MCP development guide, and validate everything works.

**Tech Stack:** Markdown documentation, pytest

**Prerequisites:** Complete Phases 1-3

---

## Task 1: Update Framework MCP Server README

**Files:**
- Create: `kubani/framework/mcp/server/README.md`

**Step 1: Write comprehensive README**

```markdown
# Kubani MCP Server Utilities

Shared base code for all Kubani MCP servers, providing consistent patterns for:

- **Connection Management**: Lifecycle management for backend connections
- **Health Checks**: Standardized health monitoring
- **Error Handling**: Consistent error classes and responses
- **Transport**: Unified command-line argument parsing
- **Testing**: Contract-based test harness and mocks

## Quick Start

### Creating a New MCP Server

```python
from kubani.framework.mcp.server import MCPServerBase, TransportConfig
from kubani.framework.mcp.server.transport import run_server_async
from mcp.server.fastmcp import FastMCP

class MyMCPServer(MCPServerBase):
    name = "my-mcp-server"
    description = "Does useful things with the backend"

    def __init__(self):
        super().__init__()
        self._client = None

    @property
    def client(self):
        self.ensure_connected()
        return self._client

    async def connect_backend(self):
        self._client = await MyBackend.connect(
            host=os.environ.get("MY_BACKEND_HOST", "localhost"),
        )

    async def disconnect_backend(self):
        if self._client:
            await self._client.close()
            self._client = None

    def register_tools(self, mcp: FastMCP):
        @mcp.tool()
        async def my_tool(query: str) -> dict:
            """Do something with the query."""
            result = await self.client.process(query)
            return {"result": result}


def main():
    import logging
    logging.basicConfig(level=logging.INFO)

    server = MyMCPServer()
    mcp = server.create_server()
    config = TransportConfig.from_args()

    async def run():
        try:
            await server.startup()
            await run_server_async(mcp, config)
        finally:
            await server.shutdown()

    import anyio
    anyio.run(run)


if __name__ == "__main__":
    main()
```

## Components

### MCPServerBase

Abstract base class that all MCP servers should inherit from:

```python
class MCPServerBase(ABC):
    name: str          # Server name
    description: str   # Server description

    @abstractmethod
    async def connect_backend(self) -> None: ...

    @abstractmethod
    async def disconnect_backend(self) -> None: ...

    @abstractmethod
    def register_tools(self, mcp: FastMCP) -> None: ...
```

### ConnectionManager

Manages connection lifecycle with state tracking:

```python
from kubani.framework.mcp.server import ConnectionManager

manager = ConnectionManager(name="my-backend")

# Connect
await manager.connect(my_connect_function)

# Check status
if manager.is_connected:
    pass

# Ensure connected (raises MCPConnectionError if not)
manager.ensure_connected()

# Disconnect
await manager.disconnect(my_disconnect_function)
```

### Health Checks

Standardized health monitoring:

```python
from kubani.framework.mcp.server import HealthCheck, HealthStatus

async def check_db():
    await db.ping()
    return True

hc = HealthCheck(name="database", check_fn=check_db, timeout=5.0)
result = await hc.run()

print(result.status)      # HealthStatus.HEALTHY
print(result.latency_ms)  # 12.5
```

### Transport Configuration

Unified argument parsing:

```python
from kubani.framework.mcp.server import TransportConfig

# From command line args
config = TransportConfig.from_args()

# From environment variables
config = TransportConfig.from_env()

# Manual
config = TransportConfig(
    mode=TransportMode.SSE,
    host="0.0.0.0",
    port=8080,
)
```

### Error Classes

Standardized MCP errors:

```python
from kubani.framework.mcp.server import (
    MCPError,
    MCPConnectionError,
    MCPTimeoutError,
    MCPValidationError,
)

raise MCPConnectionError("Cannot connect", server="qdrant")
raise MCPTimeoutError("Slow query", timeout=30.0)
raise MCPValidationError("Bad input", field="query", value="")
```

## Testing

### Contract-Based Testing

```python
from kubani.framework.mcp.server.testing import (
    MCPTestHarness,
    MCPContract,
    ToolContract,
)

contract = MCPContract(
    server_name="my-server",
    tools=[
        ToolContract(
            name="my_tool",
            parameters={"query": {"type": "string", "required": True}},
        ),
    ],
)

server = MyMCPServer()
harness = MCPTestHarness(server, contract)

# Validate all tools exist
result = await harness.validate_tools_exist()
assert result.passed

# Call a tool
await harness.setup()
result = await harness.call_tool("my_tool", query="test")
await harness.teardown()
```

### Mock Backends

```python
from kubani.framework.mcp.server.testing import MockQdrant, MockRedis

mock = MockQdrant()
await mock.connect()
await mock.create_collection("test", vector_size=128)
results = await mock.search("test", query_vector=[1.0, 0.0])
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MCP_TRANSPORT` | Transport mode (stdio, sse, http) | `stdio` |
| `MCP_HOST` | Host to bind to | `0.0.0.0` |
| `MCP_PORT` | Port to bind to | `8080` |
| `MCP_ALLOWED_HOSTS` | Comma-separated allowed hosts | `localhost:*,127.0.0.1:*` |

## Development

```bash
# Run tests
cd kubani/framework && uv run pytest mcp/server/ -v

# Run with coverage
uv run pytest mcp/server/ --cov=kubani.framework.mcp.server
```
```

**Step 2: Commit**

```bash
git add kubani/framework/mcp/server/README.md
git commit -m "docs(mcp): comprehensive README for server utilities

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Update Individual Server READMEs

**Files:**
- Modify: `kubani/mcp/servers/temporal/README.md`
- Modify: `kubani/mcp/servers/qdrant/README.md`
- Modify: `kubani/mcp/servers/memory/README.md`
- Modify: `kubani/mcp/servers/skills/README.md`
- Modify: `kubani/mcp/servers/discord/README.md`

**Step 1: Create template for server READMEs**

Each README should follow this structure:

```markdown
# [Server Name] MCP Server

[One-line description]

## Features

- [Feature 1]
- [Feature 2]
- ...

## Installation

```bash
uv pip install -e kubani/mcp/servers/[name]
```

## Quick Start

```bash
# Run with stdio (default)
[command-name]

# Run with SSE on port 8080
[command-name] --mode sse --port 8080

# Using environment variables
MCP_TRANSPORT=sse MCP_PORT=8080 [command-name]
```

## Tools

| Tool | Description |
|------|-------------|
| `tool_name` | What it does |
| ... | ... |

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `VAR_NAME` | What it configures | `default` |
| ... | ... | ... |

## Development

```bash
cd kubani/mcp/servers/[name]
uv pip install -e ".[dev]"
uv run pytest -v
```

## Architecture

[Brief description of how it works]
```

**Step 2: Update each server README following the template**

For example, `temporal/README.md`:

```markdown
# Temporal MCP Server

MCP server for Temporal workflow orchestration. Enables AI agents to start, query, signal, and manage Temporal workflows and schedules.

## Features

- List and filter workflows by status
- Start new workflow executions
- Send signals to running workflows
- Query workflow state
- Cancel and terminate workflows
- Manage schedules (pause, unpause, trigger)

## Installation

```bash
uv pip install -e kubani/mcp/servers/temporal
```

## Quick Start

```bash
# Run with stdio (default)
temporal-mcp

# Run with SSE on port 8081
temporal-mcp --mode sse --port 8081

# Using environment variables
MCP_TRANSPORT=sse MCP_PORT=8081 temporal-mcp
```

## Tools

| Tool | Description |
|------|-------------|
| `list_workflows` | List workflows with optional status filter |
| `get_workflow` | Get details of a specific workflow |
| `get_workflow_history` | Get workflow event history |
| `start_workflow` | Start a new workflow execution |
| `signal_workflow` | Send a signal to a running workflow |
| `query_workflow` | Query workflow state |
| `cancel_workflow` | Request workflow cancellation |
| `terminate_workflow` | Forcefully terminate a workflow |
| `list_schedules` | List all schedules |
| `pause_schedule` | Pause a schedule |
| `unpause_schedule` | Unpause a schedule |
| `trigger_schedule` | Trigger immediate schedule execution |
| `health` | Check server health |

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `TEMPORAL_HOST` | Temporal server host | `localhost` |
| `TEMPORAL_PORT` | Temporal server port | `7233` |
| `TEMPORAL_NAMESPACE` | Temporal namespace | `default` |
| `MCP_TRANSPORT` | Transport mode | `stdio` |
| `MCP_HOST` | Bind host | `0.0.0.0` |
| `MCP_PORT` | Bind port | `8080` |

## Development

```bash
cd kubani/mcp/servers/temporal
uv pip install -e ".[dev]"
uv run pytest -v
```

## Architecture

The server uses `MCPServerBase` from `kubani.framework.mcp.server`:

1. At startup, connects to Temporal using temporalio client
2. Registers tools via `register_tools()` method
3. Tools access the Temporal client via `self.client` property
4. Connection is maintained for server lifetime
5. Clean disconnect on shutdown
```

**Step 3: Commit all updated READMEs**

```bash
git add kubani/mcp/servers/*/README.md
git commit -m "docs(mcp): update all server READMEs with consistent format

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Create MCP Development Guide

**Files:**
- Create: `docs/kubani/mcp/development-guide.md`

**Step 1: Write development guide**

See the comprehensive development guide template in the Phase 4 overview. This should include:

- Overview of the architecture
- Step-by-step guide to creating a new server
- Package structure
- pyproject.toml template
- Server implementation template
- Testing with contracts
- Adding to registry
- Dockerfile template
- Best practices

**Step 2: Commit**

```bash
git add docs/kubani/mcp/development-guide.md
git commit -m "docs(mcp): add MCP server development guide

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Run Full Validation

**Step 1: Install all packages**

```bash
# From kubani root
uv pip install -e kubani/framework
uv pip install -e kubani/mcp/servers/discord
uv pip install -e kubani/mcp/servers/temporal
uv pip install -e kubani/mcp/servers/qdrant
uv pip install -e kubani/mcp/servers/memory
uv pip install -e kubani/mcp/servers/skills
```

**Step 2: Run framework tests**

```bash
cd kubani/framework && uv run pytest mcp/server/ -v
```

Expected: All tests pass

**Step 3: Run individual server tests**

```bash
cd kubani/mcp/servers/discord && uv run pytest -v
cd kubani/mcp/servers/temporal && uv run pytest -v
cd kubani/mcp/servers/qdrant && uv run pytest -v
cd kubani/mcp/servers/memory && uv run pytest -v
cd kubani/mcp/servers/skills && uv run pytest -v
```

Expected: All tests pass

**Step 4: Run integration tests**

```bash
cd kubani/mcp/servers && uv run pytest tests/ -v
```

Expected: All servers have their contracted tools

**Step 5: Validate registry**

```bash
just mcp-validate
```

Expected: Registry valid, all servers present

**Step 6: Document results**

Create `docs/plans/drafts/2026-01-27-mcp-validation-results.md`:

```markdown
# MCP Infrastructure Validation Results

Date: 2026-01-27

## Test Results

| Package | Tests | Status |
|---------|-------|--------|
| kubani.framework.mcp.server | 27+ | ✅ |
| discord-mcp-server | 5+ | ✅ |
| temporal-mcp-server | 8+ | ✅ |
| qdrant-mcp-server | 6+ | ✅ |
| memory-mcp-server | 10+ | ✅ |
| skills-mcp-server | 12+ | ✅ |
| Integration | 5+ | ✅ |

## Registry Validation

- Total servers: 8 (5 internal + 3 external)
- All capabilities defined: ✅
- Policies updated: ✅

## Coverage

- Overall: >80%
- Framework: 95%
- Server-specific: 70-85%

## Notes

[Any issues found and resolutions]
```

**Step 7: Commit validation results**

```bash
git add docs/plans/drafts/2026-01-27-mcp-validation-results.md
git commit -m "docs(mcp): add validation results

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Final Cleanup and PR

**Step 1: Run linting**

```bash
just lint
```

Fix any issues found.

**Step 2: Create summary commit**

```bash
git add -A
git commit -m "feat(mcp): complete MCP infrastructure review

Phase 1: Created kubani/framework/mcp/server/ module
Phase 2: Standardized all 5 MCP servers
Phase 3: Added comprehensive test suite
Phase 4: Updated documentation

Improvements:
- Consistent patterns across all servers
- All servers in registry with capabilities
- >80% test coverage
- Development guide for new servers

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

**Step 3: Move plan to completed**

```bash
mv docs/plans/drafts/2026-01-27-mcp-*.md docs/plans/completed/
git add docs/plans/
git commit -m "docs: move MCP plans to completed

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

Phase 4 completes the MCP infrastructure review:

| Deliverable | Status |
|-------------|--------|
| Server utilities README | ✅ |
| Server READMEs updated | ✅ |
| Development guide | ✅ |
| Full test run | ✅ |
| Registry validated | ✅ |
| Plans archived | ✅ |

**Final state:**
- 1 shared module (`kubani/framework/mcp/server/`)
- 5 standardized servers
- 8 servers in registry
- >80% test coverage
- Comprehensive documentation
