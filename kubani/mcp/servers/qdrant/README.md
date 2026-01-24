# Qdrant MCP Server

MCP (Model Context Protocol) server for Qdrant vector database. Enables AI agents and Claude Code to perform semantic search, store embeddings, and manage vector collections.

## Features

### Collection Management
- **list_collections**: List all collections with stats
- **create_collection**: Create new vector collections
- **delete_collection**: Delete collections
- **get_collection_info**: Get detailed collection information

### Vector Operations
- **upsert_vectors**: Insert or update vectors with metadata
- **search_vectors**: Semantic similarity search with filtering
- **get_point**: Retrieve a specific point by ID
- **delete_points**: Delete points by IDs
- **scroll_points**: Paginate through all points
- **count_points**: Count points with optional filtering

## Installation

```bash
cd tools/qdrant-mcp-server
uv pip install -e .
```

## Configuration

Set environment variables:

```bash
# Qdrant connection
export QDRANT_HOST=localhost
export QDRANT_PORT=6333
export QDRANT_API_KEY=your-api-key  # Optional
export QDRANT_HTTPS=false

# MCP transport (stdio or sse)
export MCP_TRANSPORT=stdio

# For SSE transport
export MCP_HOST=0.0.0.0
export MCP_PORT=8081
```

## Usage

### As a standalone server

```bash
# stdio transport (for Claude Code)
qdrant-mcp

# SSE transport (for web clients)
MCP_TRANSPORT=sse qdrant-mcp
```

### With Claude Code

Add to your `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "qdrant": {
      "command": "qdrant-mcp",
      "env": {
        "QDRANT_HOST": "qdrant.almckay.io",
        "QDRANT_PORT": "6333"
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
    name="qdrant-mcp",
    type="mcp",
    source="qdrant-mcp-server",
    env={
        "QDRANT_HOST": "qdrant.almckay.io",
    },
))
```

## Example Usage

### Create a collection for agent memory

```
Create a new Qdrant collection called "agent-learnings" with 1536 dimensions for OpenAI embeddings
```

### Store a learning

```
Store this learning in the "agent-learnings" collection:
- Vector: [0.1, 0.2, ...] (embedding)
- Payload: {"agent": "k8s-monitor", "type": "pattern", "content": "OOM kills indicate memory pressure"}
```

### Search for relevant learnings

```
Search the "agent-learnings" collection for learnings similar to "memory issues in kubernetes pods"
```

### Filter by agent

```
Search for learnings from the k8s-monitor agent only
```

## Integration with Memory System

The Qdrant MCP server is designed to work with the Kubani shared memory system:

```python
from core_agents.memory.shared import SharedMemorySystem

# The SharedMemorySystem uses Qdrant internally
memory = SharedMemorySystem()

# Store a learning (uses Qdrant via MCP)
await memory.store_learning(
    agent_id="k8s-monitor",
    learning_type="pattern",
    content="OOM kills often indicate need for vertical scaling",
    context={"namespace": "production"},
    confidence=0.85,
)

# Query learnings (semantic search via Qdrant)
learnings = await memory.query_learnings(
    query="memory issues kubernetes",
    min_confidence=0.7,
)
```

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=qdrant_mcp

# Lint
ruff check src/
ruff format src/
```

## Architecture

```
qdrant-mcp-server/
├── src/qdrant_mcp/
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
