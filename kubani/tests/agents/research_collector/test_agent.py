"""Tests for ResearchCollectorAgent."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from kubani.agents.research_collector import ResearchCollectorAgent
from kubani.agents.research_collector.agent import (
    ArxivCollectionResult,
    ArxivPaper,
    GitHubCollectionResult,
    GitHubRepo,
)


class TestResearchCollectorAgent:
    """Test ResearchCollectorAgent initialization and config."""

    def test_instantiation(self):
        """Test agent can be created."""
        agent = ResearchCollectorAgent()
        assert agent is not None
        assert agent.name == "research-collector"

    def test_default_arxiv_categories(self):
        """Test agent has default arXiv categories."""
        agent = ResearchCollectorAgent()
        # Check class-level defaults
        assert "cs.AI" in agent.DEFAULT_ARXIV_CATEGORIES
        assert "cs.LG" in agent.DEFAULT_ARXIV_CATEGORIES
        assert "cs.CL" in agent.DEFAULT_ARXIV_CATEGORIES

    def test_default_github_topics(self):
        """Test agent has default GitHub topics."""
        agent = ResearchCollectorAgent()
        # Check class-level defaults
        assert "machine-learning" in agent.DEFAULT_GITHUB_TOPICS
        assert "llm" in agent.DEFAULT_GITHUB_TOPICS


class TestArxivPaper:
    """Test ArxivPaper model."""

    def test_to_dict(self):
        """Test ArxivPaper can be serialized."""
        paper = ArxivPaper(
            arxiv_id="2601.12345",
            title="Test Paper",
            authors=["Author One"],
            abstract="Test abstract",
            categories=["cs.AI"],
            pdf_url="https://arxiv.org/pdf/2601.12345.pdf",
            published_at=datetime(2026, 1, 27, tzinfo=UTC),
        )
        result = paper.to_dict()

        assert result["arxiv_id"] == "2601.12345"
        assert result["title"] == "Test Paper"
        assert result["authors"] == ["Author One"]
        assert result["abstract"] == "Test abstract"
        assert result["categories"] == ["cs.AI"]
        assert "published_at" in result


class TestGitHubRepo:
    """Test GitHubRepo model."""

    def test_to_dict(self):
        """Test GitHubRepo can be serialized."""
        repo = GitHubRepo(
            name="test-repo",
            full_name="owner/test-repo",
            description="A test repository",
            url="https://github.com/owner/test-repo",
            stars=1000,
            forks=100,
            language="Python",
            topics=["machine-learning", "ai"],
            created_at=datetime(2024, 1, 15, tzinfo=UTC),
            pushed_at=datetime(2026, 1, 25, tzinfo=UTC),
        )
        result = repo.to_dict()

        assert result["name"] == "test-repo"
        assert result["full_name"] == "owner/test-repo"
        assert result["stars"] == 1000
        assert result["forks"] == 100
        assert result["language"] == "Python"
        assert "machine-learning" in result["topics"]


class TestArxivCollectionResult:
    """Test ArxivCollectionResult model."""

    def test_to_dict_equivalent(self):
        """Test result contains expected fields."""
        result = ArxivCollectionResult(
            papers=[],
            total_fetched=0,
            categories_queried=["cs.AI"],
        )

        assert result.total_fetched == 0
        assert result.categories_queried == ["cs.AI"]
        assert result.papers == []


class TestGitHubCollectionResult:
    """Test GitHubCollectionResult model."""

    def test_fields(self):
        """Test result contains expected fields."""
        result = GitHubCollectionResult(
            repos=[],
            total_fetched=5,
            topics_queried=["llm"],
        )

        assert result.total_fetched == 5
        assert result.topics_queried == ["llm"]
        assert result.repos == []


class TestArxivIdExtraction:
    """Test arXiv ID extraction."""

    def test_extract_arxiv_id(self):
        """Test extracting arXiv ID from URL."""
        agent = ResearchCollectorAgent()

        # Standard URL
        assert agent._extract_arxiv_id("https://arxiv.org/abs/2601.12345") == "2601.12345"

        # With version
        assert agent._extract_arxiv_id("http://arxiv.org/abs/2601.12345v1") == "2601.12345"

        # Non-URL returns as-is
        assert agent._extract_arxiv_id("some-other-link") == "some-other-link"


class TestGitHubParsing:
    """Test GitHub API response parsing."""

    def test_parse_github_repo(self):
        """Test parsing a GitHub API repo response."""
        agent = ResearchCollectorAgent()

        repo_data = {
            "name": "test-repo",
            "full_name": "owner/test-repo",
            "description": "A machine learning library",
            "html_url": "https://github.com/owner/test-repo",
            "stargazers_count": 5000,
            "language": "Python",
            "topics": ["machine-learning", "deep-learning"],
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2026-01-25T15:30:00Z",
            "pushed_at": "2026-01-24T12:00:00Z",
            "forks_count": 500,
            "open_issues_count": 25,
            "watchers_count": 4500,
            "owner": {"login": "owner"},
            "license": {"name": "MIT License"},
        }

        repo = agent._parse_github_repo(repo_data)

        assert repo is not None
        assert repo.name == "test-repo"
        assert repo.full_name == "owner/test-repo"
        assert repo.stars == 5000
        assert repo.forks == 500
        assert repo.language == "Python"
        assert "machine-learning" in repo.topics
        assert repo.watchers == 4500

    def test_parse_github_repo_minimal(self):
        """Test parsing a minimal GitHub repo response."""
        agent = ResearchCollectorAgent()

        repo_data = {
            "name": "simple-repo",
            "full_name": "owner/simple-repo",
            "description": None,
            "html_url": "https://github.com/owner/simple-repo",
            "stargazers_count": 100,
            "forks_count": 10,
        }

        repo = agent._parse_github_repo(repo_data)

        assert repo is not None
        assert repo.name == "simple-repo"
        assert repo.description == ""
        assert repo.stars == 100
        assert repo.forks == 10


class TestTrendingScoreCalculation:
    """Test trending score calculation."""

    def test_calculate_trending_score(self):
        """Test calculating trending score for a repo."""
        agent = ResearchCollectorAgent()

        repo_data = {
            "stargazers_count": 1000,
            "forks_count": 100,
            "pushed_at": None,
        }

        score = agent._calculate_trending_score(repo_data)

        # score = stars + (forks * 2) = 1000 + 200 = 1200
        assert score == 1200

    def test_calculate_trending_score_with_recent_push(self):
        """Test that recent activity increases score."""
        agent = ResearchCollectorAgent()

        # Just pushed today
        today = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        repo_data = {
            "stargazers_count": 1000,
            "forks_count": 100,
            "pushed_at": today,
        }

        score = agent._calculate_trending_score(repo_data)

        # Should be > 1200 due to recent push bonus
        assert score > 1200


class TestFetchArxivPapers:
    """Test arXiv paper fetching."""

    @pytest.mark.asyncio
    async def test_fetch_arxiv_papers_with_mock(self):
        """Test fetching papers with mocked HTTP client."""
        agent = ResearchCollectorAgent()

        # Create a mock RSS response
        mock_rss = """<?xml version="1.0" encoding="UTF-8"?>
        <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
            <item>
                <title>Advances in LLM Efficiency</title>
                <link>https://arxiv.org/abs/2601.99999</link>
                <description>We present new techniques for efficient LLM inference.</description>
            </item>
        </rdf:RDF>
        """

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_rss
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response

        with patch.object(agent, "_get_http_client", return_value=mock_client):
            result = await agent.fetch_arxiv_papers(
                categories=["cs.AI"],
                max_results=10,
                days_back=7,
            )

        assert result.categories_queried == ["cs.AI"]
        assert isinstance(result.total_fetched, int)


class TestFetchGitHubTrending:
    """Test GitHub trending repo fetching."""

    @pytest.mark.asyncio
    async def test_fetch_github_trending_with_mock(self):
        """Test fetching repos with mocked HTTP client."""
        agent = ResearchCollectorAgent()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "name": "awesome-llm",
                    "full_name": "org/awesome-llm",
                    "description": "Collection of LLM resources",
                    "html_url": "https://github.com/org/awesome-llm",
                    "stargazers_count": 10000,
                    "forks_count": 1000,
                    "language": "Python",
                    "topics": ["llm", "machine-learning"],
                    "created_at": "2024-06-01T00:00:00Z",
                    "pushed_at": "2026-01-26T12:00:00Z",
                    "open_issues_count": 50,
                    "watchers_count": 9500,
                    "owner": {"login": "org"},
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response

        with patch.object(agent, "_get_http_client", return_value=mock_client):
            result = await agent.fetch_github_trending(
                topics=["llm"],
                min_stars=100,
                max_results=5,
            )

        assert "llm" in result.topics_queried
        assert result.total_fetched == 1
        assert result.repos[0].name == "awesome-llm"
        assert result.repos[0].stars == 10000
