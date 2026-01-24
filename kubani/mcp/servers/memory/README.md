# Memory MCP Server

Unified MCP (Model Context Protocol) server for the Kubani memory system. Combines Qdrant (vector search), Neo4j (graph relationships), and Redis (fast cache) into a single high-level interface for AI agents and Claude Code.

## Features

### Learning Management (Vector-based)
- **store_learning**: Store learnings from agent executions
- **query_learnings**: Semantic search across learnings
- **get_agent_learnings**: Get recent learnings for an agent

### Knowledge Management (Graph-based)
- **store_knowledge**: Store domain knowledge with relationships
- **query_knowledge**: Semantic search for knowledge
- **get_knowledge_graph**: Explore knowledge graph around a topic
- **find_related_topics**: Find related topics

### Relationship Management
- **create_relationship**: Create relationships between entities
- **get_entity_relationships**: Get all relationships for an entity

### Cache Operations
- **cache_set**: Store values in fast cache
- **cache_get**: Retrieve cached values
- **cache_delete**: Remove cached values

### Utilities
- **get_memory_stats**: Get memory system statistics
- **consolidate_learnings**: Consolidate similar learnings into patterns

## Installation

```bash
cd tools/memory-mcp-server
uv pip install -e .
```

## Configuration

Set environment variables:

```bash
# Qdrant (vector search)
export QDRANT_HOST=localhost
export QDRANT_PORT=6333
export QDRANT_API_KEY=your-api-key  # Optional

# Neo4j (graph)
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=your-password

# Redis (cache)
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_PASSWORD=your-password  # Optional

# Embeddings API
export EMBEDDINGS_API_URL=http://localhost:8001/v1
export EMBEDDINGS_MODEL=text-embedding-ada-002

# MCP transport
export MCP_TRANSPORT=stdio
```

## Usage

### As a standalone server

```bash
# stdio transport (for Claude Code)
memory-mcp

# SSE transport (for web clients)
MCP_TRANSPORT=sse memory-mcp
```

### With Claude Code

Add to your `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "memory": {
      "command": "memory-mcp",
      "env": {
        "QDRANT_HOST": "qdrant.almckay.io",
        "NEO4J_URI": "bolt://neo4j.almckay.io:7687",
        "REDIS_HOST": "redis.almckay.io",
        "EMBEDDINGS_API_URL": "https://embeddings.almckay.io/v1"
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
    name="memory-mcp",
    type="mcp",
    source="memory-mcp-server",
    env={
        "QDRANT_HOST": "qdrant.almckay.io",
        "NEO4J_URI": "bolt://neo4j.almckay.io:7687",
        "REDIS_HOST": "redis.almckay.io",
    },
))
```

## Example Usage

### Store a learning

```
Store a learning from the k8s-monitor agent:
- Type: pattern
- Content: "OOM kills in production often indicate the need for vertical scaling before horizontal"
- Confidence: 0.85
- Tags: ["kubernetes", "memory", "scaling"]
```

### Query learnings

```
Search for learnings about "kubernetes memory issues" with minimum confidence 0.7
```

### Store knowledge

```
Store knowledge about kubernetes memory management:
- Topic: kubernetes/memory-management
- Content: "Kubernetes uses cgroups to enforce memory limits..."
- Related topics: kubernetes/resources, kubernetes/oom-killer
```

### Explore knowledge graph

```
Show me the knowledge graph around "kubernetes/memory-management" with depth 2
```

### Use cache for fast access

```
Cache the current cluster state with key "cluster:production:state" and TTL of 60 seconds
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Memory MCP Server                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    MCP Interface                         │   │
│  │  store_learning | query_learnings | store_knowledge     │   │
│  │  get_knowledge_graph | cache_set | cache_get | ...      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│              ┌───────────────┼───────────────┐                  │
│              ▼               ▼               ▼                  │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │
│  │ VectorBackend │  │ GraphBackend  │  │ CacheBackend  │       │
│  │   (Qdrant)    │  │   (Neo4j)     │  │   (Redis)     │       │
│  │               │  │               │  │               │       │
│  │ • Embeddings  │  │ • Nodes       │  │ • Key-Value   │       │
│  │ • Similarity  │  │ • Edges       │  │ • TTL         │       │
│  │ • Filtering   │  │ • Traversal   │  │ • Lists       │       │
│  └───────────────┘  └───────────────┘  └───────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Data Model

### Learnings
Stored in Qdrant with embeddings for semantic search:
- `learning_id`: Unique identifier
- `agent_id`: Source agent
- `learning_type`: pattern, anti_pattern, insight, fact
- `content`: Learning text
- `context`: Metadata dictionary
- `confidence`: 0-1 score
- `tags`: Categorization tags
- `timestamp`: Creation time

### Knowledge
Stored in both Qdrant (search) and Neo4j (relationships):
- `knowledge_id`: Unique identifier
- `topic`: Hierarchical path (e.g., "kubernetes/memory-management")
- `content`: Knowledge text
- `source`: Origin of knowledge
- `metadata`: Additional data
- `related_topics`: Connected topics

### Relationships (Neo4j)
- `LEARNED`: Agent → Learning
- `SUPPORTS`: Learning → Pattern
- `RELATED_TO`: Topic → Topic
- `CONTAINS`: Topic → Knowledge

## Integration with Learning System

The Memory MCP server is the storage backend for the Voyager-inspired learning system:

```python
# Critic Agent stores evaluations
await memory.store_learning(
    agent_id="k8s-monitor",
    learning_type="pattern",
    content="Successful remediation pattern identified",
    confidence=0.9,
)

# Reflection Agent queries across agents
learnings = await memory.query_learnings(
    query="successful kubernetes remediation",
    min_confidence=0.7,
)

# Skill Synthesizer stores knowledge
await memory.store_knowledge(
    topic="skills/k8s/remediation/oom-handling",
    content="Best practices for OOM handling...",
    related_topics=["kubernetes/memory-management"],
)
```

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=memory_mcp

# Lint
ruff check src/
ruff format src/
```

## License

MIT
