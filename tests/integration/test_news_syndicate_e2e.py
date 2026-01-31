"""
End-to-end integration tests for the News Syndicate pipeline.

Tests the full flow from collection -> analysis -> publishing with mocked LLM responses.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from kubani.agents.content_analyst import ContentAnalystAgent
from kubani.agents.content_analyst.agent import AnalysisResult, ProcessedArticle, TrendingTopic
from kubani.agents.digest_publisher import DigestPublisherAgent
from kubani.agents.digest_publisher.agent import NewsDigest, PublishResult
from kubani.agents.feed_collector import FeedCollectorAgent
from kubani.agents.feed_collector.agent import CollectionResult, RawArticle
from kubani.agents.research_analyst import ResearchAnalystAgent
from kubani.agents.research_analyst.agent import PaperAnalysis, RepoAnalysis
from kubani.agents.research_collector import ResearchCollectorAgent
from kubani.agents.research_collector.agent import ArxivPaper, GitHubRepo, ResearchCollectionResult
from kubani.agents.trend_analyst import TrendAnalystAgent
from kubani.agents.trend_analyst.agent import EntityTrend, TrendAnalysis


# --- Mock Response Fixtures ---

MOCK_COLLECTION_RESPONSE = json.dumps({
    "articles": [
        {
            "title": "OpenAI Releases GPT-5",
            "url": "https://example.com/gpt5",
            "source": "TechCrunch",
            "published_date": "2024-01-15T10:00:00Z",
            "summary": "OpenAI has announced GPT-5 with significant improvements.",
            "author": "John Doe",
            "tags": ["AI", "LLM", "OpenAI"],
            "source_category": "ai_focused",
        },
        {
            "title": "Anthropic Claude 4 Announcement",
            "url": "https://example.com/claude4",
            "source": "VentureBeat",
            "published_date": "2024-01-15T11:00:00Z",
            "summary": "Anthropic announces Claude 4 with extended context.",
            "author": "Jane Smith",
            "tags": ["AI", "LLM", "Anthropic"],
            "source_category": "ai_focused",
        },
    ],
    "stats": {
        "total_collected": 2,
        "seen_filtered": 5,
        "sources_fetched": 10,
        "failed_feeds": 1,
    },
})

MOCK_ANALYSIS_RESPONSE = json.dumps([
    {
        "url": "https://example.com/gpt5",
        "title": "OpenAI Releases GPT-5",
        "source": "TechCrunch",
        "source_category": "ai_focused",
        "original_summary": "OpenAI has announced GPT-5.",
        "ai_summary": "Major LLM release with improved reasoning capabilities.",
        "category": "research",
        "entities": ["OpenAI", "GPT-5"],
        "importance_score": 9,
        "is_breaking": True,
        "breaking_reason": "Major product launch",
        "content_hash": "abc123",
    },
])

MOCK_TRENDS_RESPONSE = json.dumps([
    {
        "entity": "GPT-5",
        "article_count": 15,
        "sources": ["TechCrunch", "VentureBeat", "Ars Technica"],
        "status": "HOT",
        "momentum": 150.0,
    },
    {
        "entity": "Claude 4",
        "article_count": 8,
        "sources": ["VentureBeat", "The Verge"],
        "status": "RISING",
        "momentum": 75.0,
    },
])

MOCK_ARXIV_RESPONSE = json.dumps({
    "papers": [
        {
            "arxiv_id": "2401.12345",
            "title": "Efficient Transformer Architectures",
            "authors": ["Alice Researcher", "Bob Scientist"],
            "abstract": "We present a novel approach to efficient transformers...",
            "categories": ["cs.LG", "cs.AI"],
            "pdf_url": "https://arxiv.org/pdf/2401.12345.pdf",
            "published_date": "2024-01-10",
        },
    ],
    "total_fetched": 1,
})

MOCK_GITHUB_RESPONSE = json.dumps({
    "repos": [
        {
            "full_name": "anthropic/claude-sdk",
            "name": "claude-sdk",
            "description": "Official Python SDK for Claude API",
            "url": "https://github.com/anthropic/claude-sdk",
            "stars": 5000,
            "forks": 500,
            "language": "Python",
            "topics": ["llm", "ai", "python"],
            "trending_score": 0.95,
        },
    ],
    "total_found": 1,
})

MOCK_PAPER_ANALYSIS_RESPONSE = json.dumps({
    "research_type": "architecture",
    "main_claim": "New transformer architecture is 2x more efficient",
    "key_innovation": "Novel attention mechanism",
    "practitioner_summary": "This paper presents an efficient transformer.",
    "key_takeaways": ["2x efficiency improvement", "Maintains accuracy"],
    "relevance_score": 8,
    "topics": ["transformers", "efficiency"],
    "digest_worthy": True,
    "spotlight_candidate": True,
})

MOCK_REPO_ANALYSIS_RESPONSE = json.dumps({
    "category": "sdk",
    "target_audience": "developers",
    "use_cases": ["API integration", "Chatbots"],
    "quality_score": 9,
    "spotlight_summary": "Official SDK for Claude API integration.",
    "best_for": "Building AI-powered applications",
    "spotlight_worthy": True,
})

MOCK_TREND_ANALYSIS_RESPONSE = json.dumps({
    "trends": [
        {
            "entity": "GPT-5",
            "current_mentions": 25,
            "historical_mentions": 10,
            "velocity_class": "surging",
            "velocity_percent": 150.0,
            "sources": ["TechCrunch", "VentureBeat"],
        },
        {
            "entity": "BERT",
            "current_mentions": 5,
            "historical_mentions": 20,
            "velocity_class": "declining",
            "velocity_percent": -75.0,
            "sources": ["arXiv"],
        },
    ],
    "emerging_topics": ["Mixture of Experts", "RLHF"],
    "declining_topics": ["BERT", "Word2Vec"],
    "summary": "LLMs continue to dominate with GPT-5 leading discussions.",
})

MOCK_DIGEST_RESPONSE = json.dumps({
    "digest_id": "digest-1705312800",
    "headline_summary": "GPT-5 dominates AI news this week.",
    "trending_topics": [{"name": "GPT-5", "count": 15}],
    "total_articles": 2,
    "sources_used": ["TechCrunch", "VentureBeat"],
})

MOCK_PUBLISH_RESPONSE = json.dumps({
    "success": True,
    "message_id": "1234567890",
    "chunks_sent": 1,
    "channel": "ai-news",
    "error": None,
})


# --- Fixtures ---


@pytest.fixture(autouse=True)
def mock_record_outcome():
    """Mock record_outcome to avoid MCP server connection in tests."""
    with patch(
        "kubani.agents._base.agent.KubaniAgent.record_outcome",
        new_callable=AsyncMock,
    ):
        yield


# --- Test Cases ---


class TestAgentInstantiation:
    """Test that all news syndicate agents can be instantiated."""

    def test_feed_collector_instantiates(self):
        """FeedCollectorAgent can be created."""
        agent = FeedCollectorAgent()
        assert agent is not None
        assert agent.name == "feed-collector"

    def test_content_analyst_instantiates(self):
        """ContentAnalystAgent can be created."""
        agent = ContentAnalystAgent()
        assert agent is not None
        assert agent.name == "content-analyst"

    def test_research_collector_instantiates(self):
        """ResearchCollectorAgent can be created."""
        agent = ResearchCollectorAgent()
        assert agent is not None
        assert agent.name == "research-collector"

    def test_research_analyst_instantiates(self):
        """ResearchAnalystAgent can be created."""
        agent = ResearchAnalystAgent()
        assert agent is not None
        assert agent.name == "research-analyst"

    def test_trend_analyst_instantiates(self):
        """TrendAnalystAgent can be created."""
        agent = TrendAnalystAgent()
        assert agent is not None
        assert agent.name == "trend-analyst"

    def test_digest_publisher_instantiates(self):
        """DigestPublisherAgent can be created."""
        agent = DigestPublisherAgent()
        assert agent is not None
        assert agent.name == "digest-publisher"

    def test_all_agents_can_instantiate(self):
        """All 6 news syndicate agents can be created."""
        agents = [
            FeedCollectorAgent(),
            ContentAnalystAgent(),
            ResearchCollectorAgent(),
            ResearchAnalystAgent(),
            TrendAnalystAgent(),
            DigestPublisherAgent(),
        ]
        assert len(agents) == 6
        for agent in agents:
            assert agent is not None


class TestFeedCollector:
    """Test FeedCollectorAgent.collect() method."""

    @pytest.mark.asyncio
    async def test_feed_collector_returns_collection_result(self):
        """FeedCollectorAgent.collect() returns CollectionResult with articles."""
        agent = FeedCollectorAgent()

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_COLLECTION_RESPONSE

            result = await agent.collect(max_age_hours=24)

            assert isinstance(result, CollectionResult)
            assert len(result.articles) == 2
            assert result.total_collected == 2
            assert result.seen_filtered == 5
            assert result.sources_fetched == 10
            assert result.failed_feeds == 1

            # Verify article structure
            article = result.articles[0]
            assert isinstance(article, RawArticle)
            assert article.title == "OpenAI Releases GPT-5"
            assert article.url == "https://example.com/gpt5"
            assert article.source == "TechCrunch"
            assert "AI" in article.tags

    @pytest.mark.asyncio
    async def test_feed_collector_handles_empty_response(self):
        """FeedCollectorAgent handles empty responses gracefully."""
        agent = FeedCollectorAgent()

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = json.dumps({"articles": [], "stats": {}})

            result = await agent.collect()

            assert isinstance(result, CollectionResult)
            assert len(result.articles) == 0


class TestContentAnalyst:
    """Test ContentAnalystAgent methods."""

    @pytest.mark.asyncio
    async def test_content_analyst_returns_analysis_result(self):
        """ContentAnalystAgent.full_analysis() returns AnalysisResult."""
        agent = ContentAnalystAgent()

        articles = [
            {"title": "Test Article", "url": "https://example.com/test", "summary": "Test summary"},
        ]

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            # Mock responses for analyze_articles, detect_breaking_news, analyze_trends
            mock_run.side_effect = [
                MOCK_ANALYSIS_RESPONSE,
                MOCK_ANALYSIS_RESPONSE,  # Breaking news uses same format
                MOCK_TRENDS_RESPONSE,
            ]

            result = await agent.full_analysis(articles)

            assert isinstance(result, AnalysisResult)
            assert len(result.processed_articles) > 0
            assert isinstance(result.processed_articles[0], ProcessedArticle)
            assert result.stats["total_processed"] > 0

    @pytest.mark.asyncio
    async def test_content_analyst_analyze_articles(self):
        """ContentAnalystAgent.analyze_articles() returns ProcessedArticle list."""
        agent = ContentAnalystAgent()

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_ANALYSIS_RESPONSE

            articles = [{"title": "Test", "url": "https://example.com"}]
            result = await agent.analyze_articles(articles)

            assert len(result) == 1
            article = result[0]
            assert isinstance(article, ProcessedArticle)
            assert article.importance_score == 9
            assert article.is_breaking is True


class TestResearchCollector:
    """Test ResearchCollectorAgent methods."""

    @pytest.mark.asyncio
    async def test_research_collector_returns_collection_result(self):
        """ResearchCollectorAgent.collect_all() returns ResearchCollectionResult."""
        agent = ResearchCollectorAgent()

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [MOCK_ARXIV_RESPONSE, MOCK_GITHUB_RESPONSE]

            result = await agent.collect_all()

            assert isinstance(result, ResearchCollectionResult)
            assert len(result.papers) == 1
            assert len(result.repos) == 1
            assert result.stats["total_papers"] == 1
            assert result.stats["total_repos"] == 1

    @pytest.mark.asyncio
    async def test_research_collector_fetch_arxiv_papers(self):
        """ResearchCollectorAgent.fetch_arxiv_papers() returns ArxivPaper list."""
        agent = ResearchCollectorAgent()

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_ARXIV_RESPONSE

            result = await agent.fetch_arxiv_papers()

            assert len(result) == 1
            paper = result[0]
            assert isinstance(paper, ArxivPaper)
            assert paper.arxiv_id == "2401.12345"
            assert "cs.LG" in paper.categories

    @pytest.mark.asyncio
    async def test_research_collector_fetch_github_trending(self):
        """ResearchCollectorAgent.fetch_github_trending() returns GitHubRepo list."""
        agent = ResearchCollectorAgent()

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_GITHUB_RESPONSE

            result = await agent.fetch_github_trending()

            assert len(result) == 1
            repo = result[0]
            assert isinstance(repo, GitHubRepo)
            assert repo.full_name == "anthropic/claude-sdk"
            assert repo.stars == 5000


class TestResearchAnalyst:
    """Test ResearchAnalystAgent methods."""

    @pytest.mark.asyncio
    async def test_research_analyst_analyze_paper(self):
        """ResearchAnalystAgent.analyze_paper() returns PaperAnalysis."""
        agent = ResearchAnalystAgent()

        paper = {
            "arxiv_id": "2401.12345",
            "title": "Efficient Transformers",
            "authors": ["Alice"],
            "abstract": "A" * 200,  # Long enough abstract
        }

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_PAPER_ANALYSIS_RESPONSE

            result = await agent.analyze_paper(paper)

            assert isinstance(result, PaperAnalysis)
            assert result.arxiv_id == "2401.12345"
            assert result.research_type == "architecture"
            assert result.relevance_score == 8
            assert result.digest_worthy is True

    @pytest.mark.asyncio
    async def test_research_analyst_analyze_papers_batch(self):
        """ResearchAnalystAgent.analyze_papers_batch() returns list of PaperAnalysis."""
        agent = ResearchAnalystAgent()

        papers = [
            {"arxiv_id": "2401.12345", "title": "Paper 1", "authors": ["A"], "abstract": "X" * 200},
            {"arxiv_id": "2401.12346", "title": "Paper 2", "authors": ["B"], "abstract": "Y" * 200},
        ]

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_PAPER_ANALYSIS_RESPONSE

            result = await agent.analyze_papers_batch(papers)

            assert len(result) == 2
            assert all(isinstance(p, PaperAnalysis) for p in result)

    @pytest.mark.asyncio
    async def test_research_analyst_analyze_repo(self):
        """ResearchAnalystAgent.analyze_repo() returns RepoAnalysis."""
        agent = ResearchAnalystAgent()

        repo = {
            "full_name": "anthropic/claude-sdk",
            "name": "claude-sdk",
            "description": "A" * 50,  # Long enough description
            "stars": 5000,
            "language": "Python",
            "topics": ["ai"],
        }

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_REPO_ANALYSIS_RESPONSE

            result = await agent.analyze_repo(repo)

            assert isinstance(result, RepoAnalysis)
            assert result.full_name == "anthropic/claude-sdk"
            assert result.quality_score == 9
            assert result.spotlight_worthy is True

    @pytest.mark.asyncio
    async def test_research_analyst_analyze_repos_batch(self):
        """ResearchAnalystAgent.analyze_repos_batch() returns list of RepoAnalysis."""
        agent = ResearchAnalystAgent()

        repos = [
            {"full_name": "repo1", "name": "r1", "description": "X" * 50, "stars": 1000},
            {"full_name": "repo2", "name": "r2", "description": "Y" * 50, "stars": 2000},
        ]

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_REPO_ANALYSIS_RESPONSE

            result = await agent.analyze_repos_batch(repos)

            assert len(result) == 2
            assert all(isinstance(r, RepoAnalysis) for r in result)


class TestTrendAnalyst:
    """Test TrendAnalystAgent methods."""

    @pytest.mark.asyncio
    async def test_trend_analyst_returns_trend_analysis(self):
        """TrendAnalystAgent.analyze_trends() returns TrendAnalysis."""
        agent = TrendAnalystAgent()

        current = {"GPT-5": 25, "BERT": 5}
        historical = {"GPT-5": 10, "BERT": 20}

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_TREND_ANALYSIS_RESPONSE

            result = await agent.analyze_trends(current, historical)

            assert isinstance(result, TrendAnalysis)
            assert len(result.trends) == 2
            assert isinstance(result.trends[0], EntityTrend)
            assert result.emerging_topics == ["Mixture of Experts", "RLHF"]
            assert result.declining_topics == ["BERT", "Word2Vec"]
            assert "LLMs" in result.summary

    @pytest.mark.asyncio
    async def test_trend_analyst_entity_trend_structure(self):
        """TrendAnalystAgent returns properly structured EntityTrend objects."""
        agent = TrendAnalystAgent()

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_TREND_ANALYSIS_RESPONSE

            result = await agent.analyze_trends({"GPT-5": 25}, {"GPT-5": 10})

            trend = result.trends[0]
            assert trend.entity == "GPT-5"
            assert trend.current_mentions == 25
            assert trend.historical_mentions == 10
            assert trend.velocity_class == "surging"
            assert trend.velocity_percent == 150.0


class TestDigestPublisher:
    """Test DigestPublisherAgent methods."""

    @pytest.mark.asyncio
    async def test_digest_publisher_returns_publish_result(self):
        """DigestPublisherAgent.compose_and_publish() returns PublishResult."""
        agent = DigestPublisherAgent()

        articles = [{"title": "Test", "url": "https://example.com", "summary": "Test"}]
        trends = [{"entity": "AI", "count": 10}]

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [MOCK_DIGEST_RESPONSE, MOCK_PUBLISH_RESPONSE]

            result = await agent.compose_and_publish(articles, trends)

            assert isinstance(result, PublishResult)
            assert result.success is True
            assert result.message_id == "1234567890"
            assert result.channel == "ai-news"

    @pytest.mark.asyncio
    async def test_digest_publisher_compose_digest(self):
        """DigestPublisherAgent.compose_digest() returns NewsDigest."""
        agent = DigestPublisherAgent()

        articles = [{"title": "Test", "summary": "Summary"}]
        trends = []

        with patch.object(agent, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_DIGEST_RESPONSE

            result = await agent.compose_digest(articles, trends)

            assert isinstance(result, NewsDigest)
            assert result.headline_summary == "GPT-5 dominates AI news this week."
            assert result.total_articles == 2

    @pytest.mark.asyncio
    async def test_digest_publisher_handles_empty_articles(self):
        """DigestPublisherAgent returns error for empty articles."""
        agent = DigestPublisherAgent()

        result = await agent.compose_and_publish([], [])

        assert isinstance(result, PublishResult)
        assert result.success is False
        assert "No articles" in result.error


class TestFullPipelineE2E:
    """End-to-end test of the complete news syndicate pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_e2e(self):
        """Test the full collection -> analysis -> publishing pipeline with mocks."""
        # Step 1: Feed Collection
        feed_collector = FeedCollectorAgent()
        with patch.object(feed_collector, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_COLLECTION_RESPONSE
            collection_result = await feed_collector.collect()

        assert isinstance(collection_result, CollectionResult)
        assert len(collection_result.articles) == 2

        # Convert to dicts for next stage
        articles_dicts = [
            {
                "title": a.title,
                "url": a.url,
                "source": a.source,
                "summary": a.summary,
                "source_category": a.source_category,
            }
            for a in collection_result.articles
        ]

        # Step 2: Content Analysis
        content_analyst = ContentAnalystAgent()
        with patch.object(content_analyst, "run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [
                MOCK_ANALYSIS_RESPONSE,
                MOCK_ANALYSIS_RESPONSE,
                MOCK_TRENDS_RESPONSE,
            ]
            analysis_result = await content_analyst.full_analysis(articles_dicts)

        assert isinstance(analysis_result, AnalysisResult)
        assert len(analysis_result.processed_articles) > 0

        # Step 3: Research Collection
        research_collector = ResearchCollectorAgent()
        with patch.object(research_collector, "run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [MOCK_ARXIV_RESPONSE, MOCK_GITHUB_RESPONSE]
            research_result = await research_collector.collect_all()

        assert isinstance(research_result, ResearchCollectionResult)
        assert len(research_result.papers) == 1
        assert len(research_result.repos) == 1

        # Step 4: Research Analysis
        research_analyst = ResearchAnalystAgent()
        papers_dicts = [
            {
                "arxiv_id": p.arxiv_id,
                "title": p.title,
                "authors": p.authors,
                "abstract": p.abstract or "A" * 200,
            }
            for p in research_result.papers
        ]
        repos_dicts = [
            {
                "full_name": r.full_name,
                "name": r.name,
                "description": r.description or "X" * 50,
                "stars": r.stars,
            }
            for r in research_result.repos
        ]

        with patch.object(research_analyst, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_PAPER_ANALYSIS_RESPONSE
            paper_analyses = await research_analyst.analyze_papers_batch(papers_dicts)

        with patch.object(research_analyst, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_REPO_ANALYSIS_RESPONSE
            repo_analyses = await research_analyst.analyze_repos_batch(repos_dicts)

        assert len(paper_analyses) == 1
        assert len(repo_analyses) == 1

        # Step 5: Trend Analysis
        trend_analyst = TrendAnalystAgent()
        current_entities = {"GPT-5": 25, "Claude": 15}
        historical_entities = {"GPT-5": 10, "Claude": 10}

        with patch.object(trend_analyst, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = MOCK_TREND_ANALYSIS_RESPONSE
            trend_analysis = await trend_analyst.analyze_trends(
                current_entities, historical_entities
            )

        assert isinstance(trend_analysis, TrendAnalysis)
        assert len(trend_analysis.trends) > 0

        # Step 6: Digest Publishing
        digest_publisher = DigestPublisherAgent()
        processed_dicts = [
            {"title": a.title, "url": a.url, "ai_summary": a.ai_summary, "source": a.source}
            for a in analysis_result.processed_articles
        ]
        trends_dicts = [t.to_dict() for t in trend_analysis.trends]

        with patch.object(digest_publisher, "run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [MOCK_DIGEST_RESPONSE, MOCK_PUBLISH_RESPONSE]
            publish_result = await digest_publisher.compose_and_publish(
                processed_dicts, trends_dicts
            )

        assert isinstance(publish_result, PublishResult)
        assert publish_result.success is True
        assert publish_result.message_id is not None

    @pytest.mark.asyncio
    async def test_pipeline_handles_empty_intermediate_results(self):
        """Pipeline handles empty results at intermediate stages gracefully."""
        # Collection returns no articles
        feed_collector = FeedCollectorAgent()
        with patch.object(feed_collector, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = json.dumps({"articles": [], "stats": {}})
            collection_result = await feed_collector.collect()

        assert isinstance(collection_result, CollectionResult)
        assert len(collection_result.articles) == 0

        # Analysis handles empty input
        content_analyst = ContentAnalystAgent()
        analysis_result = await content_analyst.full_analysis([])

        assert isinstance(analysis_result, AnalysisResult)
        assert len(analysis_result.processed_articles) == 0

        # Publishing handles empty input
        digest_publisher = DigestPublisherAgent()
        publish_result = await digest_publisher.compose_and_publish([], [])

        assert isinstance(publish_result, PublishResult)
        assert publish_result.success is False
