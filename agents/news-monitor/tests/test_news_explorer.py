"""Tests for the News Explorer agent."""

from news_monitor.federated.explorer import (
    CoverageGap,
    NewsExplorerAgent,
    SourceProposal,
    SourceValidation,
)


class TestCoverageGap:
    """Tests for CoverageGap dataclass."""

    def test_create_gap(self):
        """Test creating a coverage gap."""
        gap = CoverageGap(
            topic="Mistral AI",
            source_count=1,
            article_count=15,
            sources=["TechCrunch"],
            importance_score=15.0,
        )

        assert gap.topic == "Mistral AI"
        assert gap.source_count == 1
        assert gap.article_count == 15
        assert gap.importance_score == 15.0
        assert "TechCrunch" in gap.sources


class TestSourceProposal:
    """Tests for SourceProposal model."""

    def test_create_proposal(self):
        """Test creating a source proposal."""
        proposal = SourceProposal(
            name="Mistral AI Blog",
            url="https://mistral.ai/news/rss/",
            category="company_blogs",
            topic="Mistral AI",
            priority=8,
            reason="Official Mistral AI company blog",
            discovered_via="manual",
        )

        assert proposal.name == "Mistral AI Blog"
        assert proposal.url == "https://mistral.ai/news/rss/"
        assert proposal.category == "company_blogs"
        assert proposal.priority == 8

    def test_priority_bounds(self):
        """Test that priority is bounded."""
        proposal = SourceProposal(
            name="Test",
            url="https://example.com/feed",
            category="general_tech",
            topic="Test",
            priority=5,
            reason="Test",
        )
        assert 1 <= proposal.priority <= 10


class TestSourceValidation:
    """Tests for SourceValidation model."""

    def test_valid_source(self):
        """Test valid source validation."""
        validation = SourceValidation(
            valid=True,
            url="https://example.com/feed.xml",
            title="Example Feed",
            article_count=25,
            update_frequency="daily",
            sample_titles=["Article 1", "Article 2"],
        )

        assert validation.valid is True
        assert validation.article_count == 25
        assert len(validation.sample_titles) == 2

    def test_invalid_source(self):
        """Test invalid source validation."""
        validation = SourceValidation(
            valid=False,
            url="https://example.com/notafeed",
            error="HTTP 404",
        )

        assert validation.valid is False
        assert validation.error == "HTTP 404"


class TestNewsExplorerAgent:
    """Tests for NewsExplorerAgent."""

    def test_init(self):
        """Test News Explorer initialization."""
        explorer = NewsExplorerAgent(
            min_sources_for_gap=3,
            lookback_days=14,
        )

        assert explorer.min_sources_for_gap == 3
        assert explorer.lookback_days == 14
        assert explorer.source_name == "news-explorer"

    def test_is_important_topic_short(self):
        """Test that short topics are rejected."""
        explorer = NewsExplorerAgent()

        assert explorer._is_important_topic("AI") is False
        assert explorer._is_important_topic("a") is False

    def test_is_important_topic_stopwords(self):
        """Test that stopwords are rejected."""
        explorer = NewsExplorerAgent()

        assert explorer._is_important_topic("the") is False
        assert explorer._is_important_topic("and") is False
        assert explorer._is_important_topic("for") is False

    def test_is_important_topic_ai_relevant(self):
        """Test that AI-relevant topics are accepted."""
        explorer = NewsExplorerAgent()

        assert explorer._is_important_topic("machine learning") is True
        assert explorer._is_important_topic("GPT-4") is True
        assert explorer._is_important_topic("Claude AI") is True
        assert explorer._is_important_topic("LLM inference") is True

    def test_template_discover_research(self):
        """Test template discovery for research topics."""
        explorer = NewsExplorerAgent()

        gap = CoverageGap(
            topic="transformer research",
            source_count=1,
            article_count=10,
            importance_score=10.0,
        )

        proposals = explorer._template_discover(gap)

        # Should suggest ArXiv search
        arxiv_proposals = [p for p in proposals if "arxiv" in p.url.lower()]
        assert len(arxiv_proposals) > 0

    def test_template_discover_company(self):
        """Test template discovery for company topics."""
        explorer = NewsExplorerAgent()

        gap = CoverageGap(
            topic="startup funding AI",
            source_count=1,
            article_count=8,
            importance_score=8.0,
        )

        proposals = explorer._template_discover(gap)

        # Should suggest TechCrunch
        tc_proposals = [p for p in proposals if "techcrunch" in p.url.lower()]
        assert len(tc_proposals) > 0

    def test_template_discover_high_importance(self):
        """Test template discovery for high-importance topics."""
        explorer = NewsExplorerAgent()

        gap = CoverageGap(
            topic="artificial intelligence",
            source_count=1,
            article_count=50,
            importance_score=50.0,
        )

        proposals = explorer._template_discover(gap)

        # Should suggest Reddit for high-importance topics
        reddit_proposals = [p for p in proposals if "reddit" in p.url.lower()]
        assert len(reddit_proposals) > 0

    def test_get_category_coverage(self):
        """Test getting category coverage stats."""
        explorer = NewsExplorerAgent()
        coverage = explorer.get_category_coverage()

        # Should have some categories
        assert len(coverage) > 0

        # All values should be positive
        assert all(count > 0 for count in coverage.values())

    def test_find_underrepresented_categories(self):
        """Test finding underrepresented categories."""
        explorer = NewsExplorerAgent()

        # With a high threshold, should find some categories
        underrep = explorer.find_underrepresented_categories(min_sources=20)
        # Most categories should be underrepresented with threshold of 20
        assert len(underrep) > 0


class TestSourceProposalParsing:
    """Tests for parsing LLM source proposals."""

    def test_parse_source_proposals(self):
        """Test parsing LLM response into proposals."""
        explorer = NewsExplorerAgent()

        text = """
        SOURCE_NAME: AI News Daily
        RSS_URL: https://ainews.example.com/feed.xml
        CATEGORY: ai_focused
        PRIORITY: 8
        REASON: Dedicated AI news source with daily updates

        SOURCE_NAME: Tech Analysis Weekly
        RSS_URL: https://techanalysis.example.com/rss
        CATEGORY: business
        PRIORITY: 6
        REASON: In-depth analysis of tech trends
        """

        proposals = explorer._parse_source_proposals(text, "AI News")

        assert len(proposals) == 2
        assert proposals[0].name == "AI News Daily"
        assert proposals[0].url == "https://ainews.example.com/feed.xml"
        assert proposals[0].category == "ai_focused"
        assert proposals[0].priority == 8

    def test_parse_partial_proposals(self):
        """Test parsing incomplete proposals."""
        explorer = NewsExplorerAgent()

        # Missing some fields
        text = """
        SOURCE_NAME: Partial Source
        RSS_URL: https://partial.example.com/feed
        """

        proposals = explorer._parse_source_proposals(text, "Test Topic")

        assert len(proposals) == 1
        assert proposals[0].name == "Partial Source"
        # Should have defaults for missing fields
        assert proposals[0].category == "general_tech"
        assert proposals[0].priority == 5
