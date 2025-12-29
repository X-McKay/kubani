"""
Memory systems for AI agents.

Provides hierarchical memory, user preferences tracking, and mem0 configuration
for vector (Qdrant) and graph (Neo4j) memory stores.

Modules:
    config: mem0 configuration for Qdrant/Neo4j backends
    hierarchical: Three-tier memory (working → episodic → semantic)
    preferences: User engagement tracking and content personalization
"""

from core_agents.memory.config import (
    K8S_GRAPH_PROMPT,
    VLLM_MODEL_DIMENSIONS,
    get_graph_mem0_config,
    get_k8s_graph_mem0_config,
    get_mem0_config,
)
from core_agents.memory.hierarchical import (
    HierarchicalMemory,
    HierarchicalMemoryConfig,
    MemoryTier,
    WorkingMemoryItem,
)
from core_agents.memory.preferences import (
    EngagementType,
    TopicPreference,
    UserPreferences,
    UserPreferencesConfig,
)

__all__ = [
    # Config
    "get_mem0_config",
    "get_graph_mem0_config",
    "get_k8s_graph_mem0_config",
    "K8S_GRAPH_PROMPT",
    "VLLM_MODEL_DIMENSIONS",
    # Hierarchical memory
    "HierarchicalMemory",
    "HierarchicalMemoryConfig",
    "MemoryTier",
    "WorkingMemoryItem",
    # User preferences
    "UserPreferences",
    "UserPreferencesConfig",
    "TopicPreference",
    "EngagementType",
]
