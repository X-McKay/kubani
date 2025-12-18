"""Tests for Pydantic models."""

from datetime import datetime

from news_monitor.models import (
    ArticleCategory,
    NewsDigest,
    ProcessedArticle,
    RawArticle,
    TrendingTopic,
    TrendStatus,
)


def test_raw_article_creation():
    """Test creating a raw article."""
    article = RawArticle(
        url="https://example.com/article",
        title="Test Article",
        source="Test Source",
        source_category="general_tech",
    )
    assert article.url == "https://example.com/article"
    assert article.title == "Test Article"
    assert article.summary == ""  # Default
    assert article.tags == []  # Default


def test_processed_article_defaults():
    """Test processed article default values."""
    article = ProcessedArticle(
        url="https://example.com/article",
        title="Test Article",
        source="Test Source",
        source_category="general_tech",
    )
    assert article.importance_score == 5
    assert article.is_breaking is False
    assert article.category == ArticleCategory.GENERAL


def test_processed_article_importance_bounds():
    """Importance score should be bounded 1-10."""
    # Test lower bound
    article = ProcessedArticle(
        url="https://example.com",
        title="Test",
        source="Test",
        source_category="test",
        importance_score=1,
    )
    assert article.importance_score == 1

    # Test upper bound
    article = ProcessedArticle(
        url="https://example.com",
        title="Test",
        source="Test",
        source_category="test",
        importance_score=10,
    )
    assert article.importance_score == 10


def test_trending_topic_creation():
    """Test creating a trending topic."""
    now = datetime.utcnow()
    topic = TrendingTopic(
        topic="GPT-5",
        status=TrendStatus.HOT,
        article_count=5,
        first_seen=now,
        last_seen=now,
        sources=["OpenAI Blog", "TechCrunch"],
    )
    assert topic.topic == "GPT-5"
    assert topic.status == TrendStatus.HOT
    assert len(topic.sources) == 2


def test_news_digest_creation():
    """Test creating a news digest."""
    now = datetime.utcnow()
    digest = NewsDigest(
        digest_id="test-123",
        period_start=now,
        period_end=now,
        headline_summary="Test summary",
        total_articles=10,
    )
    assert digest.digest_id == "test-123"
    assert digest.published is False
    assert digest.discord_message_id is None


def test_trend_status_values():
    """Verify all trend status values."""
    assert TrendStatus.BREAKING.value == "breaking"
    assert TrendStatus.HOT.value == "hot"
    assert TrendStatus.RISING.value == "rising"
    assert TrendStatus.ESTABLISHED.value == "established"
    assert TrendStatus.FADING.value == "fading"


def test_article_category_values():
    """Verify all article category values."""
    assert ArticleCategory.RESEARCH.value == "research"
    assert ArticleCategory.BUSINESS.value == "business"
    assert ArticleCategory.PRODUCT.value == "product"
    assert ArticleCategory.SECURITY.value == "security"
    assert ArticleCategory.POLICY.value == "policy"
    assert ArticleCategory.GENERAL.value == "general"
