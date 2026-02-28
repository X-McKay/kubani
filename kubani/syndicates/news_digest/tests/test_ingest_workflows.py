"""Tests for the Ingest workflows (RSS, arXiv, GitHub).

These tests verify the workflow logic by testing initialization, result
building, and data conversion in isolation. Full workflow execution
tests require a Temporal test environment.
"""

from kubani.syndicates.news_digest.workflows.ingest_arxiv import (
    ArxivIngestInput,
    ArxivIngestResult,
    ArxivIngestWorkflow,
)
from kubani.syndicates.news_digest.workflows.ingest_github import (
    GitHubIngestInput,
    GitHubIngestResult,
    GitHubIngestWorkflow,
)
from kubani.syndicates.news_digest.workflows.ingest_rss import (
    RSSIngestInput,
    RSSIngestResult,
    RSSIngestWorkflow,
)

# =============================================================================
# RSS Ingest Workflow
# =============================================================================


class TestRSSIngestInput:
    """Test RSSIngestInput dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        input = RSSIngestInput()
        assert input.correlation_id is None

    def test_custom_values(self):
        """Should accept custom values."""
        input = RSSIngestInput(correlation_id="test-123")
        assert input.correlation_id == "test-123"


class TestRSSIngestResult:
    """Test RSSIngestResult dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        result = RSSIngestResult()
        assert result.feeds_fetched == 0
        assert result.articles_collected == 0
        assert result.articles_new == 0
        assert result.articles_stored == 0
        assert result.success is True
        assert result.error is None

    def test_custom_values(self):
        """Should accept custom values."""
        result = RSSIngestResult(
            feeds_fetched=5,
            articles_collected=20,
            articles_new=15,
            articles_stored=14,
        )
        assert result.feeds_fetched == 5
        assert result.articles_new == 15


class TestRSSIngestWorkflowInit:
    """Test RSSIngestWorkflow initialization."""

    def test_initializes(self):
        """Workflow should initialize with default state."""
        wf = RSSIngestWorkflow()
        assert wf._result is not None
        assert wf._result.success is True

    def test_build_result(self):
        """_build_result should return a complete dictionary."""
        wf = RSSIngestWorkflow()
        wf._result.feeds_fetched = 3
        wf._result.articles_collected = 10
        wf._result.articles_new = 7
        wf._result.articles_stored = 7

        result = wf._build_result()

        assert isinstance(result, dict)
        assert result["feeds_fetched"] == 3
        assert result["articles_collected"] == 10
        assert result["articles_new"] == 7
        assert result["articles_stored"] == 7
        assert result["success"] is True
        assert result["error"] is None

    def test_build_result_includes_all_fields(self):
        """_build_result should include all expected fields."""
        wf = RSSIngestWorkflow()
        result = wf._build_result()

        expected_keys = {
            "feeds_fetched",
            "articles_collected",
            "articles_new",
            "articles_stored",
            "success",
            "error",
        }
        assert set(result.keys()) == expected_keys


class TestRSSIngestWorkflowConversion:
    """Test RSS document conversion via raw_document_from_rss_entry.

    Conversion was moved from the workflow to the activity to avoid
    Temporal sandbox restrictions on uuid/datetime/hashlib.
    """

    def test_convert_rss_entry(self, sample_articles):
        """Should convert RSS entries to RawDocument dicts."""
        from kubani.syndicates.news_digest.models import raw_document_from_rss_entry

        docs = [raw_document_from_rss_entry(a).to_dict() for a in sample_articles]

        assert len(docs) == 3
        assert docs[0]["source_type"] == "rss"
        assert docs[0]["title"] == "GPT-5 Released with Major Improvements"
        assert docs[0]["source_uri"] == "https://example.com/article1"

    def test_convert_generates_deterministic_ids(self, sample_articles):
        """Same URL should produce the same document_id (uuid5)."""
        from kubani.syndicates.news_digest.models import raw_document_from_rss_entry

        doc1 = raw_document_from_rss_entry(sample_articles[0])
        doc2 = raw_document_from_rss_entry(sample_articles[0])
        assert doc1.document_id == doc2.document_id


