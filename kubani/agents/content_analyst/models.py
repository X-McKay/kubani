"""Models for the content analyst and digest publisher agents."""

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

    BREAKING = "breaking"
    HOT = "hot"
    RISING = "rising"
    ESTABLISHED = "established"
    FADING = "fading"


class ProcessedArticle(BaseModel):
    """Article after processing by the content analyst."""

    url: str
    title: str
    source: str
    source_category: str = ""
    published_at: datetime | None = None
    original_summary: str = ""

    # Processed data
    ai_summary: str = ""
    category: ArticleCategory = ArticleCategory.GENERAL
    entities: list[str] = Field(default_factory=list)
    importance_score: int = Field(default=5, ge=1, le=10)
    is_breaking: bool = False

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
    related_articles: list[str] = Field(default_factory=list)
    momentum: float = 0.0


class NewsDigest(BaseModel):
    """Complete news digest ready for publishing."""

    digest_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    period_start: datetime
    period_end: datetime

    headline_summary: str = ""
    trending_topics: list[TrendingTopic] = Field(default_factory=list)

    total_articles: int = 0
    sources_used: list[str] = Field(default_factory=list)

    published: bool = False
    discord_message_id: str | None = None
