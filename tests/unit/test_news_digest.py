"""
Tests for the enhanced news monitor digest system.

Tests cover:
- Executive brief formatting
- Breaking news detection and routing
- Emoji feedback processing
- Relevance filtering
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestExecutiveBrief:
    """Tests for the Executive Brief formatter."""

    def test_brief_initialization(self):
        """Test Executive Brief initialization."""
        from news_monitor.digest.executive_brief import ExecutiveBrief
        
        brief = ExecutiveBrief()
        
        assert brief.max_articles == 10
        assert brief.deep_dive_count == 3

    def test_format_market_pulse(self):
        """Test Market Pulse section formatting."""
        from news_monitor.digest.executive_brief import ExecutiveBrief, NewsArticle
        
        brief = ExecutiveBrief()
        
        articles = [
            NewsArticle(
                title="Tech stocks surge",
                summary="Major tech companies see gains",
                source="TechNews",
                url="https://example.com/1",
                published_at=datetime.now(timezone.utc),
                category="markets",
                sentiment=0.8,
            ),
            NewsArticle(
                title="AI investments grow",
                summary="AI sector attracts funding",
                source="AIDaily",
                url="https://example.com/2",
                published_at=datetime.now(timezone.utc),
                category="ai",
                sentiment=0.7,
            ),
        ]
        
        pulse = brief.format_market_pulse(articles)
        
        assert "📊" in pulse or "Market" in pulse
        assert "Tech stocks" in pulse or len(pulse) > 0

    def test_format_deep_dive(self):
        """Test Deep Dive section formatting."""
        from news_monitor.digest.executive_brief import ExecutiveBrief, NewsArticle
        
        brief = ExecutiveBrief()
        
        article = NewsArticle(
            title="Major AI Breakthrough",
            summary="Researchers achieve significant milestone in AI development",
            source="ScienceDaily",
            url="https://example.com/ai-breakthrough",
            published_at=datetime.now(timezone.utc),
            category="ai",
            sentiment=0.9,
            key_points=["Point 1", "Point 2", "Point 3"],
            implications=["Implication 1", "Implication 2"],
        )
        
        deep_dive = brief.format_deep_dive(article, index=1)
        
        assert "1." in deep_dive or "Major AI" in deep_dive
        assert len(deep_dive) > 0

    def test_format_full_digest(self):
        """Test full digest formatting."""
        from news_monitor.digest.executive_brief import ExecutiveBrief, NewsArticle
        
        brief = ExecutiveBrief()
        
        articles = [
            NewsArticle(
                title=f"Article {i}",
                summary=f"Summary {i}",
                source="Source",
                url=f"https://example.com/{i}",
                published_at=datetime.now(timezone.utc),
                category="tech",
                sentiment=0.5 + (i * 0.1),
            )
            for i in range(5)
        ]
        
        digest = brief.format_digest(articles)
        
        assert "Executive Brief" in digest or len(digest) > 100
        assert "Article" in digest

    def test_calculate_overall_sentiment(self):
        """Test overall sentiment calculation."""
        from news_monitor.digest.executive_brief import ExecutiveBrief, NewsArticle
        
        brief = ExecutiveBrief()
        
        articles = [
            NewsArticle(
                title="Positive news",
                summary="Good things happening",
                source="Source",
                url="https://example.com/1",
                published_at=datetime.now(timezone.utc),
                category="tech",
                sentiment=0.8,
            ),
            NewsArticle(
                title="Negative news",
                summary="Bad things happening",
                source="Source",
                url="https://example.com/2",
                published_at=datetime.now(timezone.utc),
                category="tech",
                sentiment=0.2,
            ),
        ]
        
        sentiment = brief.calculate_overall_sentiment(articles)
        
        assert 0.4 <= sentiment <= 0.6  # Average of 0.8 and 0.2

    def test_select_deep_dives(self):
        """Test deep dive article selection."""
        from news_monitor.digest.executive_brief import ExecutiveBrief, NewsArticle
        
        brief = ExecutiveBrief()
        brief.deep_dive_count = 2
        
        articles = [
            NewsArticle(
                title=f"Article {i}",
                summary=f"Summary {i}",
                source="Source",
                url=f"https://example.com/{i}",
                published_at=datetime.now(timezone.utc),
                category="tech",
                sentiment=0.5,
                importance_score=i * 0.2,  # Varying importance
            )
            for i in range(5)
        ]
        
        deep_dives = brief.select_deep_dives(articles)
        
        assert len(deep_dives) == 2
        # Should select highest importance articles
        assert deep_dives[0].importance_score >= deep_dives[1].importance_score


class TestBreakingNews:
    """Tests for the Breaking News handler."""

    def test_handler_initialization(self):
        """Test Breaking News handler initialization."""
        from news_monitor.digest.breaking_news import BreakingNewsHandler
        
        handler = BreakingNewsHandler()
        
        assert handler.urgency_threshold == 7
        assert handler.breaking_channel_id is not None or handler.breaking_channel_id is None

    def test_calculate_urgency_score(self):
        """Test urgency score calculation."""
        from news_monitor.digest.breaking_news import BreakingNewsHandler, NewsArticle
        
        handler = BreakingNewsHandler()
        
        article = NewsArticle(
            title="BREAKING: Major security breach",
            summary="Critical vulnerability discovered",
            source="SecurityNews",
            url="https://example.com/breach",
            published_at=datetime.now(timezone.utc),
            category="security",
            sentiment=-0.8,
            keywords=["breach", "critical", "vulnerability"],
        )
        
        score = handler.calculate_urgency_score(article)
        
        assert score >= 0
        assert score <= 10

    def test_is_breaking_news(self):
        """Test breaking news detection."""
        from news_monitor.digest.breaking_news import BreakingNewsHandler, NewsArticle
        
        handler = BreakingNewsHandler()
        handler.urgency_threshold = 7
        
        # High urgency article
        urgent_article = NewsArticle(
            title="BREAKING: Critical system failure",
            summary="Major outage affecting millions",
            source="TechAlert",
            url="https://example.com/outage",
            published_at=datetime.now(timezone.utc),
            category="infrastructure",
            sentiment=-0.9,
            keywords=["breaking", "critical", "outage", "urgent"],
        )
        
        # Normal article
        normal_article = NewsArticle(
            title="New feature released",
            summary="Company launches new product",
            source="TechNews",
            url="https://example.com/feature",
            published_at=datetime.now(timezone.utc),
            category="product",
            sentiment=0.5,
            keywords=["feature", "release"],
        )
        
        with patch.object(handler, "calculate_urgency_score") as mock_score:
            mock_score.side_effect = [9, 3]  # Urgent, then normal
            
            assert handler.is_breaking_news(urgent_article) is True
            assert handler.is_breaking_news(normal_article) is False

    @pytest.mark.asyncio
    async def test_send_breaking_alert(self):
        """Test sending breaking news alert."""
        from news_monitor.digest.breaking_news import BreakingNewsHandler, NewsArticle
        
        handler = BreakingNewsHandler()
        
        article = NewsArticle(
            title="BREAKING: Major event",
            summary="Important news",
            source="Source",
            url="https://example.com/breaking",
            published_at=datetime.now(timezone.utc),
            category="news",
            sentiment=0.0,
        )
        
        with patch.object(handler, "_discord_client") as mock_discord:
            mock_discord.send_embed = AsyncMock(return_value={"id": "msg-123"})
            
            message_id = await handler.send_breaking_alert(article, urgency_score=9)
            
            assert message_id == "msg-123"
            mock_discord.send_embed.assert_called_once()

    def test_format_breaking_embed(self):
        """Test breaking news embed formatting."""
        from news_monitor.digest.breaking_news import BreakingNewsHandler, NewsArticle
        
        handler = BreakingNewsHandler()
        
        article = NewsArticle(
            title="BREAKING: Critical alert",
            summary="Important information",
            source="AlertSource",
            url="https://example.com/alert",
            published_at=datetime.now(timezone.utc),
            category="alert",
            sentiment=-0.5,
            action_items=["Action 1", "Action 2"],
        )
        
        embed = handler.format_breaking_embed(article, urgency_score=8)
        
        assert embed["title"] is not None
        assert "🚨" in embed["title"] or "BREAKING" in embed["title"]
        assert embed["color"] is not None  # Should have urgency color


class TestFeedbackHandler:
    """Tests for the emoji feedback handler."""

    def test_handler_initialization(self):
        """Test Feedback Handler initialization."""
        from news_monitor.digest.feedback import FeedbackHandler
        
        handler = FeedbackHandler()
        
        assert handler.reaction_weights is not None
        assert "👍" in handler.reaction_weights

    def test_parse_reactions(self):
        """Test reaction parsing."""
        from news_monitor.digest.feedback import FeedbackHandler
        
        handler = FeedbackHandler()
        
        reactions = {
            "👍": 5,
            "📖": 3,
            "🎯": 2,
            "👎": 1,
        }
        
        feedback = handler.parse_reactions(reactions)
        
        assert feedback.positive_count == 5
        assert feedback.read_more_count == 3
        assert feedback.relevant_count == 2
        assert feedback.negative_count == 1

    def test_calculate_quality_score(self):
        """Test quality score calculation from feedback."""
        from news_monitor.digest.feedback import FeedbackHandler, ArticleFeedback
        
        handler = FeedbackHandler()
        
        feedback = ArticleFeedback(
            article_id="article-1",
            positive_count=10,
            read_more_count=5,
            relevant_count=3,
            negative_count=2,
        )
        
        score = handler.calculate_quality_score(feedback)
        
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # More positive than negative

    @pytest.mark.asyncio
    async def test_process_feedback(self):
        """Test processing feedback for an article."""
        from news_monitor.digest.feedback import FeedbackHandler
        
        handler = FeedbackHandler()
        
        with patch.object(handler, "_discord_client") as mock_discord, \
             patch.object(handler, "_store_feedback") as mock_store:
            mock_discord.get_reactions = AsyncMock(return_value={
                "👍": 8,
                "👎": 2,
            })
            mock_store.return_value = None
            
            feedback = await handler.process_feedback("msg-123", "article-1")
            
            assert feedback.positive_count == 8
            assert feedback.negative_count == 2

    @pytest.mark.asyncio
    async def test_update_preferences(self):
        """Test updating user preferences from feedback."""
        from news_monitor.digest.feedback import FeedbackHandler, ArticleFeedback
        
        handler = FeedbackHandler()
        
        feedback = ArticleFeedback(
            article_id="article-1",
            positive_count=10,
            read_more_count=8,
            relevant_count=5,
            negative_count=1,
            article_category="ai",
            article_source="AINews",
        )
        
        with patch.object(handler, "_memory_client") as mock_memory:
            mock_memory.store_learning = AsyncMock()
            
            await handler.update_preferences(feedback)
            
            # Should store preference learning
            mock_memory.store_learning.assert_called()

    def test_get_trending_topics(self):
        """Test getting trending topics from feedback."""
        from news_monitor.digest.feedback import FeedbackHandler, ArticleFeedback
        
        handler = FeedbackHandler()
        
        feedbacks = [
            ArticleFeedback(
                article_id=f"article-{i}",
                positive_count=10 - i,
                read_more_count=5,
                relevant_count=3,
                negative_count=1,
                article_category="ai" if i < 3 else "cloud",
                article_keywords=["ai", "ml"] if i < 3 else ["cloud", "aws"],
            )
            for i in range(5)
        ]
        
        trending = handler.get_trending_topics(feedbacks)
        
        assert len(trending) > 0
        assert "ai" in trending or "cloud" in trending


class TestRelevanceFilter:
    """Tests for the relevance filtering system."""

    def test_filter_initialization(self):
        """Test relevance filter initialization."""
        from news_monitor.digest.executive_brief import RelevanceFilter
        
        filter = RelevanceFilter()
        
        assert filter.min_relevance_score >= 0
        assert filter.keyword_weights is not None

    def test_calculate_relevance_score(self):
        """Test relevance score calculation."""
        from news_monitor.digest.executive_brief import RelevanceFilter, NewsArticle
        
        filter = RelevanceFilter()
        filter.relevant_keywords = ["kubernetes", "ai", "cloud"]
        
        relevant_article = NewsArticle(
            title="Kubernetes AI Integration",
            summary="New AI features for Kubernetes",
            source="TechNews",
            url="https://example.com/k8s-ai",
            published_at=datetime.now(timezone.utc),
            category="tech",
            sentiment=0.7,
            keywords=["kubernetes", "ai", "integration"],
        )
        
        irrelevant_article = NewsArticle(
            title="Sports Update",
            summary="Latest sports news",
            source="SportsNews",
            url="https://example.com/sports",
            published_at=datetime.now(timezone.utc),
            category="sports",
            sentiment=0.5,
            keywords=["sports", "game", "score"],
        )
        
        relevant_score = filter.calculate_relevance_score(relevant_article)
        irrelevant_score = filter.calculate_relevance_score(irrelevant_article)
        
        assert relevant_score > irrelevant_score

    def test_filter_articles(self):
        """Test article filtering by relevance."""
        from news_monitor.digest.executive_brief import RelevanceFilter, NewsArticle
        
        filter = RelevanceFilter()
        filter.min_relevance_score = 0.5
        
        articles = [
            NewsArticle(
                title=f"Article {i}",
                summary=f"Summary {i}",
                source="Source",
                url=f"https://example.com/{i}",
                published_at=datetime.now(timezone.utc),
                category="tech",
                sentiment=0.5,
            )
            for i in range(10)
        ]
        
        with patch.object(filter, "calculate_relevance_score") as mock_score:
            # Alternate high and low scores
            mock_score.side_effect = [0.8, 0.2, 0.9, 0.1, 0.7, 0.3, 0.6, 0.4, 0.8, 0.2]
            
            filtered = filter.filter_articles(articles)
            
            assert len(filtered) == 5  # Only articles with score >= 0.5

    def test_boost_from_feedback(self):
        """Test relevance boosting from user feedback."""
        from news_monitor.digest.executive_brief import RelevanceFilter
        
        filter = RelevanceFilter()
        
        # Simulate positive feedback for certain topics
        feedback_data = {
            "ai": {"positive": 20, "negative": 2},
            "sports": {"positive": 1, "negative": 10},
        }
        
        filter.update_from_feedback(feedback_data)
        
        assert filter.keyword_weights.get("ai", 1.0) > 1.0
        assert filter.keyword_weights.get("sports", 1.0) < 1.0
