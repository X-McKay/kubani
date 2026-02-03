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


# =============================================================================
# News/Article Storage Models
# =============================================================================


class ArticleEntry(BaseModel):
    """A stored news article."""

    article_id: str = Field(description="Unique article identifier")
    url: str = Field(description="Article URL")
    title: str = Field(description="Article title")
    source: str = Field(description="Source name")
    published_at: datetime | None = Field(default=None, description="Publication date")
    stored_at: datetime = Field(description="When article was stored")
    ai_summary: str = Field(default="", description="AI-generated summary")
    entities: list[str] = Field(default_factory=list, description="Extracted entities")
    importance_score: int = Field(default=5, description="Importance score 1-10")
    category: str = Field(default="general", description="Article category")
    content_hash: str = Field(default="", description="Content hash for deduplication")


class ArticleQueryResult(BaseModel):
    """Result of querying articles."""

    articles: list[ArticleEntry] = Field(description="Matching articles")
    count: int = Field(description="Number of results")
    start_date: str | None = Field(default=None, description="Query start date")
    end_date: str | None = Field(default=None, description="Query end date")


class TrendSnapshot(BaseModel):
    """A point-in-time snapshot of trends."""

    snapshot_id: str = Field(description="Unique snapshot identifier")
    snapshot_date: datetime = Field(description="When snapshot was taken")
    trends: list[dict[str, Any]] = Field(default_factory=list, description="Trend data")
    emerging_topics: list[str] = Field(default_factory=list, description="Emerging topics")
    declining_topics: list[str] = Field(default_factory=list, description="Declining topics")
    total_articles: int = Field(default=0, description="Article count at snapshot time")


# =============================================================================
# Generic Memory Interface Models (per skills-mcp-integration plan)
# =============================================================================


class MemoryRelation(BaseModel):
    """A relation to another memory object."""

    target_id: str = Field(description="ID of the target object")
    relation_type: str = Field(description="Type of relationship (e.g., 'analyzed_from', 'derived_from')")


class MemoryObject(BaseModel):
    """A generic memory object that can store any type of data."""

    id: str = Field(description="Unique object identifier")
    type: str = Field(description="Object type (e.g., 'document', 'analysis', 'trend', 'event')")
    namespace: str = Field(description="Namespace for organization (e.g., 'news/articles', 'k8s/pods')")
    data: dict[str, Any] = Field(description="The actual content/data")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata (timestamps, source, etc.)")
    created_at: datetime = Field(description="When the object was created")
    relations: list[MemoryRelation] = Field(default_factory=list, description="Relations to other objects")
    relevance_score: float | None = Field(default=None, description="Search relevance score (when from search)")


class MemoryAddResult(BaseModel):
    """Result of adding a memory object."""

    id: str = Field(description="ID of the created object")
    type: str = Field(description="Object type")
    namespace: str = Field(description="Object namespace")
    created_at: datetime = Field(description="Creation timestamp")
    relations_created: int = Field(default=0, description="Number of relations created")


class MemorySearchResult(BaseModel):
    """Result of searching memory."""

    results: list[MemoryObject] = Field(description="Matching objects")
    count: int = Field(description="Number of results returned")
    total: int = Field(default=0, description="Total matching (may be > count if limited)")
    query: str = Field(description="The search query used")


class MemoryGetResult(BaseModel):
    """Result of getting a memory object by ID."""

    found: bool = Field(description="Whether the object was found")
    object: MemoryObject | None = Field(default=None, description="The object if found")


class MemoryLinkResult(BaseModel):
    """Result of linking two memory objects."""

    source_id: str = Field(description="Source object ID")
    target_id: str = Field(description="Target object ID")
    relation_type: str = Field(description="Type of relationship")
    created: bool = Field(description="Whether the link was newly created")


class MemorySeenResult(BaseModel):
    """Result of checking or marking seen status."""

    key: str = Field(description="The key checked/marked")
    namespace: str = Field(description="The namespace")
    seen: bool = Field(description="Whether the key was seen")
