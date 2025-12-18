"""
Pydantic models for the news monitor agent.

Defines data structures for articles, digests, trends, and related entities.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ArticleCategory(str, Enum):
    """Categories for classifying articles."""

    RESEARCH = "research"
    BUSINESS = "business"
    PRODUCT = "product"
    SECURITY = "security"
    POLICY = "policy"
    GENERAL = "general"


class TrendStatus(str, Enum):
    """Status of a trending topic."""

    BREAKING = "breaking"  # First time seeing this, high importance
    HOT = "hot"  # Multiple sources covering same story
    RISING = "rising"  # Topic frequency increasing
    ESTABLISHED = "established"  # Ongoing story, continued coverage
    FADING = "fading"  # Was hot, now declining


class RawArticle(BaseModel):
    """Raw article as fetched from RSS feed."""

    url: str
    title: str
    source: str
    source_category: str
    published_at: datetime | None = None
    summary: str = ""  # RSS description/summary
    author: str | None = None
    tags: list[str] = Field(default_factory=list)


class ProcessedArticle(BaseModel):
    """Article after processing by the content analyst."""

    # Original data
    url: str
    title: str
    source: str
    source_category: str
    published_at: datetime | None = None
    original_summary: str = ""

    # Processed data
    ai_summary: str = ""  # AI-generated 2-3 sentence summary
    category: ArticleCategory = ArticleCategory.GENERAL
    entities: list[str] = Field(default_factory=list)  # Companies, people, technologies
    importance_score: int = Field(default=5, ge=1, le=10)
    is_breaking: bool = False  # High-importance, should trigger alert

    # Deduplication
    content_hash: str = ""
    processed_at: datetime = Field(default_factory=datetime.utcnow)


class TrendingTopic(BaseModel):
    """A topic that's trending across multiple sources."""

    topic: str
    status: TrendStatus
    article_count: int
    first_seen: datetime
    last_seen: datetime
    sources: list[str] = Field(default_factory=list)
    related_articles: list[str] = Field(default_factory=list)  # URLs
    momentum: float = 0.0  # Rate of change in coverage


class DigestSection(BaseModel):
    """A section of the digest with a theme."""

    title: str
    articles: list[ProcessedArticle]
    summary: str = ""  # Section summary paragraph


class NewsDigest(BaseModel):
    """Complete news digest ready for publishing."""

    digest_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    period_start: datetime
    period_end: datetime

    # Content
    headline_summary: str = ""  # Opening paragraph summarizing key news
    sections: list[DigestSection] = Field(default_factory=list)
    trending_topics: list[TrendingTopic] = Field(default_factory=list)

    # Metadata
    total_articles: int = 0
    sources_used: list[str] = Field(default_factory=list)

    # Publishing
    published: bool = False
    discord_message_id: str | None = None


class BreakingNewsAlert(BaseModel):
    """Alert for high-importance breaking news."""

    article: ProcessedArticle
    alert_reason: str  # Why this triggered an alert
    created_at: datetime = Field(default_factory=datetime.utcnow)
    published: bool = False
    discord_message_id: str | None = None


class ArticleMemoryRecord(BaseModel):
    """Record stored in memory for deduplication and tracking."""

    url: str
    content_hash: str
    title: str
    source: str
    published_at: datetime | None
    processed_at: datetime
    included_in_digest: str | None = None  # digest_id if published
    entities: list[str] = Field(default_factory=list)


class ThemeMemoryRecord(BaseModel):
    """Record for tracking themes over time."""

    theme_name: str
    first_seen: datetime
    last_seen: datetime
    article_count: int
    article_urls: list[str] = Field(default_factory=list)
    status: TrendStatus
    momentum_history: list[float] = Field(default_factory=list)  # Rolling momentum values
