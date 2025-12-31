"""
Shared test fixtures for news-monitor tests.

Provides mocks and fixtures for testing workflow behavior, agent responses,
and Discord notification validation without requiring actual LLM calls or
external services.
"""

import os
import sys
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Ensure the src directory is on the path for local development
_src_path = Path(__file__).parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from news_monitor.models import (  # noqa: E402
    ArticleCategory,
    NewsDigest,
    ProcessedArticle,
    RawArticle,
    TrendingTopic,
    TrendStatus,
)

# =============================================================================
# Sample Articles
# =============================================================================


@pytest.fixture
def sample_raw_article() -> RawArticle:
    """Single raw article for testing."""
    return RawArticle(
        url="https://openai.com/blog/gpt-5-announcement",
        title="OpenAI Announces GPT-5",
        source="OpenAI Blog",
        source_category="company_blogs",
        published_at=datetime.utcnow(),
        summary="Major language model announcement.",
        content="OpenAI today announced GPT-5, their latest language model...",
        tags=["ai", "llm", "openai"],
    )


@pytest.fixture
def sample_raw_articles() -> list[RawArticle]:
    """Collection of raw RSS articles."""
    now = datetime.utcnow()
    return [
        RawArticle(
            url="https://openai.com/blog/gpt-5",
            title="OpenAI Announces GPT-5",
            source="OpenAI Blog",
            source_category="company_blogs",
            published_at=now - timedelta(hours=1),
            summary="GPT-5 announcement",
            tags=["ai", "llm"],
        ),
        RawArticle(
            url="https://anthropic.com/news/claude-4",
            title="Anthropic Releases Claude 4",
            source="Anthropic",
            source_category="company_blogs",
            published_at=now - timedelta(hours=2),
            summary="Claude 4 with improved reasoning",
            tags=["ai", "claude"],
        ),
        RawArticle(
            url="https://techcrunch.com/ai-funding",
            title="AI Startups Raise $10B",
            source="TechCrunch",
            source_category="tech_news",
            published_at=now - timedelta(hours=3),
            summary="Record funding round",
            tags=["ai", "funding"],
        ),
        RawArticle(
            url="https://arxiv.org/reasoning-paper",
            title="New Reasoning Breakthrough",
            source="ArXiv",
            source_category="research",
            published_at=now - timedelta(hours=4),
            summary="Novel reasoning technique",
            tags=["ai", "research"],
        ),
    ]


@pytest.fixture
def sample_processed_article() -> ProcessedArticle:
    """Single processed article for testing."""
    return ProcessedArticle(
        url="https://openai.com/blog/gpt-5-announcement",
        title="OpenAI Announces GPT-5",
        source="OpenAI Blog",
        source_category="company_blogs",
        published_at=datetime.utcnow(),
        summary="OpenAI releases GPT-5 with significant improvements.",
        importance_score=9,
        is_breaking=True,
        category=ArticleCategory.PRODUCT,
        entities=["OpenAI", "GPT-5"],
        ai_summary="OpenAI has announced GPT-5, featuring improved reasoning capabilities.",
    )


@pytest.fixture
def sample_processed_articles() -> list[ProcessedArticle]:
    """Collection of analyzed articles."""
    now = datetime.utcnow()
    return [
        ProcessedArticle(
            url="https://openai.com/blog/gpt-5",
            title="OpenAI Announces GPT-5",
            source="OpenAI Blog",
            source_category="company_blogs",
            published_at=now - timedelta(hours=1),
            importance_score=9,
            is_breaking=True,
            category=ArticleCategory.PRODUCT,
            entities=["OpenAI", "GPT-5"],
            ai_summary="GPT-5 announcement with major improvements.",
        ),
        ProcessedArticle(
            url="https://anthropic.com/news/claude-4",
            title="Anthropic Releases Claude 4",
            source="Anthropic",
            source_category="company_blogs",
            published_at=now - timedelta(hours=2),
            importance_score=8,
            is_breaking=True,
            category=ArticleCategory.PRODUCT,
            entities=["Anthropic", "Claude"],
            ai_summary="Claude 4 released with improved reasoning.",
        ),
        ProcessedArticle(
            url="https://techcrunch.com/ai-funding",
            title="AI Startups Raise $10B",
            source="TechCrunch",
            source_category="tech_news",
            published_at=now - timedelta(hours=3),
            importance_score=6,
            is_breaking=False,
            category=ArticleCategory.BUSINESS,
            entities=["AI startups"],
            ai_summary="Record funding for AI companies.",
        ),
    ]


