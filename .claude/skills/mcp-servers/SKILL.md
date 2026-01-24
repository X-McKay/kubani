---
name: mcp-servers
description: Use and develop MCP servers for agent capabilities. Includes Temporal, Qdrant, Memory, Discord, and Registry MCP servers.
---

# MCP Servers

Kubani provides several MCP servers that extend agent capabilities.

## Available MCP Servers

| Server | Purpose | Location |
|--------|---------|----------|
| temporal-mcp | Workflow orchestration | `kubani/mcp/servers/temporal/` |
| qdrant-mcp | Vector search | `kubani/mcp/servers/qdrant/` |
| memory-mcp | Unified memory | `kubani/mcp/servers/memory/` |
| discord-mcp | Discord integration | `kubani/mcp/servers/discord/` |
| skills-mcp | Skills registry | `kubani/mcp/servers/skills/` |

## Quick Start

### Installation

```bash
# Install all MCP servers
uv pip install -e kubani/mcp/servers/temporal
uv pip install -e kubani/mcp/servers/qdrant
uv pip install -e kubani/mcp/servers/memory
uv pip install -e kubani/mcp/servers/discord
```

### Claude Code Configuration

Add to `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "temporal": {
      "command": "temporal-mcp",
      "env": {
        "TEMPORAL_HOST": "temporal.almckay.io:7233",
        "TEMPORAL_NAMESPACE": "kubani"
      }
    },
    "qdrant": {
      "command": "qdrant-mcp",
      "env": {
        "QDRANT_HOST": "qdrant.almckay.io",
        "QDRANT_PORT": "6333"
      }
    },
    "memory": {
      "command": "memory-mcp",
      "env": {
        "QDRANT_HOST": "qdrant.almckay.io",
        "NEO4J_URI": "bolt://neo4j.almckay.io:7687",
        "REDIS_HOST": "redis.almckay.io"
      }
    },
    "discord": {
      "command": "discord-mcp",
      "env": {
        "DISCORD_BOT_TOKEN": "${DISCORD_BOT_TOKEN}"
      }
    }
  }
}
```

## Temporal MCP Server

Manage Temporal workflows and schedules.

### Tools

- `list_workflows` - List workflows with filtering
- `get_workflow` - Get workflow details
- `start_workflow` - Start a new workflow
- `signal_workflow` - Send signals to workflows
- `query_workflow` - Query workflow state
- `cancel_workflow` - Cancel a workflow
- `terminate_workflow` - Force terminate
- `list_schedules` - List schedules
- `pause_schedule` / `unpause_schedule` - Manage schedules
- `trigger_schedule` - Trigger immediate execution

### Example Usage

```
List all running k8s-monitor workflows
```

```
Start a new news-digest workflow with ID "digest-2024-01-11"
```

```
Get the history of workflow "failed-workflow-123" to debug the failure
```

## Qdrant MCP Server

Vector database operations for semantic search.

### Tools

- `list_collections` - List all collections
- `create_collection` - Create a new collection
- `delete_collection` - Delete a collection
- `upsert_vectors` - Insert/update vectors
- `search_vectors` - Semantic similarity search
- `get_point` - Get a specific point
- `delete_points` - Delete points
- `scroll_points` - Paginate through points
- `count_points` - Count points

### Example Usage

```
Create a collection called "agent-learnings" with 1536 dimensions
```

```
Search for vectors similar to "kubernetes memory issues" in the learnings collection
```

## Memory MCP Server

Unified memory system combining Qdrant, Neo4j, and Redis.

### Tools

**Learnings:**
- `store_learning` - Store agent learnings
- `query_learnings` - Semantic search learnings
- `get_agent_learnings` - Get agent's learnings

**Knowledge:**
- `store_knowledge` - Store domain knowledge
- `query_knowledge` - Search knowledge
- `get_knowledge_graph` - Explore relationships
- `find_related_topics` - Find related topics

**Relationships:**
- `create_relationship` - Create entity relationships
- `get_entity_relationships` - Get relationships

**Cache:**
- `cache_set` / `cache_get` / `cache_delete` - Fast caching

**Utilities:**
- `get_memory_stats` - Memory system stats
- `consolidate_learnings` - Consolidate similar learnings

### Example Usage

```
Store a learning from k8s-monitor: "OOM kills indicate memory pressure"
with confidence 0.85 and tags ["kubernetes", "memory"]
```

```
Query learnings about "pod restart issues" with minimum confidence 0.7
```

```
Show the knowledge graph around "kubernetes/memory-management"
```

## Discord MCP Server

Discord integration for notifications and approvals.

### Tools

- `send_message` - Send a message to a channel
- `send_embed` - Send rich embed message
- `add_reaction` - Add reaction to message
- `get_reactions` - Get message reactions
- `create_thread` - Create a thread
- `wait_for_reaction` - Wait for specific reaction

### Example Usage

```
Send an alert to the alerts channel about a pod failure
```

```
Post a skill proposal to the learning channel and wait for approval reactions
```

## Developing New MCP Servers

### Template

```python
"""
My MCP Server implementation.
"""

import os
from mcp.server.fastmcp import FastMCP

def create_server() -> FastMCP:
    mcp = FastMCP(
        name="My MCP Server",
        instructions="Description of what this server does.",
    )

    @mcp.tool()
    async def my_tool(
        param1: str,
        param2: int = 10,
    ) -> dict:
        """
        Tool description.

        Args:
            param1: Description of param1
            param2: Description of param2 (default: 10)

        Returns:
            Result description
        """
        # Implementation
        return {"result": "value"}

    return mcp


async def main():
    server = create_server()
    
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    elif transport == "sse":
        await server.run_sse_async()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Project Structure

```
tools/my-mcp-server/
├── src/my_mcp/
│   ├── __init__.py
│   ├── server.py      # MCP server implementation
│   └── models.py      # Pydantic models
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_server.py
├── pyproject.toml
└── README.md
```

### Testing

```bash
# Run tests
cd tools/my-mcp-server
pytest

# Test manually
python -m my_mcp.server
```

### Registration

Add to the registry for discovery:

```bash
kubani-dev mcp register my-mcp-server
```

## Best Practices

1. **Use descriptive tool names** that indicate the action
2. **Provide detailed docstrings** for tool discovery
3. **Use Pydantic models** for complex inputs/outputs
4. **Handle errors gracefully** with informative messages
5. **Add comprehensive tests** for all tools
6. **Document environment variables** in README
7. **Support both stdio and SSE** transports
