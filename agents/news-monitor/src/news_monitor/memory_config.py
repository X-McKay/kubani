"""
Memory configuration for news-monitor agent.

Provides AI/tech news-specific graph prompts and mem0 configuration
for article memory using Qdrant + Neo4j.

This module contains domain-specific configuration that was previously
in core_agents but has been moved here to keep core domain-agnostic.
"""

import os
from typing import Any

from core_agents import get_graph_mem0_config

# News-specific graph prompt for AI/tech news monitoring
NEWS_GRAPH_PROMPT = """
Extract entities and relationships relevant to AI/tech news:

Entities to capture:
- Companies (OpenAI, Google, Microsoft, Anthropic, Meta, etc.)
- Products (GPT-4, Claude, Gemini, Llama, etc.)
- Technologies (transformers, RAG, agents, fine-tuning, etc.)
- People (researchers, executives, founders)
- Topics (AI safety, model training, inference, reasoning, etc.)
- Sources (ArXiv, TechCrunch, VentureBeat, The Verge, etc.)

Relationships to capture:
- DEVELOPS: Company develops Product/Technology
- RESEARCHES: Person/Company researches Topic
- COMPETES_WITH: Product competes with Product
- COVERS: Article covers Topic
- MENTIONS: Article mentions Entity
- RELATED_TO: Topic is related to Topic
- PUBLISHED_BY: Article published by Source
- WORKS_AT: Person works at Company
- ANNOUNCES: Company announces Product/Technology
"""


def get_news_graph_mem0_config(
    collection_name: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Build a mem0 configuration optimized for AI/tech news monitoring.

    Uses Qdrant for vector similarity search and Neo4j for graph-based
    relationship tracking with a custom prompt tuned for news entities.

    Enables:
    - Cross-article theme detection via entity relationships
    - Topic evolution tracking through relationship paths
    - Duplicate detection via shared entity mentions

    Args:
        collection_name: Qdrant collection name (default: from env or 'news-monitor')
        **kwargs: Additional arguments passed to get_graph_mem0_config()

    Returns:
        Dict configuration for news-focused graph memory
    """
    _collection_name = collection_name or os.environ.get("QDRANT_COLLECTION", "news-monitor")
    return get_graph_mem0_config(
        collection_name=_collection_name,
        graph_custom_prompt=NEWS_GRAPH_PROMPT,
        **kwargs,
    )
