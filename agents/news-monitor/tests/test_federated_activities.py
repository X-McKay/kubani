"""
Tests for federated Temporal activities.

These tests validate the new federated activities that wrap
federated agent functionality for Temporal execution.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from news_monitor.models import (
    ArticleCategory,
    NewsDigest,
    ProcessedArticle,
    RawArticle,
    TrendingTopic,
    TrendStatus,
)


@pytest.fixture
def sample_raw_articles():
    """Create sample raw articles for testing."""
    return [
        RawArticle(
            url=f"https://example.com/article-{i}",
            title=f"Test Article {i}",
            source="Test Source",
            source_category="research",
            published_at=datetime.now(UTC),
            summary=f"Summary for article {i}",
        )
        for i in range(3)
    ]


@pytest.fixture
def sample_processed_articles():
    """Create sample processed articles for testing."""
    return [
        ProcessedArticle(
            url=f"https://example.com/article-{i}",
            title=f"Test Article {i}",
            source="Test Source",
            source_category="research",
            published_at=datetime.now(UTC),
            original_summary=f"Summary for article {i}",
            ai_summary=f"AI summary for article {i}",
            category=ArticleCategory.RESEARCH,
            importance_score=7,
            entities=["Entity1"],
        )
        for i in range(3)
    ]


@pytest.fixture
def sample_breaking_article():
    """Create a breaking news article."""
    return ProcessedArticle(
        url="https://example.com/breaking",
        title="Breaking: Major AI Announcement",
        source="Test Source",
        source_category="research",
        published_at=datetime.now(UTC),
        original_summary="Breaking news about AI",
        ai_summary="Breaking: A major AI announcement has been made.",
        category=ArticleCategory.RESEARCH,
        importance_score=9,
        is_breaking=True,
        entities=["OpenAI"],
    )


@pytest.fixture
def sample_trends():
    """Create sample trending topics."""
    return [
        TrendingTopic(
            topic="Machine Learning",
            status=TrendStatus.HOT,
            article_count=5,
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            sources=["Source1", "Source2"],
        ),
    ]


@pytest.fixture
def sample_digest(sample_processed_articles, sample_trends):
    """Create a sample news digest."""
    return NewsDigest(
        digest_id="test-digest-123",
        period_start=datetime.now(UTC),
        period_end=datetime.now(UTC),
        total_articles=len(sample_processed_articles),
        trending_topics=sample_trends,
    )


class TestCollectArticles:
    """Tests for the collect_articles federated activity."""

    @pytest.mark.asyncio
    async def test_returns_article_dicts(self, sample_raw_articles):
        """Activity should return list of article dictionaries."""
        from news_monitor.federated_activities import collect_articles

        mock_result = MagicMock()
        mock_result.articles = sample_raw_articles
        mock_result.total_collected = 10
        mock_result.seen_filtered = 7

        with patch("news_monitor.federated_activities.NewsCollectorAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.collect.return_value = mock_result
            mock_class.return_value = mock_instance

            result = await collect_articles(max_age_hours=24)

            assert isinstance(result, list)
            assert len(result) == len(sample_raw_articles)
            assert all(isinstance(r, dict) for r in result)
            assert all("url" in r and "title" in r for r in result)

    @pytest.mark.asyncio
    async def test_respects_max_age(self):
        """Activity should pass max_age_hours to collector."""
        from news_monitor.federated_activities import collect_articles

        mock_result = MagicMock()
        mock_result.articles = []
        mock_result.total_collected = 0
        mock_result.seen_filtered = 0

        with patch("news_monitor.federated_activities.NewsCollectorAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.collect.return_value = mock_result
            mock_class.return_value = mock_instance

            await collect_articles(max_age_hours=6)

            mock_class.assert_called_with(max_age_hours=6)

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_articles(self):
        """Activity should return empty list when no articles found."""
        from news_monitor.federated_activities import collect_articles

        mock_result = MagicMock()
        mock_result.articles = []
        mock_result.total_collected = 0
        mock_result.seen_filtered = 0

        with patch("news_monitor.federated_activities.NewsCollectorAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.collect.return_value = mock_result
            mock_class.return_value = mock_instance

            result = await collect_articles()

            assert result == []


class TestAnalyzeSingleArticle:
    """Tests for the analyze_single_article federated activity."""

    @pytest.mark.asyncio
    async def test_returns_processed_article(self, sample_raw_articles, sample_processed_articles):
        """Activity should return processed article dictionary."""
        from news_monitor.federated_activities import analyze_single_article

        mock_result = MagicMock()
        mock_result.processed_articles = [sample_processed_articles[0]]

        with patch("news_monitor.federated_activities.NewsAnalystAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.analyze_articles.return_value = mock_result
            mock_class.return_value = mock_instance

            article_data = sample_raw_articles[0].model_dump()
            result = await analyze_single_article(article_data)

            assert result is not None
            assert isinstance(result, dict)
            assert "url" in result
            assert "importance_score" in result

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self, sample_raw_articles):
        """Activity should return None when analysis fails."""
        from news_monitor.federated_activities import analyze_single_article

        mock_result = MagicMock()
        mock_result.processed_articles = []

        with patch("news_monitor.federated_activities.NewsAnalystAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.analyze_articles.return_value = mock_result
            mock_class.return_value = mock_instance

            article_data = sample_raw_articles[0].model_dump()
            result = await analyze_single_article(article_data)

            assert result is None

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        """Activity should handle exceptions and return None."""
        from news_monitor.federated_activities import analyze_single_article

        with patch("news_monitor.federated_activities.NewsAnalystAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.analyze_articles.side_effect = Exception("Analysis failed")
            mock_class.return_value = mock_instance

            article_data = {
                "url": "https://example.com/test",
                "title": "Test",
                "source": "Test",
                "source_category": "research",
                "published_at": datetime.now(UTC).isoformat(),
            }
            result = await analyze_single_article(article_data)

            assert result is None


class TestAnalyzeArticlesBatch:
    """Tests for the analyze_articles_batch federated activity."""

    @pytest.mark.asyncio
    async def test_returns_processed_articles(self, sample_raw_articles, sample_processed_articles):
        """Activity should return list of processed article dictionaries."""
        from news_monitor.federated_activities import analyze_articles_batch

        mock_result = MagicMock()
        mock_result.processed_articles = sample_processed_articles
        mock_result.articles_analyzed = 3
        mock_result.articles_failed = 0

        with patch("news_monitor.federated_activities.NewsAnalystAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.analyze_articles.return_value = mock_result
            mock_class.return_value = mock_instance

            articles_data = [a.model_dump() for a in sample_raw_articles]
            result = await analyze_articles_batch(articles_data)

            assert isinstance(result, list)
            assert len(result) == len(sample_processed_articles)
            assert all(isinstance(r, dict) for r in result)

    @pytest.mark.asyncio
    async def test_passes_deduplicate_flag(self, sample_raw_articles):
        """Activity should pass deduplicate flag to analyst."""
        from news_monitor.federated_activities import analyze_articles_batch

        mock_result = MagicMock()
        mock_result.processed_articles = []
        mock_result.articles_analyzed = 0
        mock_result.articles_failed = 0

        with patch("news_monitor.federated_activities.NewsAnalystAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.analyze_articles.return_value = mock_result
            mock_class.return_value = mock_instance

            articles_data = [a.model_dump() for a in sample_raw_articles]
            await analyze_articles_batch(articles_data, deduplicate=False)

            mock_instance.analyze_articles.assert_called_once()
            call_args = mock_instance.analyze_articles.call_args
            assert call_args.kwargs.get("deduplicate") is False


class TestDetectBreakingNews:
    """Tests for the detect_breaking_news federated activity."""

    @pytest.mark.asyncio
    async def test_returns_breaking_articles(
        self, sample_processed_articles, sample_breaking_article
    ):
        """Activity should return list of breaking news articles."""
        from news_monitor.federated_activities import detect_breaking_news

        with patch("news_monitor.federated_activities.NewsAnalystAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.detect_breaking_news.return_value = [sample_breaking_article]
            mock_class.return_value = mock_instance

            articles_data = [a.model_dump() for a in sample_processed_articles]
            result = await detect_breaking_news(articles_data)

            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["is_breaking"] is True

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_breaking(self, sample_processed_articles):
        """Activity should return empty list when no breaking news."""
        from news_monitor.federated_activities import detect_breaking_news

        with patch("news_monitor.federated_activities.NewsAnalystAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.detect_breaking_news.return_value = []
            mock_class.return_value = mock_instance

            articles_data = [a.model_dump() for a in sample_processed_articles]
            result = await detect_breaking_news(articles_data)

            assert result == []


class TestAnalyzeTrends:
    """Tests for the analyze_trends federated activity."""

    @pytest.mark.asyncio
    async def test_returns_trends(self, sample_processed_articles, sample_trends):
        """Activity should return list of trending topics."""
        from news_monitor.federated_activities import analyze_trends

        with patch("news_monitor.federated_activities.NewsAnalystAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.analyze_trends.return_value = sample_trends
            mock_class.return_value = mock_instance

            articles_data = [a.model_dump() for a in sample_processed_articles]
            result = await analyze_trends(articles_data)

            assert isinstance(result, list)
            assert len(result) == 1
            assert "topic" in result[0]

    @pytest.mark.asyncio
    async def test_returns_empty_with_few_articles(self):
        """Activity should return empty list with insufficient articles."""
        from news_monitor.federated_activities import analyze_trends

        with patch("news_monitor.federated_activities.NewsAnalystAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.analyze_trends.return_value = []
            mock_class.return_value = mock_instance

            result = await analyze_trends([])

            assert result == []


class TestComposeDigest:
    """Tests for the compose_digest federated activity."""

    @pytest.mark.asyncio
    async def test_returns_digest_dict(
        self, sample_processed_articles, sample_trends, sample_digest
    ):
        """Activity should return news digest dictionary."""
        from news_monitor.federated_activities import compose_digest

        with patch("news_monitor.federated_activities.NewsPublisherAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.compose_digest.return_value = sample_digest
            mock_class.return_value = mock_instance

            articles_data = [a.model_dump() for a in sample_processed_articles]
            trends_data = [t.model_dump() for t in sample_trends]
            result = await compose_digest(articles_data, trends_data, period_hours=12)

            assert isinstance(result, dict)
            assert "digest_id" in result
            assert "total_articles" in result

    @pytest.mark.asyncio
    async def test_passes_period_hours(
        self, sample_processed_articles, sample_trends, sample_digest
    ):
        """Activity should pass period_hours to publisher."""
        from news_monitor.federated_activities import compose_digest

        with patch("news_monitor.federated_activities.NewsPublisherAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.compose_digest.return_value = sample_digest
            mock_class.return_value = mock_instance

            articles_data = [a.model_dump() for a in sample_processed_articles]
            trends_data = [t.model_dump() for t in sample_trends]
            await compose_digest(articles_data, trends_data, period_hours=6)

            mock_instance.compose_digest.assert_called_once()
            call_args = mock_instance.compose_digest.call_args
            assert call_args.args[2] == 6  # period_hours


class TestPublishDigest:
    """Tests for the publish_digest federated activity."""

    @pytest.mark.asyncio
    async def test_returns_updated_digest(self, sample_digest):
        """Activity should return updated digest with message ID."""
        from news_monitor.federated_activities import publish_digest

        updated_digest = sample_digest.model_copy()
        updated_digest.discord_message_id = "msg-12345"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.digest = updated_digest

        with patch("news_monitor.federated_activities.NewsPublisherAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.publish_digest.return_value = mock_result
            mock_class.return_value = mock_instance

            digest_data = sample_digest.model_dump()
            result = await publish_digest(digest_data)

            assert isinstance(result, dict)
            assert result.get("discord_message_id") == "msg-12345"

    @pytest.mark.asyncio
    async def test_returns_original_on_failure(self, sample_digest):
        """Activity should return original digest when publish fails."""
        from news_monitor.federated_activities import publish_digest

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.digest = None

        with patch("news_monitor.federated_activities.NewsPublisherAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.publish_digest.return_value = mock_result
            mock_class.return_value = mock_instance

            digest_data = sample_digest.model_dump()
            result = await publish_digest(digest_data)

            assert result == digest_data


class TestPublishBreakingAlert:
    """Tests for the publish_breaking_alert federated activity."""

    @pytest.mark.asyncio
    async def test_returns_message_id(self, sample_breaking_article):
        """Activity should return Discord message ID on success."""
        from news_monitor.federated_activities import publish_breaking_alert

        mock_result = MagicMock()
        mock_result.message_id = "msg-breaking-123"

        with patch("news_monitor.federated_activities.NewsPublisherAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.publish_breaking_alert.return_value = mock_result
            mock_class.return_value = mock_instance

            article_data = sample_breaking_article.model_dump()
            result = await publish_breaking_alert(article_data)

            assert result == "msg-breaking-123"

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self, sample_breaking_article):
        """Activity should return None when publish fails."""
        from news_monitor.federated_activities import publish_breaking_alert

        mock_result = MagicMock()
        mock_result.message_id = None

        with patch("news_monitor.federated_activities.NewsPublisherAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.publish_breaking_alert.return_value = mock_result
            mock_class.return_value = mock_instance

            article_data = sample_breaking_article.model_dump()
            result = await publish_breaking_alert(article_data)

            assert result is None


class TestRunFullPipeline:
    """Tests for the run_full_pipeline federated activity."""

    @pytest.mark.asyncio
    async def test_returns_pipeline_results(
        self, sample_raw_articles, sample_processed_articles, sample_trends, sample_digest
    ):
        """Activity should run full pipeline and return stats."""
        from news_monitor.federated_activities import run_full_pipeline

        # Mock collection result
        mock_collection = MagicMock()
        mock_collection.articles = sample_raw_articles
        mock_collection.total_collected = 10

        # Mock analysis result
        mock_analysis = MagicMock()
        mock_analysis.processed_articles = sample_processed_articles
        mock_analysis.breaking_articles = []
        mock_analysis.trends = sample_trends

        # Mock publish result
        mock_publish = MagicMock()
        mock_publish.success = True
        mock_publish.digest = sample_digest

        with (
            patch("news_monitor.federated_activities.NewsCollectorAgent") as mock_collector_class,
            patch("news_monitor.federated_activities.NewsAnalystAgent") as mock_analyst_class,
            patch("news_monitor.federated_activities.NewsPublisherAgent") as mock_publisher_class,
        ):
            mock_collector = AsyncMock()
            mock_collector.collect.return_value = mock_collection
            mock_collector_class.return_value = mock_collector

            mock_analyst = AsyncMock()
            mock_analyst.full_analysis.return_value = mock_analysis
            mock_analyst_class.return_value = mock_analyst

            mock_publisher = AsyncMock()
            mock_publisher.compose_and_publish.return_value = mock_publish
            mock_publisher.publish_breaking_alert.return_value = MagicMock(message_id=None)
            mock_publisher_class.return_value = mock_publisher

            result = await run_full_pipeline(max_age_hours=24, period_hours=12)

            assert result["success"] is True
            assert result["articles_collected"] == 10
            assert result["articles_processed"] == 3
            assert result["digest_published"] is True

    @pytest.mark.asyncio
    async def test_returns_early_when_no_articles(self):
        """Activity should return early stats when no articles collected."""
        from news_monitor.federated_activities import run_full_pipeline

        mock_collection = MagicMock()
        mock_collection.articles = []

        with patch("news_monitor.federated_activities.NewsCollectorAgent") as mock_class:
            mock_instance = AsyncMock()
            mock_instance.collect.return_value = mock_collection
            mock_class.return_value = mock_instance

            result = await run_full_pipeline()

            assert result["success"] is True
            assert result["articles_collected"] == 0
            assert result["digest_published"] is False

    @pytest.mark.asyncio
    async def test_publishes_breaking_alerts(
        self,
        sample_raw_articles,
        sample_processed_articles,
        sample_breaking_article,
        sample_trends,
        sample_digest,
    ):
        """Activity should publish breaking alerts when detected."""
        from news_monitor.federated_activities import run_full_pipeline

        mock_collection = MagicMock()
        mock_collection.articles = sample_raw_articles
        mock_collection.total_collected = 3

        mock_analysis = MagicMock()
        mock_analysis.processed_articles = sample_processed_articles
        mock_analysis.breaking_articles = [sample_breaking_article]
        mock_analysis.trends = sample_trends

        mock_publish = MagicMock()
        mock_publish.success = True
        mock_publish.digest = sample_digest

        with (
            patch("news_monitor.federated_activities.NewsCollectorAgent") as mock_collector_class,
            patch("news_monitor.federated_activities.NewsAnalystAgent") as mock_analyst_class,
            patch("news_monitor.federated_activities.NewsPublisherAgent") as mock_publisher_class,
        ):
            mock_collector = AsyncMock()
            mock_collector.collect.return_value = mock_collection
            mock_collector_class.return_value = mock_collector

            mock_analyst = AsyncMock()
            mock_analyst.full_analysis.return_value = mock_analysis
            mock_analyst_class.return_value = mock_analyst

            mock_publisher = AsyncMock()
            mock_publisher.compose_and_publish.return_value = mock_publish
            mock_publisher.publish_breaking_alert.return_value = MagicMock(message_id="msg-123")
            mock_publisher_class.return_value = mock_publisher

            result = await run_full_pipeline()

            assert result["breaking_count"] == 1
            mock_publisher.publish_breaking_alert.assert_called_once()