@pytest.fixture
def breaking_news_article() -> ProcessedArticle:
    """High importance breaking news article."""
    return ProcessedArticle(
        url="https://openai.com/blog/gpt-5-launch",
        title="BREAKING: GPT-5 Launches Today",
        source="OpenAI Blog",
        source_category="company_blogs",
        published_at=datetime.utcnow(),
        importance_score=10,
        is_breaking=True,
        category=ArticleCategory.PRODUCT,
        entities=["OpenAI", "GPT-5"],
        ai_summary="GPT-5 is now available to all users.",
    )


@pytest.fixture
def duplicate_articles() -> tuple[ProcessedArticle, ProcessedArticle]:
    """Two articles with similar content."""
    now = datetime.utcnow()
    original = ProcessedArticle(
        url="https://openai.com/blog/gpt-5",
        title="OpenAI Announces GPT-5",
        source="OpenAI Blog",
        source_category="company_blogs",
        published_at=now,
        importance_score=9,
        category=ArticleCategory.PRODUCT,
        ai_summary="OpenAI has announced GPT-5 with major improvements.",
    )
    duplicate = ProcessedArticle(
        url="https://techcrunch.com/openai-gpt-5",
        title="OpenAI's GPT-5 Announced",
        source="TechCrunch",
        source_category="tech_news",
        published_at=now + timedelta(minutes=30),
        importance_score=7,
        category=ArticleCategory.PRODUCT,
        ai_summary="OpenAI announces GPT-5, their latest language model.",
    )
    return original, duplicate


# =============================================================================
# Sample Trends and Digests
# =============================================================================


@pytest.fixture
def sample_trends() -> list[TrendingTopic]:
    """Collection of trending topics."""
    now = datetime.utcnow()
    return [
        TrendingTopic(
            topic="GPT-5",
            status=TrendStatus.BREAKING,
            article_count=5,
            first_seen=now - timedelta(hours=2),
            last_seen=now,
            sources=["OpenAI", "TechCrunch", "The Verge"],
        ),
        TrendingTopic(
            topic="LLM Safety",
            status=TrendStatus.HOT,
            article_count=3,
            first_seen=now - timedelta(hours=6),
            last_seen=now - timedelta(hours=1),
            sources=["Anthropic", "ArXiv"],
        ),
        TrendingTopic(
            topic="AI Funding",
            status=TrendStatus.RISING,
            article_count=2,
            first_seen=now - timedelta(hours=12),
            last_seen=now - timedelta(hours=4),
            sources=["TechCrunch"],
        ),
    ]


@pytest.fixture
def sample_digest(sample_processed_articles, sample_trends) -> NewsDigest:
    """Sample news digest for testing."""
    now = datetime.utcnow()
    return NewsDigest(
        digest_id="test-digest-123",
        period_start=now - timedelta(hours=4),
        period_end=now,
        headline_summary="Major AI announcements: GPT-5 and Claude 4 released",
        total_articles=len(sample_processed_articles),
        trending_topics=sample_trends,
    )


# =============================================================================
# Mock Discord Webhook
# =============================================================================


