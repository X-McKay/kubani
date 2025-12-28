"""
mem0 utilities for vLLM-based embeddings.

Provides configuration helpers for using vLLM with mem0's memory system.

The standard mem0 OpenAI embedder always passes dimensions= to the API, which
vLLM rejects for models that don't support matryoshka (variable dimensions)
like Qwen3-Embedding-0.6B.

Solution: Use mem0's 'lmstudio' provider, which uses the OpenAI SDK but doesn't
pass the dimensions parameter. We just point it at vLLM instead of LM Studio.

This module provides:
1. get_mem0_config() - Standard configuration for mem0 with vLLM embeddings
2. VLLM_MODEL_DIMENSIONS - Known dimensions for common vLLM embedding models

Usage:
    from core_agents.mem0_utils import get_mem0_config
    from mem0 import Memory

    # Create memory with vLLM embeddings
    config = get_mem0_config(
        pg_host="postgresql.database.svc.cluster.local",
        pg_database="my_memory_db",
    )
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
    pg_host: str | None = None,
    pg_port: int | None = None,
    pg_user: str | None = None,
    pg_password: str | None = None,
    pg_database: str | None = None,
    llm_url: str | None = None,
    llm_model: str | None = None,
    embeddings_url: str | None = None,
    embeddings_model: str | None = None,
    embedding_dims: int | None = None,
) -> dict[str, Any]:
    """
    Build a standard mem0 configuration for vLLM-based embeddings.

    Uses the 'lmstudio' provider which doesn't pass the dimensions parameter
    (unlike 'openai' which always does). This works with vLLM models that don't
    support matryoshka (variable dimension) embeddings like Qwen3-Embedding.

    All parameters can be provided explicitly or via environment variables.

    Args:
        pg_host: PostgreSQL host (env: MEMORY_PG_HOST)
        pg_port: PostgreSQL port (env: MEMORY_PG_PORT, default: 5432)
        pg_user: PostgreSQL user (env: MEMORY_PG_USER)
        pg_password: PostgreSQL password (env: MEMORY_PG_PASSWORD)
        pg_database: Database name (env: MEMORY_PG_DATABASE)
        llm_url: vLLM API URL for LLM operations (env: VLLM_API_URL)
        llm_model: vLLM model name (env: VLLM_MODEL)
        embeddings_url: Embeddings API URL (env: EMBEDDINGS_API_URL)
        embeddings_model: Embeddings model name (env: EMBEDDINGS_MODEL)
        embedding_dims: Embedding dimensions (auto-detected if known model)

    Returns:
        Dict configuration suitable for Memory.from_config()
    """
    # Resolve all configuration values
    _pg_host = pg_host or os.environ.get("MEMORY_PG_HOST", "postgresql.database.svc.cluster.local")
    _pg_port = pg_port or int(os.environ.get("MEMORY_PG_PORT", "5432"))
    _pg_user = pg_user or os.environ.get("MEMORY_PG_USER", "mem0")
    _pg_password = pg_password or os.environ.get("MEMORY_PG_PASSWORD", "")
    _pg_database = pg_database or os.environ.get("MEMORY_PG_DATABASE", "mem0")

    _llm_url = llm_url or os.environ.get(
        "VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1"
    )
    _llm_model = llm_model or os.environ.get("VLLM_MODEL", "Qwen/Qwen3-14B-FP8")

    _embeddings_url = embeddings_url or os.environ.get(
        "EMBEDDINGS_API_URL", "http://embeddings-api.vllm.svc.cluster.local:8000/v1"
    )
    _embeddings_model = embeddings_model or os.environ.get(
        "EMBEDDINGS_MODEL", "Qwen/Qwen3-Embedding-0.6B"
    )

    # Auto-detect dimensions for known models
    _embedding_dims = embedding_dims or VLLM_MODEL_DIMENSIONS.get(_embeddings_model, 1024)

    logger.debug(
        f"Building mem0 config: embeddings={_embeddings_model} ({_embedding_dims}d) "
        f"at {_embeddings_url}"
    )

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
            "provider": "pgvector",
            "config": {
                "host": _pg_host,
                "port": _pg_port,
                "user": _pg_user,
                "password": _pg_password,
                "dbname": _pg_database,
                "embedding_model_dims": _embedding_dims,
            },
        },
        "version": "v1.1",
    }
