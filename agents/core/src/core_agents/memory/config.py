"""
mem0 utilities for Qdrant vector store and Neo4j graph memory.

Provides configuration helpers for using mem0's memory system with:
- Qdrant: High-performance vector database for semantic search
- Neo4j: Graph database for relationship tracking (mem0g)
- vLLM: Self-hosted embeddings via OpenAI-compatible API

Architecture:
    Qdrant (vector store) - stores embeddings for similarity search
    Neo4j (graph store) - stores entities and relationships
    vLLM (embeddings) - generates embeddings via OpenAI-compatible API

The standard mem0 OpenAI embedder always passes dimensions= to the API, which
vLLM rejects for models that don't support matryoshka (variable dimensions)
like Qwen3-Embedding-0.6B.

Solution: Use mem0's 'lmstudio' provider, which uses the OpenAI SDK but doesn't
pass the dimensions parameter. We just point it at vLLM instead of LM Studio.

This module provides:
1. get_mem0_config() - Standard configuration with Qdrant vector store
2. get_graph_mem0_config() - Configuration with Qdrant + Neo4j graph memory
3. VLLM_MODEL_DIMENSIONS - Known dimensions for common vLLM embedding models

Usage:
    from core_agents.mem0_utils import get_mem0_config, get_graph_mem0_config
    from mem0 import Memory

    # Standard memory with Qdrant vector store
    config = get_mem0_config()
    memory = Memory.from_config(config)

    # Graph memory with Qdrant + Neo4j for relationship tracking
    config = get_graph_mem0_config()
    memory = Memory.from_config(config)
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Known model dimensions for common vLLM embedding models
VLLM_MODEL_DIMENSIONS = {
    "Qwen/Qwen3-Embedding-0.6B": 1024,
    "Qwen/Qwen3-Embedding-4B": 2560,
    "Qwen/Qwen3-Embedding-8B": 4096,
}


def get_mem0_config(
    qdrant_host: str | None = None,
    qdrant_port: int | None = None,
    qdrant_api_key: str | None = None,
    collection_name: str | None = None,
    llm_url: str | None = None,
    llm_model: str | None = None,
    embeddings_url: str | None = None,
    embeddings_model: str | None = None,
    embedding_dims: int | None = None,
) -> dict[str, Any]:
    """
    Build a standard mem0 configuration with Qdrant vector store.

    Uses Qdrant for high-performance vector similarity search.
    Uses the 'lmstudio' embedder provider which doesn't pass the dimensions
    parameter (unlike 'openai' which always does). This works with vLLM models
    that don't support matryoshka (variable dimension) embeddings.

    All parameters can be provided explicitly or via environment variables.

    Args:
        qdrant_host: Qdrant host (env: QDRANT_HOST)
        qdrant_port: Qdrant port (env: QDRANT_PORT, default: 6333)
        qdrant_api_key: Qdrant API key (env: QDRANT_API_KEY)
        collection_name: Qdrant collection name (env: QDRANT_COLLECTION)
        llm_url: vLLM API URL for LLM operations (env: VLLM_API_URL)
        llm_model: vLLM model name (env: VLLM_MODEL)
        embeddings_url: Embeddings API URL (env: EMBEDDINGS_API_URL)
        embeddings_model: Embeddings model name (env: EMBEDDINGS_MODEL)
        embedding_dims: Embedding dimensions (auto-detected if known model)

    Returns:
        Dict configuration suitable for Memory.from_config()
    """
    # Resolve Qdrant configuration
    _qdrant_host = qdrant_host or os.environ.get(
        "QDRANT_HOST", "qdrant.database.svc.cluster.local"
    )
    _qdrant_port = qdrant_port or int(os.environ.get("QDRANT_PORT", "6333"))
    _qdrant_api_key = qdrant_api_key or os.environ.get("QDRANT_API_KEY")
    _collection_name = collection_name or os.environ.get("QDRANT_COLLECTION", "mem0")

    # Resolve LLM configuration
    _llm_url = llm_url or os.environ.get(
        "VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1"
    )
    _llm_model = llm_model or os.environ.get("VLLM_MODEL", "Qwen/Qwen3-14B-FP8")

    # Resolve embeddings configuration
    _embeddings_url = embeddings_url or os.environ.get(
        "EMBEDDINGS_API_URL", "http://embeddings-api.vllm.svc.cluster.local:8000/v1"
    )
    _embeddings_model = embeddings_model or os.environ.get(
        "EMBEDDINGS_MODEL", "Qwen/Qwen3-Embedding-0.6B"
    )

    # Auto-detect dimensions for known models
    _embedding_dims = embedding_dims or VLLM_MODEL_DIMENSIONS.get(_embeddings_model, 1024)

    logger.debug(
        f"Building mem0 config: embeddings={_embeddings_model} ({_embedding_dims}d), "
        f"vector_store=qdrant://{_qdrant_host}:{_qdrant_port}/{_collection_name}"
    )

    # Build Qdrant config
    qdrant_config: dict[str, Any] = {
        "host": _qdrant_host,
        "port": _qdrant_port,
        "collection_name": _collection_name,
        "embedding_model_dims": _embedding_dims,
    }
    if _qdrant_api_key:
        qdrant_config["api_key"] = _qdrant_api_key

    return {
        "llm": {
            "provider": "openai",
            "config": {
                "model": _llm_model,
                "api_key": "not-needed",
                "openai_base_url": _llm_url,
                "temperature": 0.1,
            },
        },
        # Use 'lmstudio' provider - it uses OpenAI SDK but doesn't pass dimensions=
        # which is required for vLLM models that don't support matryoshka embeddings
        "embedder": {
            "provider": "lmstudio",
            "config": {
                "model": _embeddings_model,
                "embedding_dims": _embedding_dims,
                "lmstudio_base_url": _embeddings_url,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": qdrant_config,
        },
        "version": "v1.1",
    }


def get_graph_mem0_config(
    qdrant_host: str | None = None,
    qdrant_port: int | None = None,
    qdrant_api_key: str | None = None,
    collection_name: str | None = None,
    llm_url: str | None = None,
    llm_model: str | None = None,
    embeddings_url: str | None = None,
    embeddings_model: str | None = None,
    embedding_dims: int | None = None,
    neo4j_url: str | None = None,
    neo4j_username: str | None = None,
    neo4j_password: str | None = None,
    graph_custom_prompt: str | None = None,
) -> dict[str, Any]:
    """
    Build a mem0 configuration with Qdrant + Neo4j graph memory.

    Combines:
    - Qdrant for vector similarity search (fast semantic lookup)
    - Neo4j for graph memory (relationship tracking)

    Graph memory uses Neo4j to track relationships between entities, enabling
    queries like "What fixes worked for OOMKilled pods?" by storing:
    - Entities (pods, issues, fixes, outcomes)
    - Relationships (caused_by, fixed_by, resulted_in)

    Args:
        qdrant_host: Qdrant host (env: QDRANT_HOST)
        qdrant_port: Qdrant port (env: QDRANT_PORT, default: 6333)
        qdrant_api_key: Qdrant API key (env: QDRANT_API_KEY)
        collection_name: Qdrant collection name (env: QDRANT_COLLECTION)
        llm_url: vLLM API URL for LLM operations (env: VLLM_API_URL)
        llm_model: vLLM model name (env: VLLM_MODEL)
        embeddings_url: Embeddings API URL (env: EMBEDDINGS_API_URL)
        embeddings_model: Embeddings model name (env: EMBEDDINGS_MODEL)
        embedding_dims: Embedding dimensions (auto-detected if known model)
        neo4j_url: Neo4j bolt URL (env: NEO4J_URL)
        neo4j_username: Neo4j username (env: NEO4J_USERNAME)
        neo4j_password: Neo4j password (env: NEO4J_PASSWORD)
        graph_custom_prompt: Custom prompt for entity/relationship extraction

    Returns:
        Dict configuration suitable for Memory.from_config() with graph memory enabled
    """
    # Get base configuration with Qdrant
    config = get_mem0_config(
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
        qdrant_api_key=qdrant_api_key,
        collection_name=collection_name,
        llm_url=llm_url,
        llm_model=llm_model,
        embeddings_url=embeddings_url,
        embeddings_model=embeddings_model,
        embedding_dims=embedding_dims,
    )

    # Resolve Neo4j configuration
    _neo4j_url = neo4j_url or os.environ.get(
        "NEO4J_URL", "bolt://neo4j.database.svc.cluster.local:7687"
    )
    _neo4j_username = neo4j_username or os.environ.get("NEO4J_USERNAME", "neo4j")
    _neo4j_password = neo4j_password or os.environ.get("NEO4J_PASSWORD", "")

    logger.debug(f"Building mem0g config with Neo4j at {_neo4j_url}")

    # Build graph store config
    graph_config: dict[str, Any] = {
        "provider": "neo4j",
        "config": {
            "url": _neo4j_url,
            "username": _neo4j_username,
            "password": _neo4j_password,
        },
    }

    # Add custom prompt if provided
    if graph_custom_prompt:
        graph_config["custom_prompt"] = graph_custom_prompt

    config["graph_store"] = graph_config

    return config


# K8s-specific graph prompt for remediation memory
K8S_GRAPH_PROMPT = """
Extract entities and relationships relevant to Kubernetes operations:

Entities to capture:
- Pods, Deployments, Services, Namespaces
- Issues (OOMKilled, CrashLoopBackOff, ImagePullError, etc.)
- Fixes (restart, scale, resource adjustment, config change)
- Outcomes (resolved, partially resolved, failed)

Relationships to capture:
- AFFECTS: Issue affects Pod/Deployment
- FIXED_BY: Issue was fixed by a specific action
- RESULTED_IN: Fix resulted in an outcome
- CAUSED_BY: Issue was caused by another issue or condition
- SIMILAR_TO: Issue is similar to a previous issue
"""


def get_k8s_graph_mem0_config(
    collection_name: str = "k8s-remediation",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Build a mem0 configuration optimized for Kubernetes remediation memory.

    Uses a custom graph prompt tuned for K8s entities and relationships.

    Args:
        collection_name: Qdrant collection name (default: k8s-remediation)
        **kwargs: Additional arguments passed to get_graph_mem0_config()

    Returns:
        Dict configuration for K8s-focused graph memory
    """
    return get_graph_mem0_config(
        collection_name=collection_name,
        graph_custom_prompt=K8S_GRAPH_PROMPT,
        **kwargs,
    )
