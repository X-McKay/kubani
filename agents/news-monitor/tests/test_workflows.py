"""
Tests for Temporal workflows.

These tests validate workflow orchestration logic.
Note: Temporal workflows require a proper workflow runtime context.
We test the activity functions directly and use integration tests for
full workflow validation.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Activity-Level Workflow Logic Tests
# =============================================================================
# Since Temporal workflows require a special runtime context, we test
# the activity orchestration patterns by testing the activities directly.


class TestWorkflowActivityPatterns:
    """Test the patterns that workflows use when calling activities."""

    @pytest.mark.asyncio
    async def test_empty_collection_skips_processing(self) -> None:
        """Empty article collection should short-circuit workflow."""
        from news_monitor.activities import collect_rss_feeds

        with patch("news_monitor.activities.RSSCollectorAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.collect_all.return_value = []
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=None)
            mock_class.return_value = mock_instance

            result = await collect_rss_feeds()

            assert result == []
            # Workflow would return {"status": "no_articles"} here

    @pytest.mark.asyncio
    async def test_filter_seen_urls_pattern(self) -> None:
        """filter_seen_urls activity pattern test."""
        from news_monitor.activities import filter_seen_urls

        articles = [
            {"url": "https://test.com/1", "title": "Test 1"},
            {"url": "https://test.com/2", "title": "Test 2"},
        ]

        # Simulate one URL already seen
        seen_urls = {"https://test.com/1"}

        with patch(
            "news_monitor.activities.is_url_seen",
            side_effect=lambda url: url in seen_urls,
        ):
            result = await filter_seen_urls(articles)

            assert len(result) == 1
            assert result[0]["url"] == "https://test.com/2"

    @pytest.mark.asyncio
    async def test_breaking_news_detection_pattern(self) -> None:
        """Breaking news detection activity pattern test."""
        from news_monitor.activities import check_breaking_news

        articles = [
            {
                "url": "u1",
                "title": "Breaking",
                "source": "Test",
                "source_category": "test",
                "importance_score": 9,
                "is_breaking": True,
            },
            {
                "url": "u2",
                "title": "Normal",
                "source": "Test",
                "source_category": "test",
                "importance_score": 5,
                "is_breaking": False,
            },
        ]

        result = await check_breaking_news(articles)

        assert len(result) == 1
        assert result[0]["title"] == "Breaking"


class TestWorkflowDataFlow:
    """Test data flows between activities as used by workflows."""

    @pytest.mark.asyncio
    async def test_full_article_pipeline(self, sample_raw_articles) -> None:
        """Test the full article processing pipeline pattern."""
        from news_monitor.activities import filter_seen_urls, process_articles
        from news_monitor.models import ArticleCategory, ProcessedArticle

        # Step 1: Filter (all new)
        articles_dicts = [a.model_dump() for a in sample_raw_articles]

        with patch("news_monitor.activities.is_url_seen", return_value=False):
            filtered = await filter_seen_urls(articles_dicts)

        assert len(filtered) == len(sample_raw_articles)

        # Step 2: Process
        with patch("news_monitor.activities.ContentAnalystAgent") as mock_class:
            mock_instance = MagicMock()

            def mock_analyze(article):
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

            processed = await process_articles(filtered)

        assert len(processed) == len(sample_raw_articles)
        assert all(p.get("importance_score") == 7 for p in processed)

    @pytest.mark.asyncio
    async def test_digest_generation_pipeline(
        self, sample_processed_articles, sample_trends
    ) -> None:
        """Test the digest generation pipeline pattern."""
        from datetime import datetime

        from news_monitor.activities import analyze_trends, compose_digest
        from news_monitor.models import NewsDigest

        articles_dicts = [a.model_dump() for a in sample_processed_articles]

        # Step 1: Analyze trends
        with patch("news_monitor.activities.TrendAnalyzerAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.analyze_trends.return_value = sample_trends
            mock_class.return_value = mock_instance

            trends = await analyze_trends(articles_dicts)

        assert len(trends) == len(sample_trends)

        # Step 2: Compose digest
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

            digest = await compose_digest(articles_dicts, trends, period_hours=4)

        assert digest["digest_id"] == "test-123"


class TestWorkflowEdgeCases:
    """Test edge cases in workflow patterns."""

    @pytest.mark.asyncio
    async def test_all_duplicates_filtered(self) -> None:
        """All duplicates should result in empty list."""
        from news_monitor.activities import filter_seen_urls

        articles = [
            {"url": "https://test.com/1", "title": "Test 1"},
            {"url": "https://test.com/2", "title": "Test 2"},
        ]

        # All URLs already seen
        with patch("news_monitor.activities.is_url_seen", return_value=True):
            result = await filter_seen_urls(articles)

        assert result == []
        # Workflow would return {"status": "no_new_articles"}

    @pytest.mark.asyncio
    async def test_no_breaking_news_in_batch(self) -> None:
        """No breaking news should result in empty list."""
        from news_monitor.activities import check_breaking_news

        articles = [
            {
                "url": "u1",
                "title": "Normal 1",
                "source": "Test",
                "source_category": "test",
                "importance_score": 5,
                "is_breaking": False,
            },
            {
                "url": "u2",
                "title": "Normal 2",
                "source": "Test",
                "source_category": "test",
                "importance_score": 6,
                "is_breaking": False,
            },
        ]

        result = await check_breaking_news(articles)

        assert result == []

    @pytest.mark.asyncio
    async def test_partial_deduplication(self) -> None:
        """Some articles should be filtered as duplicates."""
        from news_monitor.activities import deduplicate_single_article

        # First article is unique
        with (
            patch("news_monitor.activities.is_duplicate_article", return_value=False),
            patch("news_monitor.activities.store_article", return_value="mem-1"),
        ):
            result1 = await deduplicate_single_article(
                {
                    "url": "https://test.com/1",
                    "title": "Unique",
                    "source": "T",
                    "source_category": "t",
                }
            )
            assert result1 is not None

        # Second article is duplicate
        with patch("news_monitor.activities.is_duplicate_article", return_value=True):
            result2 = await deduplicate_single_article(
                {
                    "url": "https://test.com/2",
                    "title": "Duplicate",
                    "source": "T",
                    "source_category": "t",
                }
            )
            assert result2 is None


class TestContinueAsNewPattern:
    """Test the continue-as-new pattern used by scheduled workflows."""

    def test_scheduled_workflows_exist(self) -> None:
        """Verify scheduled workflow classes are defined."""
        from news_monitor.workflows import (
            ScheduledArticleIngestionWorkflow,
            ScheduledBreakingNewsWorkflow,
            ScheduledDigestGenerationWorkflow,
            ScheduledNewsDigestWorkflow,
        )

        # Verify they exist and have run methods
        assert hasattr(ScheduledArticleIngestionWorkflow, "run")
        assert hasattr(ScheduledDigestGenerationWorkflow, "run")
        assert hasattr(ScheduledBreakingNewsWorkflow, "run")
        assert hasattr(ScheduledNewsDigestWorkflow, "run")

    def test_child_workflows_exist(self) -> None:
        """Verify child workflow classes are defined."""
        from news_monitor.workflows import (
            ArticleIngestionWorkflow,
            BreakingNewsCheckWorkflow,
            DigestGenerationWorkflow,
            NewsDigestWorkflow,
            ProcessSingleArticleWorkflow,
        )

        # Verify they exist and have run methods
        assert hasattr(ArticleIngestionWorkflow, "run")
        assert hasattr(DigestGenerationWorkflow, "run")
        assert hasattr(BreakingNewsCheckWorkflow, "run")
        assert hasattr(NewsDigestWorkflow, "run")
        assert hasattr(ProcessSingleArticleWorkflow, "run")


class TestWorkflowReturnValues:
    """Test that activities return values suitable for workflow consumption."""

    @pytest.mark.asyncio
    async def test_collect_returns_serializable_dicts(self, sample_raw_articles) -> None:
        """collect_rss_feeds should return JSON-serializable dicts."""
        from news_monitor.activities import collect_rss_feeds

        with patch("news_monitor.activities.RSSCollectorAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.collect_all.return_value = sample_raw_articles
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=None)
            mock_class.return_value = mock_instance

            result = await collect_rss_feeds()

            # All results should be dicts (JSON-serializable for Temporal)
            assert all(isinstance(r, dict) for r in result)
            # Should have expected keys
            for r in result:
                assert "url" in r
                assert "title" in r
                assert "source" in r

    @pytest.mark.asyncio
    async def test_digest_returns_serializable_dict(self, sample_processed_articles) -> None:
        """compose_digest should return JSON-serializable dict."""
        from datetime import timedelta

        from news_monitor.activities import compose_digest
        from news_monitor.models import NewsDigest

        articles_dicts = [a.model_dump() for a in sample_processed_articles]
        trends = []

        now = datetime.utcnow()
        mock_digest = NewsDigest(
            digest_id="test-123",
            period_start=now - timedelta(hours=4),
            period_end=now,
            headline_summary="Test",
            total_articles=len(articles_dicts),
        )

        with patch("news_monitor.activities.DigestComposerAgent") as mock_class:
            mock_instance = MagicMock()
            mock_instance.compose_digest.return_value = mock_digest
            mock_class.return_value = mock_instance

            result = await compose_digest(articles_dicts, trends, period_hours=4)

            assert isinstance(result, dict)
            assert "digest_id" in result
            assert "headline_summary" in result