@dataclass
class DiscordWebhookCapture:
    """Captures Discord webhook calls for testing."""

    calls: list[dict[str, Any]] = field(default_factory=list)
    should_fail: bool = False
    fail_with: Exception | None = None
    fail_on_call: int | None = None  # Fail on nth call

    def capture(self, payload: dict[str, Any]) -> str:
        """Record a webhook call and return fake message ID."""
        self.calls.append(payload)

        # Check if we should fail on this call
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            raise self.fail_with or Exception("Simulated failure on nth call")

        if self.should_fail and self.fail_with:
            raise self.fail_with

        return f"discord-msg-{len(self.calls)}"

    def set_failure(self, error: Exception) -> None:
        """Configure the webhook to fail with an error."""
        self.should_fail = True
        self.fail_with = error

    def clear(self) -> None:
        """Clear captured calls and reset failure state."""
        self.calls.clear()
        self.should_fail = False
        self.fail_with = None
        self.fail_on_call = None

    @property
    def call_count(self) -> int:
        """Number of webhook calls made."""
        return len(self.calls)


@pytest.fixture
def mock_discord_webhook() -> Generator[DiscordWebhookCapture, None, None]:
    """Mock Discord webhook that captures calls."""
    capture = DiscordWebhookCapture()

    def mock_publish(digest: Any, formatted: str) -> str | None:
        try:
            return capture.capture({"type": "digest", "content": formatted})
        except Exception:
            return None

    def mock_publish_alert(article: Any, formatted: str) -> str | None:
        try:
            return capture.capture({"type": "alert", "content": formatted})
        except Exception:
            return None

    with (
        patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.test/webhook"}),
        patch("news_monitor.agents.publisher.DiscordPublisherAgent.publish_digest", mock_publish),
        patch(
            "news_monitor.agents.publisher.DiscordPublisherAgent.publish_breaking_alert",
            mock_publish_alert,
        ),
    ):
        yield capture


# =============================================================================
# Mock Memory Services
# =============================================================================


@dataclass
class MockMemoryService:
    """Mock mem0 and Redis memory services."""

    seen_urls: set[str] = field(default_factory=set)
    stored_articles: list[dict] = field(default_factory=list)
    duplicate_threshold: float = 0.92  # Match production value

    def is_url_seen(self, url: str) -> bool:
        """Check if URL has been seen."""
        return url in self.seen_urls

    def mark_url_seen(self, url: str) -> None:
        """Mark URL as seen."""
        self.seen_urls.add(url)

    def is_duplicate(self, article: ProcessedArticle) -> bool:
        """Check if article is semantically similar to stored ones."""
        # Simple simulation: check for title similarity
        return any(stored.get("title") == article.title for stored in self.stored_articles)

    def store_article(self, article: ProcessedArticle) -> str | None:
        """Store article and return memory ID."""
        self.stored_articles.append(article.model_dump())
        self.mark_url_seen(article.url)
        return f"mem-{len(self.stored_articles)}"

    def query_since(self, cutoff: datetime) -> list[dict]:
        """Query articles since cutoff."""
        return [
            a
            for a in self.stored_articles
            if a.get("published_at") and a["published_at"] >= cutoff.isoformat()
        ]


@pytest.fixture
def mock_memory() -> Generator[MockMemoryService, None, None]:
    """Mock memory services (Redis + mem0)."""
    service = MockMemoryService()

    with (
        patch("news_monitor.memory.is_url_seen", service.is_url_seen),
        patch("news_monitor.memory.is_duplicate_article", service.is_duplicate),
        patch("news_monitor.memory.store_article", service.store_article),
        patch("news_monitor.memory.query_articles_since", service.query_since),
        patch("news_monitor.activities.is_url_seen", service.is_url_seen),
        patch("news_monitor.activities.is_duplicate_article", service.is_duplicate),
        patch("news_monitor.activities.store_article", service.store_article),
        patch("news_monitor.activities.query_articles_since", service.query_since),
    ):
        yield service


# =============================================================================
# Mock RSS Feeds
# =============================================================================


