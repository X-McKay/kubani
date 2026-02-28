"""Shared test fixtures for news_digest syndicate tests.

Provides sample data, mock factories, and reusable fixtures for testing
the three-stage pipeline: Ingest → Analyze → Digest.
"""

import pytest


# =============================================================================
# Sample Source Data (pre-ingest)
# =============================================================================


@pytest.fixture
def sample_articles():
    """Sample RSS articles as returned by the feed collector."""
    return [
        {
            "url": "https://example.com/article1",
            "title": "GPT-5 Released with Major Improvements",
            "source": "AI News Daily",
            "published_at": "2026-01-15T10:00:00Z",
            "summary": "OpenAI releases GPT-5 with significant capabilities.",
            "author": "Jane Doe",
            "tags": ["gpt-5", "openai", "llm"],
            "source_category": "ai_focused",
            "importance_score": 9,
            "category": "product",
        },
        {
            "url": "https://example.com/article2",
            "title": "New Security Vulnerability in ML Framework",
            "source": "Security Weekly",
            "published_at": "2026-01-15T08:00:00Z",
            "summary": "Critical vulnerability discovered in popular ML library.",
            "author": "John Smith",
            "tags": ["security", "vulnerability"],
            "source_category": "security",
            "importance_score": 8,
            "category": "security",
        },
        {
            "url": "https://example.com/article3",
            "title": "AI Startup Raises $100M Series B",
            "source": "Tech Crunch",
            "published_at": "2026-01-15T06:00:00Z",
            "summary": "AI startup raises funding for expansion.",
            "author": "Mike Johnson",
            "tags": ["funding", "startup"],
            "source_category": "business",
            "importance_score": 5,
            "category": "business",
        },
    ]


@pytest.fixture
def sample_papers():
    """Sample arXiv papers as returned by the research-collector agent."""
    return [
        {
            "arxiv_id": "2601.12345",
            "title": "Advances in Transformer Architecture",
            "authors": ["Alice Researcher", "Bob Scientist"],
            "abstract": "We present novel improvements to transformer architectures...",
            "categories": ["cs.LG", "cs.AI"],
            "pdf_url": "https://arxiv.org/pdf/2601.12345.pdf",
            "published_at": "2026-01-14",
        },
        {
            "arxiv_id": "2601.12346",
            "title": "Efficient Fine-tuning Methods for LLMs",
            "authors": ["Carol Expert"],
            "abstract": "This paper explores parameter-efficient fine-tuning...",
            "categories": ["cs.CL", "cs.LG"],
            "pdf_url": "https://arxiv.org/pdf/2601.12346.pdf",
            "published_at": "2026-01-13",
        },
    ]


@pytest.fixture
def sample_repos():
    """Sample GitHub repos as returned by the research-collector agent."""
    return [
        {
            "repo_url": "https://github.com/example/ml-toolkit",
            "name": "ml-toolkit",
            "description": "A comprehensive ML toolkit for practitioners",
            "stars": 5000,
            "language": "Python",
            "topics": ["machine-learning", "pytorch", "toolkit"],
            "forks": 500,
            "trending_score": 0.85,
        },
        {
            "repo_url": "https://github.com/example/llm-inference",
            "name": "llm-inference",
            "description": "Fast LLM inference engine",
            "stars": 3000,
            "language": "Rust",
            "topics": ["llm", "inference", "optimization"],
            "forks": 200,
            "trending_score": 0.72,
        },
    ]


# =============================================================================
# Sample RawDocument Dicts (post-ingest)
# =============================================================================


