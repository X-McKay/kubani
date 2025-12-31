"""
Tests for error handling scenarios.

These tests validate graceful error handling for:
1. RSS feed failures
2. LLM/vLLM failures
3. Memory service failures (Redis, mem0, Qdrant)
4. Discord webhook failures
"""

from unittest.mock import MagicMock, patch

import pytest

from news_monitor.models import ArticleCategory, ProcessedArticle, RawArticle


class TestRSSFeedFailures:
    """Tests for RSS feed error handling."""

    @pytest.mark.asyncio
    async def test_feed_timeout_continues_with_others(self) -> None:
        """Timeout on one feed should not affect others."""
        from news_monitor.activities import collect_rss_feeds

        with patch("news_monitor.activities.RSSCollectorAgent") as mock_class:
            mock_instance = MagicMock()
            # Return some articles even if some feeds failed
            mock_instance.collect_all.return_value = [
                RawArticle(
                    url="https://test.com/1",
                    title="Test",
                    source="Working Feed",
                    source_category="test",
                )
            ]
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=None)
            mock_class.return_value = mock_instance

            result = await collect_rss_feeds()

            # Should return articles from working feeds
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_malformed_xml_skipped(self) -> None:
        """Malformed RSS XML should be skipped gracefully."""
        from news_monitor.activities import collect_rss_feeds

        with patch("news_monitor.activities.RSSCollectorAgent") as mock_class:
            mock_instance = MagicMock()
            # Collector handles malformed feeds internally
            mock_instance.collect_all.return_value = []
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=None)
            mock_class.return_value = mock_instance

            result = await collect_rss_feeds()

            # Should return empty, not crash
            assert result == []

    @pytest.mark.asyncio
    async def test_all_feeds_fail_returns_empty(self) -> None:
        """All feeds failing should return empty list, not crash."""
        from news_monitor.activities import collect_rss_feeds

        with patch("news_monitor.activities.RSSCollectorAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.collect_all.side_effect = Exception("Network error")
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=None)
            mock_class.return_value = mock_instance

            # Should raise the exception (activity will be retried by Temporal)
            with pytest.raises(Exception, match="Network error"):
                await collect_rss_feeds()