class TestRSSIngestWorkflowTriggerAnalysis:
    """Test that RSS ingest has the _trigger_analysis method."""

    def test_has_trigger_analysis_method(self):
        """Workflow should have _trigger_analysis for child workflow trigger."""
        wf = RSSIngestWorkflow()
        assert hasattr(wf, "_trigger_analysis")
        assert callable(wf._trigger_analysis)


class TestRSSIngestWorkflowQueries:
    """Test workflow queries."""

    def test_get_ingest_stats(self):
        """get_ingest_stats should return current statistics."""
        wf = RSSIngestWorkflow()
        wf._result.feeds_fetched = 5
        wf._result.articles_collected = 20
        wf._result.articles_new = 15
        wf._result.articles_stored = 14

        stats = wf.get_ingest_stats()

        assert stats["feeds_fetched"] == 5
        assert stats["articles_collected"] == 20
        assert stats["articles_new"] == 15
        assert stats["articles_stored"] == 14


# =============================================================================
# arXiv Ingest Workflow
# =============================================================================


class TestArxivIngestInput:
    """Test ArxivIngestInput dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        input = ArxivIngestInput()
        assert input.categories is None
        assert input.max_results == 30
        assert input.correlation_id is None

    def test_custom_values(self):
        """Should accept custom values."""
        input = ArxivIngestInput(
            categories=["cs.AI"],
            max_results=10,
            correlation_id="test-123",
        )
        assert input.categories == ["cs.AI"]
        assert input.max_results == 10


class TestArxivIngestResult:
    """Test ArxivIngestResult dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        result = ArxivIngestResult()
        assert result.papers_collected == 0
        assert result.papers_new == 0
        assert result.papers_stored == 0
        assert result.success is True
        assert result.error is None


class TestArxivIngestWorkflowInit:
    """Test ArxivIngestWorkflow initialization."""

    def test_initializes(self):
        """Workflow should initialize with default state."""
        wf = ArxivIngestWorkflow()
        assert wf._result is not None
        assert wf._result.success is True

    def test_build_result(self):
        """_build_result should return a complete dictionary."""
        wf = ArxivIngestWorkflow()
        wf._result.papers_collected = 10
        wf._result.papers_new = 7
        wf._result.papers_stored = 7

        result = wf._build_result()

        assert result["papers_collected"] == 10
        assert result["papers_new"] == 7
        assert result["papers_stored"] == 7
        assert result["success"] is True

    def test_build_result_includes_all_fields(self):
        """_build_result should include all expected fields."""
        wf = ArxivIngestWorkflow()
        result = wf._build_result()

        expected_keys = {
            "papers_collected",
            "papers_new",
            "papers_stored",
            "success",
            "error",
        }
        assert set(result.keys()) == expected_keys


class TestArxivIngestWorkflowConversion:
    """Test arXiv document conversion logic."""

    def test_convert_to_raw_documents(self, sample_papers):
        """Should convert arXiv papers to RawDocument dicts."""
        wf = ArxivIngestWorkflow()
        docs = wf._convert_to_raw_documents(sample_papers)

        assert len(docs) == 2
        assert docs[0]["source_type"] == "arxiv"
        assert docs[0]["source_uri"] == "arxiv:2601.12345"
        assert docs[0]["title"] == "Advances in Transformer Architecture"

    def test_convert_empty_list(self):
        """Should return empty list for empty input."""
        wf = ArxivIngestWorkflow()
        docs = wf._convert_to_raw_documents([])
        assert docs == []


class TestArxivIngestWorkflowTriggerAnalysis:
    """Test that arXiv ingest has the _trigger_analysis method."""

    def test_has_trigger_analysis_method(self):
        """Workflow should have _trigger_analysis for child workflow trigger."""
        wf = ArxivIngestWorkflow()
        assert hasattr(wf, "_trigger_analysis")
        assert callable(wf._trigger_analysis)