@pytest.fixture
def sample_raw_documents():
    """Sample RawDocument dicts as produced by ingest workflows."""
    return [
        {
            "document_id": "doc-rss-001",
            "source_type": "rss",
            "source_uri": "https://example.com/article1",
            "content_hash": "abc123",
            "title": "GPT-5 Released with Major Improvements",
            "raw_content": "GPT-5 Released with Major Improvements\n\nOpenAI releases GPT-5.",
            "author": "Jane Doe",
            "source_name": "AI News Daily",
            "published_at": "2026-01-15T10:00:00Z",
            "retrieved_at": "2026-01-15T10:30:00Z",
            "metadata": {"source_category": "ai_focused", "tags": ["gpt-5", "openai"]},
        },
        {
            "document_id": "doc-arxiv-001",
            "source_type": "arxiv",
            "source_uri": "arxiv:2601.12345",
            "content_hash": "def456",
            "title": "Advances in Transformer Architecture",
            "raw_content": "Advances in Transformer Architecture\n\nWe present novel improvements...",
            "author": "Alice Researcher, Bob Scientist",
            "source_name": "arXiv",
            "published_at": "2026-01-14",
            "retrieved_at": "2026-01-15T10:30:00Z",
            "metadata": {"arxiv_id": "2601.12345", "categories": ["cs.LG", "cs.AI"]},
        },
        {
            "document_id": "doc-github-001",
            "source_type": "github",
            "source_uri": "https://github.com/example/ml-toolkit",
            "content_hash": "ghi789",
            "title": "ml-toolkit",
            "raw_content": "ml-toolkit\n\nA comprehensive ML toolkit for practitioners",
            "author": None,
            "source_name": "GitHub",
            "published_at": None,
            "retrieved_at": "2026-01-15T10:30:00Z",
            "metadata": {"stars": 5000, "language": "Python", "trending_score": 0.85},
        },
    ]


# =============================================================================
# Sample AnalyzedDocument Dicts (post-analyze)
# =============================================================================


@pytest.fixture
def sample_analyzed_documents():
    """Sample AnalyzedDocument dicts as produced by the analyze workflow."""
    return [
        {
            "document_id": "doc-rss-001",
            "source_type": "rss",
            "source_uri": "https://example.com/article1",
            "title": "GPT-5 Released with Major Improvements",
            "summary": "OpenAI has released GPT-5 with significant improvements.",
            "entities": ["OpenAI", "GPT-5"],
            "topics": ["LLM", "Product Launch"],
            "importance_score": 9,
            "source_name": "AI News Daily",
            "published_at": "2026-01-15T10:00:00Z",
            "analyzed_at": "2026-01-15T10:35:00Z",
            "metadata": {"source_category": "ai_focused"},
        },
        {
            "document_id": "doc-arxiv-001",
            "source_type": "arxiv",
            "source_uri": "arxiv:2601.12345",
            "title": "Advances in Transformer Architecture",
            "summary": "Novel improvements to transformer architectures for efficiency.",
            "entities": ["Transformer", "Attention Mechanism"],
            "topics": ["Architecture", "Efficiency"],
            "importance_score": 7,
            "source_name": "arXiv",
            "published_at": "2026-01-14",
            "analyzed_at": "2026-01-15T10:35:00Z",
            "metadata": {"arxiv_id": "2601.12345"},
        },
        {
            "document_id": "doc-github-001",
            "source_type": "github",
            "source_uri": "https://github.com/example/ml-toolkit",
            "title": "ml-toolkit",
            "summary": "A comprehensive ML toolkit gaining traction.",
            "entities": ["PyTorch"],
            "topics": ["Tools", "Machine Learning"],
            "importance_score": 6,
            "source_name": "GitHub",
            "published_at": None,
            "analyzed_at": "2026-01-15T10:35:00Z",
            "metadata": {"stars": 5000, "trending_score": 0.85},
        },
    ]


# =============================================================================
# Mock Factories
# =============================================================================


@pytest.fixture
def mock_activity_success():
    """Factory for creating successful activity mock results."""

    def _create(result_data: dict | None = None):
        return {"success": True, "error": None, **(result_data or {})}

    return _create


@pytest.fixture
def mock_activity_failure():
    """Factory for creating failed activity mock results."""

    def _create(error: str = "Activity failed"):
        return {"success": False, "error": error}

    return _create


# =============================================================================
# Sample Trends (legacy, kept for backward compatibility)
# =============================================================================


@pytest.fixture
def sample_trends():
    """Sample trends for testing."""
    return [
        {
            "topic": "GPT-5",
            "mention_count": 15,
            "momentum": 0.8,
            "description": "Major model release from OpenAI",
        },
        {
            "topic": "Mixture of Experts",
            "mention_count": 8,
            "momentum": 0.6,
            "description": "Architecture gaining traction",
        },
        {
            "topic": "AI Safety",
            "mention_count": 5,
            "momentum": 0.3,
            "description": "Ongoing discussions about alignment",
        },
    ]
