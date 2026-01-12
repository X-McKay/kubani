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
    VLLM_MODEL_DIMENSIONS,
    get_graph_mem0_config,
    get_mem0_config,
)
from core_agents.memory.facts import (
    ExtractedFacts,
    extract_facts,
    extract_facts_sync,
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
from core_agents.memory.shared import (
    MemoryEntry,
    MemoryScope,
    MemoryType,
    Neo4jMemory,
    QdrantMemory,
    RedisCache,
    SearchResult,
    SharedMemory,
    get_shared_memory,
)

__all__ = [
    # Config
    "get_mem0_config",
    "get_graph_mem0_config",
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
    # Fact extraction
    "ExtractedFacts",
    "extract_facts",
    "extract_facts_sync",
    # Shared memory
    "MemoryEntry",
    "MemoryScope",
    "MemoryType",
    "SearchResult",
    "QdrantMemory",
    "Neo4jMemory",
    "RedisCache",
    "SharedMemory",
    "get_shared_memory",
]
