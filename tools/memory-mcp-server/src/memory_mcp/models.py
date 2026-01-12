"""
Memory MCP Server data models.

Pydantic models for the unified memory system.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LearningEntry(BaseModel):
    """A learning entry from an agent."""

    learning_id: str = Field(description="Unique learning identifier")
    agent_id: str = Field(description="Agent that created this learning")
    learning_type: str = Field(description="Type: pattern, anti_pattern, insight, fact")
    content: str = Field(description="Learning content")
    context: dict[str, Any] = Field(default_factory=dict, description="Context/metadata")
    confidence: float = Field(description="Confidence score 0-1")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    timestamp: datetime = Field(description="When the learning was created")
    relevance_score: float | None = Field(default=None, description="Search relevance score")


class LearningResult(BaseModel):
    """Result of storing a learning."""

    learning_id: str = Field(description="Unique learning identifier")
    agent_id: str = Field(description="Agent that created this learning")
    learning_type: str = Field(description="Type of learning")
    content: str = Field(description="Learning content")
    confidence: float = Field(description="Confidence score")
    timestamp: datetime = Field(description="Creation timestamp")


class LearningsResult(BaseModel):
    """Result of querying learnings."""

    learnings: list[LearningEntry] = Field(description="Matching learnings")
    count: int = Field(description="Number of results")
    query: str = Field(description="Original query")


class KnowledgeEntry(BaseModel):
    """A knowledge entry."""

    knowledge_id: str = Field(description="Unique knowledge identifier")
    topic: str = Field(description="Topic path (e.g., kubernetes/memory-management)")
    content: str = Field(description="Knowledge content")
    source: str = Field(description="Source of knowledge")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    timestamp: datetime = Field(description="When the knowledge was created")
    relevance_score: float | None = Field(default=None, description="Search relevance score")


class KnowledgeResult(BaseModel):
    """Result of storing knowledge."""

    knowledge_id: str = Field(description="Unique knowledge identifier")
    topic: str = Field(description="Topic path")
    content: str = Field(description="Knowledge content")
    source: str = Field(description="Source")
    timestamp: datetime = Field(description="Creation timestamp")


class RelationshipResult(BaseModel):
    """Result of relationship operations."""

    relationship_id: str = Field(description="Relationship identifier")
    from_entity: str = Field(description="Source entity")
    to_entity: str = Field(description="Target entity")
    relationship_type: str = Field(description="Type of relationship")
    properties: dict[str, Any] = Field(default_factory=dict, description="Relationship properties")


class MemoryStats(BaseModel):
    """Memory system statistics."""

    total_learnings: int = Field(description="Total number of learnings")
    total_knowledge: int = Field(description="Total knowledge entries")
    total_relationships: int = Field(description="Total relationships")
    cache_keys: int = Field(description="Number of cached keys")
    agents_with_learnings: int = Field(description="Number of agents with learnings")
