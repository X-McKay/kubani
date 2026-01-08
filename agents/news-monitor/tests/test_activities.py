"""
Tests for Temporal activities.

These tests validate activity behavior with mocked dependencies:
- RSS collection activities
- Article processing activities
- Deduplication activities
- Publishing activities
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from news_monitor.models import ArticleCategory, ProcessedArticle, RawArticle


class TestCollectRSSFeeds:
    """Tests for the collect_rss_feeds activity."""

    @pytest.mark.asyncio
    async def test_returns_article_dicts(self, sample_raw_articles) -> None:
        """Activity should return list of article dictionaries."""
        from news_monitor.activities import collect_rss_feeds

        with patch("news_monitor.activities.RSSCollectorAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.collect_all.return_value = sample_raw_articles
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=None)
            mock_class.return_value = mock_instance

            result = await collect_rss_feeds(max_age_hours=24)

            assert isinstance(result, list)
            assert len(result) == len(sample_raw_articles)
            assert all(isinstance(r, dict) for r in result)
            assert all("url" in r and "title" in r for r in result)

    @pytest.mark.asyncio
    async def test_respects_max_age(self) -> None:
        """Activity should pass max_age_hours to collector."""
        from news_monitor.activities import collect_rss_feeds

        with patch("news_monitor.activities.RSSCollectorAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.collect_all.return_value = []
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=None)
            mock_class.return_value = mock_instance

            await collect_rss_feeds(max_age_hours=6)

            mock_class.assert_called_with(max_age_hours=6)

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_articles(self) -> None:
        """Activity should return empty list when no articles found."""
        from news_monitor.activities import collect_rss_feeds

        with patch("news_monitor.activities.RSSCollectorAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.collect_all.return_value = []
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=None)
            mock_class.return_value = mock_instance

            result = await collect_rss_feeds()

            assert result == []


class TestFilterSeenUrls:
    """Tests for the filter_seen_urls activity."""

    @pytest.mark.asyncio
    async def test_filters_seen_urls(self, mock_memory, sample_raw_articles) -> None:
        """Activity should filter out already-seen URLs."""
        from news_monitor.activities import filter_seen_urls

        # Mark first two URLs as seen
        articles_dicts = [a.model_dump() for a in sample_raw_articles]
        mock_memory.mark_url_seen(articles_dicts[0]["url"])
        mock_memory.mark_url_seen(articles_dicts[1]["url"])

        result = await filter_seen_urls(articles_dicts)

        assert len(result) == len(sample_raw_articles) - 2
        urls = [a["url"] for a in result]
        assert articles_dicts[0]["url"] not in urls
        assert articles_dicts[1]["url"] not in urls

    @pytest.mark.asyncio
    async def test_returns_all_when_none_seen(self, mock_memory, sample_raw_articles) -> None:
        """Activity should return all articles when none are seen."""
        from news_monitor.activities import filter_seen_urls

        articles_dicts = [a.model_dump() for a in sample_raw_articles]

        result = await filter_seen_urls(articles_dicts)

        assert len(result) == len(sample_raw_articles)


class TestProcessArticles:
    """Tests for the process_articles activity."""

    @pytest.mark.asyncio
    async def test_returns_processed_articles(self, sample_raw_articles) -> None:
        """Activity should return processed article dictionaries."""
        from news_monitor.activities import process_articles

        articles_dicts = [a.model_dump() for a in sample_raw_articles]

        with patch("news_monitor.activities.ContentAnalystAgent") as mock_class:
            mock_instance = MagicMock()

            def mock_analyze(article: RawArticle) -> ProcessedArticle:
                return ProcessedArticle(
                    url=article.url,
                    title=article.title,
                    source=article.source,
                    source_category=article.source_category,
                    importance_score=7,
                    category=ArticleCategory.GENERAL,
                )

            mock_instance.analyze_article = mock_analyze
            mock_class.return_value = mock_instance

            result = await process_articles(articles_dicts)

            assert len(result) == len(sample_raw_articles)
            assert all("importance_score" in r for r in result)

    @pytest.mark.asyncio
    async def test_handles_partial_failures(self) -> None:
        """Activity should continue processing when some articles fail."""
        from news_monitor.activities import process_articles

        articles = [
            {
                "url": "https://test.com/1",
                "title": "Good",
                "source": "Test",
                "source_category": "test",
            },
            {
                "url": "https://test.com/2",
                "title": "Bad",
                "source": "Test",
                "source_category": "test",
            },
            {
                "url": "https://test.com/3",
                "title": "Good",
                "source": "Test",
                "source_category": "test",
            },
        ]

        with patch("news_monitor.activities.ContentAnalystAgent") as mock_class:
            mock_instance = MagicMock()
            call_count = [0]

            def mock_analyze(article: RawArticle) -> ProcessedArticle:
                call_count[0] += 1
                if "Bad" in article.title:
                    raise ValueError("Processing failed")
                return ProcessedArticle(
                    url=article.url,
                    title=article.title,
                    source=article.source,
                    source_category=article.source_category,
                    importance_score=5,
                )

            mock_instance.analyze_article = mock_analyze
            mock_class.return_value = mock_instance

            result = await process_articles(articles)

            # Should have processed 2 successfully, 1 failed
            assert len(result) == 2


class TestDeduplicateSingleArticle:
    """Tests for the deduplicate_single_article activity."""

    @pytest.mark.asyncio
    async def test_returns_unique_article(self, mock_memory, sample_processed_article) -> None:
        """Activity should return article if unique."""
        from news_monitor.activities import deduplicate_single_article

        result = await deduplicate_single_article(sample_processed_article.model_dump())

        assert result is not None
        assert result["url"] == sample_processed_article.url

    @pytest.mark.asyncio
    async def test_returns_none_for_duplicate(self, sample_processed_article) -> None:
        """Activity should return None for duplicate articles."""
        from news_monitor.activities import deduplicate_single_article

        with (
            patch("news_monitor.activities.is_duplicate_article", return_value=True),
            patch("news_monitor.activities.store_article"),
        ):
            result = await deduplicate_single_article(sample_processed_article.model_dump())

            assert result is None


class TestAnalyzeTrends:
    """Tests for the analyze_trends activity."""

    @pytest.mark.asyncio
    async def test_returns_trend_dicts(self, sample_processed_articles) -> None:
        """Activity should return list of trend dictionaries."""
        from news_monitor.activities import analyze_trends
        from news_monitor.models import TrendingTopic, TrendStatus

        articles_dicts = [a.model_dump() for a in sample_processed_articles]

        with patch("news_monitor.activities.TrendAnalyzerAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.analyze_trends.return_value = [
                TrendingTopic(
                    topic="GPT-5",
                    status=TrendStatus.HOT,
                    article_count=2,
                    first_seen=datetime.utcnow(),
                    last_seen=datetime.utcnow(),
                    sources=["OpenAI"],
                )
            ]
            mock_class.return_value = mock_instance

            result = await analyze_trends(articles_dicts)

            assert len(result) == 1
            assert result[0]["topic"] == "GPT-5"
            assert result[0]["status"] == "hot"


class TestComposeDigest:
    """Tests for the compose_digest activity."""

    @pytest.mark.asyncio
    async def test_returns_digest_dict(self, sample_processed_articles, sample_trends) -> None:
        """Activity should return a digest dictionary."""
        from news_monitor.activities import compose_digest
        from news_monitor.models import NewsDigest

        articles_dicts = [a.model_dump() for a in sample_processed_articles]
        trends_dicts = [t.model_dump() for t in sample_trends]

        now = datetime.utcnow()
        mock_digest = NewsDigest(
            digest_id="test-123",
            period_start=now - timedelta(hours=4),
            period_end=now,
            headline_summary="Test summary",
            total_articles=len(articles_dicts),
        )

        with patch("news_monitor.activities.DigestComposerAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.compose_digest.return_value = mock_digest
            mock_class.return_value = mock_instance

            result = await compose_digest(articles_dicts, trends_dicts, period_hours=4)

            assert "digest_id" in result
            assert result["headline_summary"] == "Test summary"


class TestPublishDigest:
    """Tests for the publish_digest activity."""

    @pytest.mark.asyncio
    async def test_returns_updated_digest(self, sample_digest) -> None:
        """Activity should return digest with message ID."""
        from news_monitor.activities import publish_digest

        with (
            patch("news_monitor.activities.DigestComposerAgent") as mock_composer,
            patch("news_monitor.activities.DiscordPublisherAgent") as mock_publisher,
            patch("news_monitor.activities.store_digest_record"),
        ):
            mock_composer.return_value.format_for_discord.return_value = "formatted"
            mock_publisher.return_value.publish_digest.return_value = "msg-123"

            result = await publish_digest(sample_digest.model_dump())

            assert result["published"] is True
            assert result["discord_message_id"] == "msg-123"

    @pytest.mark.asyncio
    async def test_handles_publish_failure(self, sample_digest) -> None:
        """Activity should handle Discord publish failure."""
        from news_monitor.activities import publish_digest

        with (
            patch("news_monitor.activities.DigestComposerAgent") as mock_composer,
            patch("news_monitor.activities.DiscordPublisherAgent") as mock_publisher,
            patch("news_monitor.activities.store_digest_record"),
        ):
            mock_composer.return_value.format_for_discord.return_value = "formatted"
            mock_publisher.return_value.publish_digest.return_value = None  # Failure

            result = await publish_digest(sample_digest.model_dump())

            assert result["published"] is False
            assert result["discord_message_id"] is None


class TestCheckBreakingNews:
    """Tests for the check_breaking_news activity."""

    @pytest.mark.asyncio
    async def test_identifies_breaking_articles(self) -> None:
        """Activity should identify high-importance breaking articles."""
        from news_monitor.activities import check_breaking_news

        articles = [
            {
                "url": "https://test.com/1",
                "title": "Breaking",
                "source": "Test",
                "source_category": "test",
                "importance_score": 9,
                "is_breaking": True,
            },
            {
                "url": "https://test.com/2",
                "title": "Normal",
                "source": "Test",
                "source_category": "test",
                "importance_score": 5,
                "is_breaking": False,
            },
            {
                "url": "https://test.com/3",
                "title": "Important but not breaking",
                "source": "Test",
                "source_category": "test",
                "importance_score": 8,
                "is_breaking": False,
            },
        ]

        result = await check_breaking_news(articles)

        assert len(result) == 1
        assert result[0]["title"] == "Breaking"

    @pytest.mark.asyncio
    async def test_requires_both_breaking_and_high_importance(self) -> None:
        """Breaking flag AND high importance required."""
        from news_monitor.activities import check_breaking_news

        articles = [
            {
                "url": "https://test.com/1",
                "title": "Breaking but low importance",
                "source": "Test",
                "source_category": "test",
                "importance_score": 5,
                "is_breaking": True,
            },
        ]

        result = await check_breaking_news(articles)

        assert len(result) == 0  # Score < 8


class TestPublishBreakingAlert:
    """Tests for the publish_breaking_alert activity."""

    @pytest.mark.asyncio
    async def test_publishes_alert(self, breaking_news_article) -> None:
        """Activity should publish breaking alert and return message ID."""
        from news_monitor.activities import publish_breaking_alert

        with (
            patch("news_monitor.activities.DigestComposerAgent") as mock_composer,
            patch("news_monitor.activities.DiscordPublisherAgent") as mock_publisher,
            patch("news_monitor.activities.try_claim_breaking_alert") as mock_claim,
        ):
            mock_claim.return_value = True  # Successfully claimed
            mock_composer.return_value.format_breaking_alert.return_value = "alert"
            mock_publisher.return_value.publish_breaking_alert.return_value = "msg-456"

            result = await publish_breaking_alert(breaking_news_article.model_dump())

            assert result == "msg-456"
            mock_claim.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_already_sent(self, breaking_news_article) -> None:
        """Activity should skip publishing if alert was already claimed."""
        from news_monitor.activities import publish_breaking_alert

        with (
            patch("news_monitor.activities.try_claim_breaking_alert") as mock_claim,
            patch("news_monitor.activities.DiscordPublisherAgent") as mock_publisher,
        ):
            mock_claim.return_value = False  # Already claimed by another worker

            result = await publish_breaking_alert(breaking_news_article.model_dump())

            assert result is None
            mock_publisher.return_value.publish_breaking_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_fails_closed_when_redis_unavailable(self, breaking_news_article) -> None:
        """Activity should skip publishing if Redis is unavailable (fail-closed)."""
        from news_monitor.activities import publish_breaking_alert

        with (
            patch("news_monitor.activities.try_claim_breaking_alert") as mock_claim,
            patch("news_monitor.activities.DiscordPublisherAgent") as mock_publisher,
        ):
            mock_claim.return_value = None  # Redis unavailable

            result = await publish_breaking_alert(breaking_news_article.model_dump())

            assert result is None
            mock_publisher.return_value.publish_breaking_alert.assert_not_called()


class TestProcessSingleArticle:
    """Tests for the process_single_article activity."""

    @pytest.mark.asyncio
    async def test_processes_article(self, sample_raw_article) -> None:
        """Activity should process and return article dict."""
        from news_monitor.activities import process_single_article

        with patch("news_monitor.activities.ContentAnalystAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.analyze_article.return_value = ProcessedArticle(
                url=sample_raw_article.url,
                title=sample_raw_article.title,
                source=sample_raw_article.source,
                source_category=sample_raw_article.source_category,
                importance_score=8,
            )
            mock_class.return_value = mock_instance

            result = await process_single_article(sample_raw_article.model_dump())

            assert result is not None
            assert result["importance_score"] == 8

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self, sample_raw_article) -> None:
        """Activity should return None on processing failure."""
        from news_monitor.activities import process_single_article

        with patch("news_monitor.activities.ContentAnalystAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.analyze_article.side_effect = Exception("LLM timeout")
            mock_class.return_value = mock_instance

            result = await process_single_article(sample_raw_article.model_dump())

            assert result is None


class TestDeduplicateAndStoreArticle:
    """Tests for the deduplicate_and_store_article activity."""

    @pytest.mark.asyncio
    async def test_stores_unique_article(self, sample_processed_article) -> None:
        """Activity should store unique article and return it."""
        from news_monitor.activities import deduplicate_and_store_article

        with (
            patch("news_monitor.activities.is_duplicate_article", return_value=False),
            patch("news_monitor.activities.store_article", return_value="mem-123"),
        ):
            result = await deduplicate_and_store_article(sample_processed_article.model_dump())

            assert result is not None
            assert result["url"] == sample_processed_article.url

    @pytest.mark.asyncio
    async def test_returns_none_for_duplicate(self, sample_processed_article) -> None:
        """Activity should return None for duplicate."""
        from news_monitor.activities import deduplicate_and_store_article

        with patch("news_monitor.activities.is_duplicate_article", return_value=True):
            result = await deduplicate_and_store_article(sample_processed_article.model_dump())

            assert result is None

    @pytest.mark.asyncio
    async def test_returns_article_on_store_failure(self, sample_processed_article) -> None:
        """Activity should still return article if store fails (article is unique)."""
        from news_monitor.activities import deduplicate_and_store_article

        with (
            patch("news_monitor.activities.is_duplicate_article", return_value=False),
            patch("news_monitor.activities.store_article", return_value=None),  # Store failed
        ):
            result = await deduplicate_and_store_article(sample_processed_article.model_dump())

            # Should still return the article since it's unique
            assert result is not None


class TestCheckAndAlertBreaking:
    """Tests for the check_and_alert_breaking activity."""

    @pytest.mark.asyncio
    async def test_publishes_for_breaking_news(self, breaking_news_article) -> None:
        """Activity should publish alert for breaking news."""
        from news_monitor.activities import check_and_alert_breaking

        with (
            patch("news_monitor.activities.DigestComposerAgent") as mock_composer,
            patch("news_monitor.activities.DiscordPublisherAgent") as mock_publisher,
            patch("news_monitor.activities.try_claim_breaking_alert") as mock_claim,
        ):
            mock_claim.return_value = True  # Successfully claimed
            mock_composer.return_value.format_breaking_alert.return_value = "alert"
            mock_publisher.return_value.publish_breaking_alert.return_value = "msg-789"

            result = await check_and_alert_breaking(breaking_news_article.model_dump())

            assert result is True
            mock_claim.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_non_breaking(self, sample_processed_article) -> None:
        """Activity should skip non-breaking articles."""
        from news_monitor.activities import check_and_alert_breaking

        # Modify to non-breaking
        article_data = sample_processed_article.model_dump()
        article_data["is_breaking"] = False
        article_data["importance_score"] = 5

        result = await check_and_alert_breaking(article_data)

        assert result is False

    @pytest.mark.asyncio
    async def test_skips_when_alert_already_sent(self, breaking_news_article) -> None:
        """Activity should skip if alert was already claimed."""
        from news_monitor.activities import check_and_alert_breaking

        with (
            patch("news_monitor.activities.try_claim_breaking_alert") as mock_claim,
            patch("news_monitor.activities.DiscordPublisherAgent") as mock_publisher,
        ):
            mock_claim.return_value = False  # Already claimed by another worker

            result = await check_and_alert_breaking(breaking_news_article.model_dump())

            assert result is False
            mock_publisher.return_value.publish_breaking_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_fails_closed_when_redis_unavailable(self, breaking_news_article) -> None:
        """Activity should skip if Redis unavailable (fail-closed)."""
        from news_monitor.activities import check_and_alert_breaking

        with (
            patch("news_monitor.activities.try_claim_breaking_alert") as mock_claim,
            patch("news_monitor.activities.DiscordPublisherAgent") as mock_publisher,
        ):
            mock_claim.return_value = None  # Redis unavailable

            result = await check_and_alert_breaking(breaking_news_article.model_dump())

            assert result is False
            mock_publisher.return_value.publish_breaking_alert.assert_not_called()


class TestQueryRecentArticles:
    """Tests for the query_recent_articles activity."""

    @pytest.mark.asyncio
    async def test_queries_by_period(self) -> None:
        """Activity should query articles from specified period."""
        from news_monitor.activities import query_recent_articles

        mock_articles = [
            {"url": "https://test.com/1", "title": "Recent 1"},
            {"url": "https://test.com/2", "title": "Recent 2"},
        ]

        with patch("news_monitor.activities.query_articles_since", return_value=mock_articles):
            result = await query_recent_articles(period_hours=4)

            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_articles(self) -> None:
        """Activity should return empty list when no articles found."""
        from news_monitor.activities import query_recent_articles

        with patch("news_monitor.activities.query_articles_since", return_value=[]):
            result = await query_recent_articles(period_hours=4)

            assert result == []
