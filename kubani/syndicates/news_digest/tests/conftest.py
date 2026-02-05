"""Shared test fixtures for news_digest syndicate tests."""

import pytest


@pytest.fixture
def sample_articles():
    """Sample articles for testing."""
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
    """Sample arXiv papers for testing."""
    return [
        {
            "arxiv_id": "2601.12345",
            "title": "Advances in Transformer Architecture",
            "authors": ["Alice Researcher", "Bob Scientist"],
            "abstract": "We present novel improvements to transformer architectures...",
            "categories": ["cs.LG", "cs.AI"],
            "pdf_url": "https://arxiv.org/pdf/2601.12345.pdf",
            "published_date": "2026-01-14",
        },
        {
            "arxiv_id": "2601.12346",
            "title": "Efficient Fine-tuning Methods for LLMs",
            "authors": ["Carol Expert"],
            "abstract": "This paper explores parameter-efficient fine-tuning...",
            "categories": ["cs.CL", "cs.LG"],
            "pdf_url": "https://arxiv.org/pdf/2601.12346.pdf",
            "published_date": "2026-01-13",
        },
    ]


@pytest.fixture
def sample_repos():
    """Sample GitHub repos for testing."""
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