class TestArxivIngestWorkflowQueries:
    """Test workflow queries."""

    def test_get_ingest_stats(self):
        """get_ingest_stats should return current statistics."""
        wf = ArxivIngestWorkflow()
        wf._result.papers_collected = 10
        wf._result.papers_new = 7
        wf._result.papers_stored = 6

        stats = wf.get_ingest_stats()

        assert stats["papers_collected"] == 10
        assert stats["papers_new"] == 7
        assert stats["papers_stored"] == 6


# =============================================================================
# GitHub Ingest Workflow
# =============================================================================


class TestGitHubIngestInput:
    """Test GitHubIngestInput dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        input = GitHubIngestInput()
        assert input.max_results == 20
        assert input.correlation_id is None

    def test_custom_values(self):
        """Should accept custom values."""
        input = GitHubIngestInput(max_results=50, correlation_id="test-123")
        assert input.max_results == 50


class TestGitHubIngestResult:
    """Test GitHubIngestResult dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        result = GitHubIngestResult()
        assert result.repos_collected == 0
        assert result.repos_new == 0
        assert result.repos_stored == 0
        assert result.success is True
        assert result.error is None


class TestGitHubIngestWorkflowInit:
    """Test GitHubIngestWorkflow initialization."""

    def test_initializes(self):
        """Workflow should initialize with default state."""
        wf = GitHubIngestWorkflow()
        assert wf._result is not None
        assert wf._result.success is True

    def test_build_result(self):
        """_build_result should return a complete dictionary."""
        wf = GitHubIngestWorkflow()
        wf._result.repos_collected = 20
        wf._result.repos_new = 15
        wf._result.repos_stored = 15

        result = wf._build_result()

        assert result["repos_collected"] == 20
        assert result["repos_new"] == 15
        assert result["repos_stored"] == 15
        assert result["success"] is True

    def test_build_result_includes_all_fields(self):
        """_build_result should include all expected fields."""
        wf = GitHubIngestWorkflow()
        result = wf._build_result()

        expected_keys = {
            "repos_collected",
            "repos_new",
            "repos_stored",
            "success",
            "error",
        }
        assert set(result.keys()) == expected_keys


class TestGitHubIngestWorkflowConversion:
    """Test GitHub document conversion logic."""

    def test_convert_to_raw_documents(self, sample_repos):
        """Should convert GitHub repos to RawDocument dicts."""
        wf = GitHubIngestWorkflow()
        docs = wf._convert_to_raw_documents(sample_repos)

        assert len(docs) == 2
        assert docs[0]["source_type"] == "github"
        assert docs[0]["source_uri"] == "https://github.com/example/ml-toolkit"
        assert docs[0]["title"] == "ml-toolkit"

    def test_convert_preserves_metadata(self, sample_repos):
        """Metadata should include GitHub-specific fields."""
        wf = GitHubIngestWorkflow()
        docs = wf._convert_to_raw_documents(sample_repos)

        assert docs[0]["metadata"]["stars"] == 5000
        assert docs[0]["metadata"]["language"] == "Python"
        assert docs[0]["metadata"]["trending_score"] == 0.85

    def test_convert_empty_list(self):
        """Should return empty list for empty input."""
        wf = GitHubIngestWorkflow()
        docs = wf._convert_to_raw_documents([])
        assert docs == []


class TestGitHubIngestWorkflowTriggerAnalysis:
    """Test that GitHub ingest has the _trigger_analysis method."""

    def test_has_trigger_analysis_method(self):
        """Workflow should have _trigger_analysis for child workflow trigger."""
        wf = GitHubIngestWorkflow()
        assert hasattr(wf, "_trigger_analysis")
        assert callable(wf._trigger_analysis)


class TestGitHubIngestWorkflowQueries:
    """Test workflow queries."""

    def test_get_ingest_stats(self):
        """get_ingest_stats should return current statistics."""
        wf = GitHubIngestWorkflow()
        wf._result.repos_collected = 20
        wf._result.repos_new = 15
        wf._result.repos_stored = 14

        stats = wf.get_ingest_stats()

        assert stats["repos_collected"] == 20
        assert stats["repos_new"] == 15
        assert stats["repos_stored"] == 14
