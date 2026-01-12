"""
mem0 utilities for Qdrant vector store and Neo4j graph memory.

This module provides configuration helpers for using mem0's memory system.
It now delegates to the unified configuration system for all settings.

Usage:
    from core_agents.memory import get_mem0_config, get_graph_mem0_config
    from mem0 import Memory

    # Standard memory with Qdrant vector store
    config = get_mem0_config()
    memory = Memory.from_config(config)

    # Graph memory with Qdrant + Neo4j for relationship tracking
    config = get_graph_mem0_config()
    memory = Memory.from_config(config)
"""

from typing import Any

from core_agents.config_unified import get_config

# Model embedding dimensions for common vLLM models
VLLM_MODEL_DIMENSIONS = {
    "nvidia/Qwen3-14B-FP4": 4096,
    "Qwen/Qwen3-14B": 4096,
    "nvidia/NV-Embed-v2": 4096,
    "BAAI/bge-m3": 1024,
    "default": 4096,
}


# Custom fact extraction prompt optimized for vLLM/Qwen models.
# The default mem0 prompt sometimes causes Qwen to return {} instead of {"facts": []},
# which triggers a KeyError. This prompt is more explicit about always including the
# "facts" key and provides clearer examples.
VLLM_FACT_EXTRACTION_PROMPT = """You are a fact extraction system. Your task is to extract key facts from the input text.

CRITICAL: You MUST always respond with a valid JSON object containing a "facts" key with a list value.
- If you find relevant facts, return them in the list.
- If you find NO relevant facts, return an empty list: {"facts": []}
- NEVER return an empty object {} or omit the "facts" key.

Examples:
Input: ""
Output: {"facts": []}

Input: "Hello"
Output: {"facts": []}

Input: "The weather is nice today"
Output: {"facts": []}

Input: "My name is John and I work at Google"
Output: {"facts": ["Name is John", "Works at Google"]}

Input: "OpenAI released GPT-5 with improved reasoning. It scores 95% on benchmarks."
Output: {"facts": ["OpenAI released GPT-5", "GPT-5 has improved reasoning", "GPT-5 scores 95% on benchmarks"]}

Input: "Article about AI research published on ArXiv discusses transformer architectures"
Output: {"facts": ["Article about AI research", "Published on ArXiv", "Discusses transformer architectures"]}

Rules:
- Extract only factual information, not opinions or speculation
- Keep each fact concise (under 20 words)
- Return {"facts": []} if the input is empty, too short, unclear, or contains no extractable facts
- ALWAYS include the "facts" key in your response, even for empty/invalid input
- For empty or whitespace-only input, respond with: {"facts": []}

Now extract facts from the following input:"""


def get_mem0_config(collection_name: str = "mem0") -> dict[str, Any]:
    """
    Build a standard mem0 configuration with Qdrant vector store.

    Uses the unified configuration system for all settings.

    Args:
        collection_name: Qdrant collection name (default: "mem0")

    Returns:
        Dict configuration suitable for Memory.from_config()
    """
    config = get_config()
    mem0_config = config.get_mem0_config(collection_name)

    # Add custom prompt optimized for vLLM/Qwen models
    mem0_config["custom_fact_extraction_prompt"] = VLLM_FACT_EXTRACTION_PROMPT

    return mem0_config


def get_graph_mem0_config(
    collection_name: str = "mem0",
    graph_custom_prompt: str | None = None,
) -> dict[str, Any]:
    """
    Build a mem0 configuration with Qdrant + Neo4j graph memory.

    Combines:
    - Qdrant for vector similarity search (fast semantic lookup)
    - Neo4j for graph memory (relationship tracking)

    Args:
        collection_name: Qdrant collection name (default: "mem0")
        graph_custom_prompt: Custom prompt for entity/relationship extraction

    Returns:
        Dict configuration suitable for Memory.from_config() with graph memory enabled
    """
    config = get_config()
    mem0_config = config.get_graph_mem0_config(collection_name)

    # Add custom prompts
    mem0_config["custom_fact_extraction_prompt"] = VLLM_FACT_EXTRACTION_PROMPT
    if graph_custom_prompt:
        mem0_config["graph_store"]["custom_prompt"] = graph_custom_prompt

    return mem0_config