@pytest.fixture
def mock_rss_feeds(sample_raw_articles) -> Generator[MagicMock, None, None]:
    """Mock RSS feed responses."""
    with patch("news_monitor.agents.collector.RSSCollectorAgent") as mock_class:
        mock_instance = MagicMock()
        mock_instance.collect_all.return_value = sample_raw_articles
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=None)
        mock_class.return_value = mock_instance
        yield mock_instance


# =============================================================================
# Mock LLM (vLLM)
# =============================================================================


@pytest.fixture
def mock_vllm() -> Generator[MagicMock, None, None]:
    """Mock vLLM API responses for content analysis."""
    with patch("news_monitor.agents.analyst.ContentAnalystAgent") as mock_class:
        mock_instance = MagicMock()

        def mock_analyze(article: RawArticle) -> ProcessedArticle:
            return ProcessedArticle(
                url=article.url,
                title=article.title,
                source=article.source,
                source_category=article.source_category,
                published_at=article.published_at,
                importance_score=7,
                is_breaking=False,
                category=ArticleCategory.GENERAL,
                ai_summary=f"Summary of: {article.title}",
            )

        mock_instance.analyze_article = mock_analyze
        mock_class.return_value = mock_instance
        yield mock_instance


# =============================================================================
# Error Injection
# =============================================================================


class ErrorInjector:
    """Inject errors at specific points in execution."""

    def __init__(self):
        self.error_points: dict[str, Exception] = {}
        self.call_counts: dict[str, int] = {}
        self.fail_on_nth: dict[str, tuple[int, Exception]] = {}

    def fail_on(self, point: str, error: Exception) -> None:
        """Always fail at this point."""
        self.error_points[point] = error

    def fail_on_nth_call(self, point: str, n: int, error: Exception) -> None:
        """Fail on the nth call to this point."""
        self.fail_on_nth[point] = (n, error)
        self.call_counts[point] = 0

    def clear(self) -> None:
        """Clear all error injections."""
        self.error_points.clear()
        self.call_counts.clear()
        self.fail_on_nth.clear()

    def check_and_raise(self, point: str) -> None:
        """Check if an error should be raised at this point."""
        if point in self.error_points:
            raise self.error_points[point]

        if point in self.fail_on_nth:
            self.call_counts[point] = self.call_counts.get(point, 0) + 1
            n, error = self.fail_on_nth[point]
            if self.call_counts[point] == n:
                raise error


@pytest.fixture
def error_injector() -> ErrorInjector:
    """Provide an error injector for testing."""
    return ErrorInjector()


# =============================================================================
# Utility Functions
# =============================================================================


def make_raw_article(
    url: str = "https://test.com/article",
    title: str = "Test Article",
    source: str = "Test Source",
    **kwargs,
) -> RawArticle:
    """Create a RawArticle with defaults."""
    return RawArticle(
        url=url,
        title=title,
        source=source,
        source_category=kwargs.get("source_category", "general"),
        published_at=kwargs.get("published_at", datetime.utcnow()),
        summary=kwargs.get("summary", ""),
        content=kwargs.get("content", ""),
        tags=kwargs.get("tags", []),
    )


def make_processed_article(
    url: str = "https://test.com/article",
    title: str = "Test Article",
    importance: int = 5,
    is_breaking: bool = False,
    **kwargs,
) -> ProcessedArticle:
    """Create a ProcessedArticle with defaults."""
    return ProcessedArticle(
        url=url,
        title=title,
        source=kwargs.get("source", "Test Source"),
        source_category=kwargs.get("source_category", "general"),
        published_at=kwargs.get("published_at", datetime.utcnow()),
        importance_score=importance,
        is_breaking=is_breaking,
        category=kwargs.get("category", ArticleCategory.GENERAL),
        entities=kwargs.get("entities", []),
        ai_summary=kwargs.get("ai_summary", f"Summary of {title}"),
    )
