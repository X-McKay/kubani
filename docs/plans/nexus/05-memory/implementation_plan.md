
># Nexus Implementation Plan: 05 - Unified Memory MCP Server

**Author:** Manus AI
**Date:** February 6, 2026

## 1. Overview

This document details the implementation plan for the **Unified Memory MCP Server**. This service is a critical component of the agent's intelligence, providing a single, abstract interface for all memory operations. It will orchestrate the flow of information between the agent's working memory (Redis), its episodic and semantic memory (Qdrant), and its long-term knowledge graph (Neo4j).

By abstracting away the underlying databases, this server simplifies the logic of the agent and its skills, promotes consistency, and makes the overall system more maintainable.

## 2. Technology Stack

-   **Language:** Python
-   **Framework:** FastAPI
-   **Core Logic:** `mem0` library (for orchestrating memory types)
-   **Databases:**
    -   Redis (for caching and working memory)
    -   Qdrant (for vector search)
    -   Neo4j (for graph-based knowledge)

## 3. Core Logic: Leveraging `mem0`

The existing `kubani` project already includes `mem0` as an optional dependency. We will make it a core component of this server. The `mem0` library is designed to solve this exact problem, providing a unified API that can manage multiple memory types and backends.

Our server will essentially be a FastAPI wrapper around a `mem0` instance, exposing its functionality as a secure MCP service.

**Configuration:**

We will configure a `mem0` instance that uses all three of our target databases:

```python
from mem0 import Memory

# This configuration will be loaded from the Kubani config system
config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": "qdrant.kubani.local",
            "port": 6333,
        },
    },
    "graph_store": {
        "provider": "neo4j",
        "config": {
            "uri": "bolt://neo4j.kubani.local:7687",
            "username": "neo4j",
            "password": "...",
        },
    },
    "cache": {
        "provider": "redis",
        "config": {
            "host": "redis.kubani.local",
            "port": 6379,
        },
    },
}

memory_instance = Memory.from_config(config)
```

## 4. API Design

The server will expose a simple, high-level API that mirrors the `mem0` client API.

### 4.1. `POST /add`

-   **Purpose:** Add new information to the agent's memory.
-   **Request Body:**
    ```json
    {
        "data": "User said their favorite color is blue.",
        "metadata": {
            "user_id": "user-123",
            "conversation_id": "conv-456"
        }
    }
    ```
-   **Logic:** This endpoint will call `memory_instance.add(data=..., metadata=...)`. The `mem0` library will handle the rest: embedding the data, storing it in Qdrant, extracting entities and relationships, and storing them in Neo4j.

### 4.2. `POST /search`

-   **Purpose:** Search the agent's memory based on a query.
-   **Request Body:**
    ```json
    {
        "query": "What is my favorite color?"
    }
    ```
-   **Logic:** This will call `memory_instance.search(query=...)`. `mem0` will perform a semantic search against the Qdrant vector store and return the most relevant memories.

### 4.3. `GET /history`

-   **Purpose:** Retrieve a recent history of memories.
-   **Logic:** This will call `memory_instance.history()`.

### 4.4. `GET /graph`

-   **Purpose:** (Advanced) Expose a way to query the underlying knowledge graph directly for specific relationship-based questions.
-   **Query Parameters:** `?cypher_query=...`
-   **Logic:** This endpoint will provide controlled, read-only access to the Neo4j database for complex graph queries that go beyond the standard `mem0` search.

## 5. Deployment

-   This service will be deployed as a standard Kubernetes `Deployment` and `Service` named `memory-mcp-server`.
-   It will replace any existing memory-related MCP servers to become the single source of truth.
-   Its configuration will be managed via the central `kubani` configuration system, allowing us to easily point it to the correct database instances in different environments (local vs. cluster).

By centralizing all memory logic into this single, powerful service, we create a clean and maintainable architecture that can easily evolve as the agent's memory needs become more complex.
