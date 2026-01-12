"""
Tests for the enhanced news monitor digest system.

Tests cover:
- Executive brief formatting
- Breaking news detection and routing
- Emoji feedback processing
- News monitor models
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestExecutiveBrief:
    """Tests for the Executive Brief formatter."""

    def test_content_category_enum(self):
        """Test ContentCategory enum values."""
        from news_monitor.digest.executive_brief import ContentCategory
        
        assert ContentCategory.RESEARCH.value == "research"
        assert ContentCategory.TOOLS.value == "tools"
        assert ContentCategory.SECURITY.value == "security"

    def test_news_urgency_enum(self):
        """Test NewsUrgency enum values."""
        from news_monitor.digest.executive_brief import NewsUrgency
        
        assert NewsUrgency.BREAKING.value == "breaking"
        assert NewsUrgency.HIGH.value == "high"
        assert NewsUrgency.NORMAL.value == "normal"

    def test_deep_dive_dataclass(self):
        """Test DeepDive dataclass."""
        from news_monitor.digest.executive_brief import DeepDive
        
        dive = DeepDive(
            title="New AI Research",
            source="arXiv",
            source_url="https://arxiv.org/abs/2601.01234",
            one_paragraph_summary="This paper presents...",
            key_takeaways=["Key point 1", "Key point 2"],
            practical_implications=["Use case 1"],
        )
        
        assert dive.title == "New AI Research"
        assert len(dive.key_takeaways) == 2
        assert dive.caveats == []

    def test_mini_brief_dataclass(self):
        """Test MiniBrief dataclass."""
        from news_monitor.digest.executive_brief import MiniBrief, ContentCategory
        
        brief = MiniBrief(
            title="New MCP Server",
            category=ContentCategory.TOOLS,
            what_it_is="A new tool for...",
            why_interesting="It enables...",
            who_its_for="Developers who...",
        )
        
        assert brief.title == "New MCP Server"
        assert brief.category == ContentCategory.TOOLS

    def test_security_alert_dataclass(self):
        """Test SecurityAlert dataclass."""
        from news_monitor.digest.executive_brief import SecurityAlert
        
        alert = SecurityAlert(
            title="Critical Vulnerability",
            impact="Remote code execution",
            affected="All versions < 2.0",
            mitigation="Upgrade to 2.0+",
            reference="CVE-2026-1234",
        )
        
        assert alert.title == "Critical Vulnerability"
        assert "CVE" in alert.reference

    def test_trend_indicator_dataclass(self):
        """Test TrendIndicator dataclass."""
        from news_monitor.digest.executive_brief import TrendIndicator
        
        trend = TrendIndicator(
            topic="AI Agents",
            direction="↑",
            description="Growing interest in agentic systems",
        )
        
        assert trend.topic == "AI Agents"
        assert trend.direction == "↑"


class TestBreakingNews:
    """Tests for the Breaking News handler."""

    def test_breaking_news_item_dataclass(self):
        """Test BreakingNewsItem dataclass."""
        from news_monitor.digest.breaking_news import BreakingNewsItem
        from news_monitor.models import ProcessedArticle
        
        article = ProcessedArticle(
            url="https://example.com/article",
            title="Major Security Breach",
            source="SecurityNews",
            source_category="security",
        )
        
        item = BreakingNewsItem(
            article=article,
            urgency_score=9.5,
            urgency_reason="Critical security vulnerability",
            category="security",
            impact_summary="Affects all users",
        )
        
        assert item.urgency_score == 9.5
        assert item.category == "security"

    def test_breaking_news_handler_initialization(self):
        """Test BreakingNewsHandler initialization."""
        from news_monitor.digest.breaking_news import BreakingNewsHandler
        
        handler = BreakingNewsHandler(
            discord_webhook_url="https://discord.com/api/webhooks/123",
            max_per_hour=5,
            min_interval_minutes=10,
        )
        
        assert handler.max_per_hour == 5
        assert handler.discord_webhook_url == "https://discord.com/api/webhooks/123"

    def test_breaking_news_classifier_exists(self):
        """Test BreakingNewsClassifier exists."""
        from news_monitor.digest.breaking_news import BreakingNewsClassifier
        
        classifier = BreakingNewsClassifier()
        assert classifier is not None

    def test_relevance_filter_exists(self):
        """Test RelevanceFilter exists."""
        from news_monitor.digest.breaking_news import RelevanceFilter
        
        filter_obj = RelevanceFilter()
        assert filter_obj is not None
        assert hasattr(filter_obj, 'HIGH_RELEVANCE_KEYWORDS')


class TestFeedbackHandler:
    """Tests for the Emoji Feedback handler."""

    def test_feedback_type_enum(self):
        """Test FeedbackType enum values."""
        from news_monitor.digest.feedback import FeedbackType
        
        assert FeedbackType.POSITIVE.value == "positive"
        assert FeedbackType.NEGATIVE.value == "negative"
        assert FeedbackType.INTERESTED.value == "interested"

    def test_feedback_event_dataclass(self):
        """Test FeedbackEvent dataclass."""
        from news_monitor.digest.feedback import FeedbackEvent, FeedbackType
        
        event = FeedbackEvent(
            message_id="msg-123",
            channel_id="channel-456",
            user_id="user-789",
            emoji="👍",
            feedback_type=FeedbackType.POSITIVE,
        )
        
        assert event.message_id == "msg-123"
        assert event.feedback_type == FeedbackType.POSITIVE

    def test_emoji_mapping(self):
        """Test emoji to feedback type mapping."""
        from news_monitor.digest.feedback import EMOJI_MAPPING, FeedbackType
        
        # Check that emoji mappings are defined
        assert len(EMOJI_MAPPING) > 0
        assert EMOJI_MAPPING["👍"] == FeedbackType.POSITIVE
        assert EMOJI_MAPPING["👎"] == FeedbackType.NEGATIVE

    def test_feedback_aggregation_dataclass(self):
        """Test FeedbackAggregation dataclass."""
        from news_monitor.digest.feedback import FeedbackAggregation
        
        agg = FeedbackAggregation(
            item_id="article-123",
            total_reactions=10,
            positive_count=5,
            interested_count=3,
            negative_count=2,
        )
        
        assert agg.item_id == "article-123"
        assert agg.total_reactions == 10

    def test_feedback_aggregation_engagement_score(self):
        """Test FeedbackAggregation engagement score calculation."""
        from news_monitor.digest.feedback import FeedbackAggregation
        
        agg = FeedbackAggregation(
            item_id="article-123",
            total_reactions=10,
            positive_count=5,
            interested_count=3,
            actionable_count=2,
            negative_count=0,
        )
        
        score = agg.engagement_score
        assert 0 <= score <= 1

    def test_feedback_aggregation_zero_reactions(self):
        """Test FeedbackAggregation with zero reactions."""
        from news_monitor.digest.feedback import FeedbackAggregation
        
        agg = FeedbackAggregation(item_id="article-123")
        
        assert agg.engagement_score == 0.0


class TestNewsMonitorModels:
    """Tests for the news monitor models."""

    def test_article_category_enum(self):
        """Test ArticleCategory enum values."""
        from news_monitor.models import ArticleCategory
        
        assert ArticleCategory.RESEARCH.value == "research"
        assert ArticleCategory.BUSINESS.value == "business"
        assert ArticleCategory.SECURITY.value == "security"

    def test_trend_status_enum(self):
        """Test TrendStatus enum values."""
        from news_monitor.models import TrendStatus
        
        assert TrendStatus.BREAKING.value == "breaking"
        assert TrendStatus.HOT.value == "hot"
        assert TrendStatus.RISING.value == "rising"

    def test_raw_article_model(self):
        """Test RawArticle model."""
        from news_monitor.models import RawArticle
        
        article = RawArticle(
            url="https://example.com/article",
            title="Test Article",
            source="TestSource",
            source_category="tech",
        )
        
        assert article.url == "https://example.com/article"
        assert article.title == "Test Article"

    def test_processed_article_model(self):
        """Test ProcessedArticle model."""
        from news_monitor.models import ProcessedArticle, ArticleCategory
        
        article = ProcessedArticle(
            url="https://example.com/article",
            title="Test Article",
            source="TestSource",
            source_category="tech",
            ai_summary="This article discusses...",
            category=ArticleCategory.RESEARCH,
            importance_score=8,
        )
        
        assert article.importance_score == 8
        assert article.category == ArticleCategory.RESEARCH

    def test_trending_topic_model(self):
        """Test TrendingTopic model."""
        from news_monitor.models import TrendingTopic, TrendStatus
        
        topic = TrendingTopic(
            topic="AI Agents",
            status=TrendStatus.HOT,
            article_count=10,
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )
        
        assert topic.topic == "AI Agents"
        assert topic.status == TrendStatus.HOT

    def test_news_digest_model(self):
        """Test NewsDigest model."""
        from news_monitor.models import NewsDigest
        
        digest = NewsDigest(
            digest_id="digest-123",
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            headline_summary="Key news today...",
        )
        
        assert digest.digest_id == "digest-123"
        assert digest.published is False

    def test_breaking_news_alert_model(self):
        """Test BreakingNewsAlert model."""
        from news_monitor.models import BreakingNewsAlert, ProcessedArticle
        
        article = ProcessedArticle(
            url="https://example.com",
            title="Breaking News",
            source="NewsSource",
            source_category="tech",
        )
        
        alert = BreakingNewsAlert(
            article=article,
            alert_reason="High importance score",
        )
        
        assert alert.alert_reason == "High importance score"
        assert alert.published is False
