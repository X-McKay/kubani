"""Tests for the Ingest workflow dataclasses and initialization.

These tests verify the workflow input dataclasses and that the workflow
classes can be instantiated correctly. The actual pipeline logic is
tested in ``test_ingest_pipeline.py`` via the ``LocalContext``.

Full Temporal workflow execution tests require a Temporal test
environment and are not included here.
"""

from kubani.syndicates.news_digest.workflows.ingest_arxiv import (
    ArxivIngestInput,
    ArxivIngestWorkflow,
)
from kubani.syndicates.news_digest.workflows.ingest_github import (
    GitHubIngestInput,
    GitHubIngestWorkflow,
)
from kubani.syndicates.news_digest.workflows.ingest_rss import (
    RSSIngestInput,
    RSSIngestWorkflow,
)
from kubani.syndicates.news_digest.pipeline import IngestResult


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


class TestRSSIngestWorkflowInit:
    """Test RSSIngestWorkflow initialization."""

    def test_initializes(self):
        """Workflow should initialize with default state."""
        wf = RSSIngestWorkflow()
        assert wf._stats == {}

    def test_has_get_ingest_stats_query(self):
        """Workflow should have the get_ingest_stats query handler."""
        wf = RSSIngestWorkflow()
        assert hasattr(wf, "get_ingest_stats")
        assert callable(wf.get_ingest_stats)

    def test_get_ingest_stats_returns_empty_initially(self):
        """get_ingest_stats should return empty dict before any run."""
        wf = RSSIngestWorkflow()
        assert wf.get_ingest_stats() == {}


# =============================================================================
# RSS Document Conversion (via models)
# =============================================================================


class TestRSSDocumentConversion:
    """Test RSS document conversion via raw_document_from_rss_entry.

    Conversion is now handled by the TemporalContext and the models
    module. These tests verify the conversion functions still work.
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


class TestArxivIngestWorkflowInit:
    """Test ArxivIngestWorkflow initialization."""

    def test_initializes(self):
        """Workflow should initialize with default state."""
        wf = ArxivIngestWorkflow()
        assert wf._stats == {}

    def test_has_get_ingest_stats_query(self):
        """Workflow should have the get_ingest_stats query handler."""
        wf = ArxivIngestWorkflow()
        assert hasattr(wf, "get_ingest_stats")
        assert callable(wf.get_ingest_stats)


class TestArxivDocumentConversion:
    """Test arXiv document conversion logic."""

    def test_convert_arxiv_paper(self, sample_papers):
        """Should convert arXiv papers to RawDocument dicts."""
        from kubani.syndicates.news_digest.models import raw_document_from_arxiv_paper

        docs = [raw_document_from_arxiv_paper(p).to_dict() for p in sample_papers]

        assert len(docs) == 2
        assert docs[0]["source_type"] == "arxiv"
        assert docs[0]["source_uri"] == "arxiv:2601.12345"
        assert docs[0]["title"] == "Advances in Transformer Architecture"

    def test_convert_empty_list(self):
        """Should return empty list for empty input."""
        from kubani.syndicates.news_digest.models import raw_document_from_arxiv_paper

        docs = [raw_document_from_arxiv_paper(p).to_dict() for p in []]
        assert docs == []


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


class TestGitHubIngestWorkflowInit:
    """Test GitHubIngestWorkflow initialization."""

    def test_initializes(self):
        """Workflow should initialize with default state."""
        wf = GitHubIngestWorkflow()
        assert wf._stats == {}

    def test_has_get_ingest_stats_query(self):
        """Workflow should have the get_ingest_stats query handler."""
        wf = GitHubIngestWorkflow()
        assert hasattr(wf, "get_ingest_stats")
        assert callable(wf.get_ingest_stats)


class TestGitHubDocumentConversion:
    """Test GitHub document conversion logic."""

    def test_convert_github_repo(self, sample_repos):
        """Should convert GitHub repos to RawDocument dicts."""
        from kubani.syndicates.news_digest.models import raw_document_from_github_repo

        docs = [raw_document_from_github_repo(r).to_dict() for r in sample_repos]

        assert len(docs) == 2
        assert docs[0]["source_type"] == "github"
        assert docs[0]["source_uri"] == "https://github.com/example/ml-toolkit"
        assert docs[0]["title"] == "ml-toolkit"

    def test_convert_preserves_metadata(self, sample_repos):
        """Metadata should include GitHub-specific fields."""
        from kubani.syndicates.news_digest.models import raw_document_from_github_repo

        doc = raw_document_from_github_repo(sample_repos[0])
        d = doc.to_dict()

        assert d["metadata"]["stars"] == 5000
        assert d["metadata"]["language"] == "Python"
        assert d["metadata"]["trending_score"] == 0.85

    def test_convert_empty_list(self):
        """Should return empty list for empty input."""
        from kubani.syndicates.news_digest.models import raw_document_from_github_repo

        docs = [raw_document_from_github_repo(r).to_dict() for r in []]
        assert docs == []


# =============================================================================
# IngestResult (shared result type)
# =============================================================================


class TestIngestResult:
    """Test the shared IngestResult dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        result = IngestResult()
        assert result.documents_collected == 0
        assert result.documents_new == 0
        assert result.documents_stored == 0
        assert result.success is True
        assert result.error is None

    def test_to_dict(self):
        """to_dict should return a complete dictionary."""
        result = IngestResult(
            source_type="rss",
            documents_collected=10,
            documents_new=7,
            documents_stored=7,
        )
        d = result.to_dict()

        assert d["source_type"] == "rss"
        assert d["documents_collected"] == 10
        assert d["documents_new"] == 7
        assert d["documents_stored"] == 7
        assert d["success"] is True
        assert d["error"] is None

    def test_to_dict_with_extra(self):
        """to_dict should include extra fields."""
        result = IngestResult(
            source_type="rss",
            extra={"feeds_fetched": 5},
        )
        d = result.to_dict()
        assert d["feeds_fetched"] == 5