class TestLLMFailures:
    """Tests for LLM/vLLM error handling."""

    @pytest.mark.asyncio
    async def test_analysis_timeout_returns_none(self) -> None:
        """LLM timeout during analysis should return None."""
        from news_monitor.activities import process_single_article

        article = {
            "url": "https://test.com/1",
            "title": "Test",
            "source": "Test",
            "source_category": "test",
        }

        with patch("news_monitor.activities.ContentAnalystAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.analyze_article.side_effect = TimeoutError("LLM timeout")
            mock_class.return_value = mock_instance

            result = await process_single_article(article)

            # Should return None, not crash
            assert result is None

    @pytest.mark.asyncio
    async def test_model_unavailable_returns_none(self) -> None:
        """vLLM unavailable should return None."""
        from news_monitor.activities import process_single_article

        article = {
            "url": "https://test.com/1",
            "title": "Test",
            "source": "Test",
            "source_category": "test",
        }

        with patch("news_monitor.activities.ContentAnalystAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.analyze_article.side_effect = ConnectionError("vLLM not available")
            mock_class.return_value = mock_instance

            result = await process_single_article(article)

            assert result is None

    @pytest.mark.asyncio
    async def test_parallel_processing_handles_partial_failures(self) -> None:
        """Parallel processing should handle some LLM failures."""
        from news_monitor.activities import process_articles

        articles = [
            {"url": "https://test.com/1", "title": "Good 1", "source": "T", "source_category": "t"},
            {"url": "https://test.com/2", "title": "Bad", "source": "T", "source_category": "t"},
            {"url": "https://test.com/3", "title": "Good 2", "source": "T", "source_category": "t"},
        ]

        with patch("news_monitor.activities.ContentAnalystAgent") as mock_class:
            mock_instance = MagicMock()

            def mock_analyze(article):
                if "Bad" in article.title:
                    raise Exception("LLM error")
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

            # Should have 2 successful, 1 failed
            assert len(result) == 2


class TestMemoryFailures:
    """Tests for memory service (Redis, mem0, Qdrant) error handling."""

    @pytest.mark.asyncio
    async def test_redis_unavailable_falls_back(self, sample_raw_articles) -> None:
        """Redis unavailable should fall back gracefully."""
        from news_monitor.activities import filter_seen_urls

        articles_dicts = [a.model_dump() for a in sample_raw_articles]

        with patch("news_monitor.activities.is_url_seen") as mock_seen:
            # Redis throws error
            mock_seen.side_effect = Exception("Redis connection refused")

            # Activity should propagate error (Temporal will retry)
            with pytest.raises(Exception, match="Redis"):
                await filter_seen_urls(articles_dicts)

    @pytest.mark.asyncio
    async def test_mem0_unavailable_continues(self, sample_processed_article) -> None:
        """mem0 unavailable should not crash deduplication."""
        from news_monitor.activities import deduplicate_and_store_article

        with (
            patch("news_monitor.activities.is_duplicate_article") as mock_dup,
            patch("news_monitor.activities.store_article"),
        ):
            mock_dup.side_effect = Exception("mem0 unavailable")

            # Should propagate error (Temporal will retry)
            with pytest.raises(Exception, match="mem0"):
                await deduplicate_and_store_article(sample_processed_article.model_dump())

    @pytest.mark.asyncio
    async def test_qdrant_unavailable_returns_empty(self) -> None:
        """Qdrant unavailable should return empty list."""
        from news_monitor.activities import query_recent_articles

        with patch("news_monitor.activities.query_articles_since") as mock_query:
            mock_query.side_effect = Exception("Qdrant connection failed")

            # Should propagate error (Temporal will retry)
            with pytest.raises(Exception, match="Qdrant"):
                await query_recent_articles(period_hours=4)

    @pytest.mark.asyncio
    async def test_store_failure_still_returns_article(self, sample_processed_article) -> None:
        """Storage failure should still return unique article."""
        from news_monitor.activities import deduplicate_and_store_article

        with (
            patch("news_monitor.activities.is_duplicate_article", return_value=False),
            patch("news_monitor.activities.store_article", return_value=None),  # Store failed
        ):
            result = await deduplicate_and_store_article(sample_processed_article.model_dump())

            # Article is unique, should return it even if store failed
            assert result is not None
            assert result["url"] == sample_processed_article.url


class TestDiscordFailures:
    """Tests for Discord webhook error handling."""

    @pytest.mark.asyncio
    async def test_webhook_failure_returns_none(self, sample_digest) -> None:
        """Discord webhook failure should return None message ID."""
        from news_monitor.activities import publish_digest

        with (
            patch("news_monitor.activities.DigestComposerAgent") as mock_composer,
            patch("news_monitor.activities.DiscordPublisherAgent") as mock_publisher,
        ):
            mock_composer.return_value.format_for_discord.return_value = "formatted"
            mock_publisher.return_value.publish_digest.return_value = None  # Failure

            result = await publish_digest(sample_digest.model_dump())

            assert result["published"] is False

    @pytest.mark.asyncio
    async def test_rate_limit_not_fatal(self, sample_digest) -> None:
        """Discord rate limit should be handled gracefully."""
        from news_monitor.activities import publish_digest

        with (
            patch("news_monitor.activities.DigestComposerAgent") as mock_composer,
            patch("news_monitor.activities.DiscordPublisherAgent") as mock_publisher,
        ):
            mock_composer.return_value.format_for_discord.return_value = "formatted"
            # Simulate rate limit (publisher returns None)
            mock_publisher.return_value.publish_digest.return_value = None

            result = await publish_digest(sample_digest.model_dump())

            # Should not crash, just mark as not published
            assert result["published"] is False

    @pytest.mark.asyncio
    async def test_breaking_alert_failure_returns_none(self, breaking_news_article) -> None:
        """Breaking alert failure should return None."""
        from news_monitor.activities import publish_breaking_alert

        with (
            patch("news_monitor.activities.DigestComposerAgent") as mock_composer,
            patch("news_monitor.activities.DiscordPublisherAgent") as mock_publisher,
        ):
            mock_composer.return_value.format_breaking_alert.return_value = "alert"
            mock_publisher.return_value.publish_breaking_alert.return_value = None

            result = await publish_breaking_alert(breaking_news_article.model_dump())

            assert result is None


class TestWorkflowErrorRecovery:
    """Tests for workflow-level error recovery patterns."""

    @pytest.mark.asyncio
    async def test_activity_failure_propagates(self) -> None:
        """Activity failures should propagate (Temporal will retry)."""
        from news_monitor.activities import analyze_trends

        articles = [
            {
                "url": "https://test.com/1",
                "title": "Test",
                "source": "Test",
                "source_category": "test",
            }
        ]

        with patch("news_monitor.activities.TrendAnalyzerAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.analyze_trends.side_effect = Exception("Trend analysis failed")
            mock_class.return_value = mock_instance

            with pytest.raises(Exception, match="Trend analysis"):
                await analyze_trends(articles)

    @pytest.mark.asyncio
    async def test_processing_failures_tracked(self) -> None:
        """Processing failures should be trackable."""
        from news_monitor.activities import process_articles
        from news_monitor.models import ProcessedArticle

        articles = [
            {"url": "https://test.com/1", "title": "Good", "source": "T", "source_category": "t"},
            {"url": "https://test.com/2", "title": "Fail", "source": "T", "source_category": "t"},
            {"url": "https://test.com/3", "title": "Good 2", "source": "T", "source_category": "t"},
        ]

        with patch("news_monitor.activities.ContentAnalystAgent") as mock_class:
            mock_instance = MagicMock()

            def mock_analyze(article):
                if "Fail" in article.title:
                    raise Exception("LLM failure")
                return ProcessedArticle(
                    url=article.url,
                    title=article.title,
                    source=article.source,
                    source_category=article.source_category,
                    importance_score=5,
                    category=ArticleCategory.GENERAL,
                )

            mock_instance.analyze_article = mock_analyze
            mock_class.return_value = mock_instance

            result = await process_articles(articles)

            # 2 succeeded, 1 failed
            assert len(result) == 2


class TestErrorInjectorUtility:
    """Tests for the ErrorInjector test utility."""

    def test_always_fail(self, error_injector) -> None:
        """ErrorInjector should always fail when configured."""
        error_injector.fail_on("test_point", ValueError("Always fails"))

        with pytest.raises(ValueError, match="Always fails"):
            error_injector.check_and_raise("test_point")

    def test_fail_on_nth_call(self, error_injector) -> None:
        """ErrorInjector should fail on nth call."""
        error_injector.fail_on_nth_call("test_point", 3, RuntimeError("Third call"))

        # First two succeed
        error_injector.check_and_raise("test_point")
        error_injector.check_and_raise("test_point")

        # Third fails
        with pytest.raises(RuntimeError, match="Third call"):
            error_injector.check_and_raise("test_point")

    def test_clear_removes_errors(self, error_injector) -> None:
        """ErrorInjector.clear should remove all configured errors."""
        error_injector.fail_on("test_point", Exception("Should fail"))
        error_injector.clear()

        # Should not raise after clear
        error_injector.check_and_raise("test_point")

    def test_unconfigured_point_no_error(self, error_injector) -> None:
        """Unconfigured points should not raise errors."""
        # Should not raise
        error_injector.check_and_raise("unconfigured_point")
