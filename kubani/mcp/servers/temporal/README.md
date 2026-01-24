# Temporal MCP Server

MCP (Model Context Protocol) server for Temporal workflow orchestration. Enables AI agents and Claude Code to manage, monitor, and debug Temporal workflows.

## Features

### Workflow Management
- **list_workflows**: List workflows with filtering by status and query
- **get_workflow**: Get details of a specific workflow execution
- **get_workflow_history**: View event history for debugging
- **start_workflow**: Start new workflow executions
- **signal_workflow**: Send signals to running workflows
- **query_workflow**: Query workflow state
- **cancel_workflow**: Request graceful cancellation
- **terminate_workflow**: Force terminate a workflow
- **get_workflow_result**: Wait for and retrieve workflow results

### Schedule Management
- **list_schedules**: List all schedules in the namespace
- **pause_schedule**: Pause a schedule
- **unpause_schedule**: Resume a paused schedule
- **trigger_schedule**: Trigger immediate execution

## Installation

```bash
cd tools/temporal-mcp-server
uv pip install -e .
```

## Configuration

Set environment variables:

```bash
# Temporal connection
export TEMPORAL_HOST=localhost
export TEMPORAL_PORT=7233
export TEMPORAL_NAMESPACE=default

# MCP transport (stdio or sse)
export MCP_TRANSPORT=stdio

# For SSE transport
export MCP_HOST=0.0.0.0
export MCP_PORT=8080
```

## Usage

### As a standalone server

```bash
# stdio transport (for Claude Code)
temporal-mcp

# SSE transport (for web clients)
MCP_TRANSPORT=sse temporal-mcp
```

### With Claude Code

Add to your `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "temporal": {
      "command": "temporal-mcp",
      "env": {
        "TEMPORAL_HOST": "temporal.almckay.io",
        "TEMPORAL_PORT": "7233",
        "TEMPORAL_NAMESPACE": "kubani"
      }
    }
  }
}
```

### With Kubani Agents

```python
from core_agents.plugins import get_plugin_manager, PluginConfig

manager = get_plugin_manager()
await manager.load_plugin(PluginConfig(
    name="temporal-mcp",
    type="mcp",
    source="temporal-mcp-server",
    env={
        "TEMPORAL_HOST": "temporal.almckay.io",
        "TEMPORAL_NAMESPACE": "kubani",
    },
))
```

## Example Usage

### List running workflows

```
Use the temporal MCP server to list all running workflows
```

### Start a workflow

```
Start a new k8s-monitor workflow with ID "monitor-2024-01-11" on the "k8s-monitor" task queue
```

### Debug a failed workflow

```
Get the history of workflow "failed-workflow-123" and identify why it failed
```

### Manage schedules

```
List all schedules and pause the "daily-digest" schedule
```

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=temporal_mcp

# Lint
ruff check src/
ruff format src/
```

## Architecture

```
temporal-mcp-server/
├── src/temporal_mcp/
│   ├── __init__.py      # Package exports
│   ├── server.py        # MCP server implementation
│   └── models.py        # Pydantic data models
├── tests/
│   ├── __init__.py
│   ├── conftest.py      # Test fixtures
│   └── test_server.py   # Server tests
├── pyproject.toml       # Package configuration
└── README.md            # This file
```

## License

MIT
