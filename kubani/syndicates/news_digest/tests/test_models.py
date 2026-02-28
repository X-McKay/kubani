"""Tests for the News Digest data models.

Tests the pure data structures and utility functions used across
the three-stage pipeline.
"""

from kubani.syndicates.news_digest.models import (
    AnalyzedDocument,
    RawDocument,
    compute_content_hash,
    make_dedup_key,
    make_document_id,
    make_knowledge_topic,
    parse_json_array_from_text,
    parse_json_object_from_text,
    raw_document_from_arxiv_paper,
    raw_document_from_github_repo,
    raw_document_from_rss_entry,
)


# =============================================================================
# RawDocument
# =============================================================================


class TestRawDocument:
    """Test RawDocument dataclass."""

    def test_default_values(self):
        """RawDocument should have sensible defaults for optional fields."""
        doc = RawDocument(
            document_id="test-id",
            source_type="rss",
            source_uri="https://example.com",
            content_hash="abc123",
            title="Test",
            raw_content="Test content",
        )
        assert doc.author is None
        assert doc.source_name == ""
        assert doc.published_at is None
        assert doc.retrieved_at == ""
        assert doc.metadata == {}

    def test_to_dict(self):
        """to_dict should produce a complete dictionary."""
        doc = RawDocument(
            document_id="test-id",
            source_type="rss",
            source_uri="https://example.com",
            content_hash="abc123",
            title="Test",
            raw_content="Test content",
            author="Author",
            source_name="Source",
            published_at="2026-01-15T10:00:00Z",
            retrieved_at="2026-01-15T10:30:00Z",
            metadata={"key": "value"},
        )
        d = doc.to_dict()

        assert d["document_id"] == "test-id"
        assert d["source_type"] == "rss"
        assert d["source_uri"] == "https://example.com"
        assert d["content_hash"] == "abc123"
        assert d["title"] == "Test"
        assert d["raw_content"] == "Test content"
        assert d["author"] == "Author"
        assert d["metadata"] == {"key": "value"}

    def test_from_dict(self):
        """from_dict should reconstruct a RawDocument."""
        data = {
            "document_id": "test-id",
            "source_type": "arxiv",
            "source_uri": "arxiv:123",
            "content_hash": "abc",
            "title": "Paper",
            "raw_content": "Content",
            "author": "Author",
        }
        doc = RawDocument.from_dict(data)

        assert doc.document_id == "test-id"
        assert doc.source_type == "arxiv"
        assert doc.source_uri == "arxiv:123"
        assert doc.title == "Paper"

    def test_from_dict_with_missing_fields(self):
        """from_dict should handle missing fields gracefully."""
        doc = RawDocument.from_dict({})

        assert doc.document_id == ""
        assert doc.source_type == "rss"
        assert doc.metadata == {}

    def test_roundtrip(self):
        """to_dict → from_dict should produce an equivalent object."""
        original = RawDocument(
            document_id="test-id",
            source_type="github",
            source_uri="https://github.com/test/repo",
            content_hash="xyz",
            title="Repo",
            raw_content="Description",
            metadata={"stars": 100},
        )
        reconstructed = RawDocument.from_dict(original.to_dict())

        assert reconstructed.document_id == original.document_id
        assert reconstructed.source_type == original.source_type
        assert reconstructed.metadata == original.metadata

    def test_dedup_key_property(self):
        """dedup_key property should return the correct cache key."""
        doc = RawDocument(
            document_id="test-id",
            source_type="rss",
            source_uri="https://example.com/article",
            content_hash="abc123",
            title="Test",
            raw_content="content",
        )
        expected = make_dedup_key("rss", "https://example.com/article")
        assert doc.dedup_key == expected

    def test_dedup_key_deterministic(self):
        """Same source_uri should always produce the same dedup_key."""
        doc1 = RawDocument(
            document_id="id1",
            source_type="arxiv",
            source_uri="arxiv:2602.00001",
            content_hash="h1",
            title="Paper 1",
            raw_content="content 1",
        )
        doc2 = RawDocument(
            document_id="id2",
            source_type="arxiv",
            source_uri="arxiv:2602.00001",
            content_hash="h2",
            title="Paper 2",
            raw_content="content 2",
        )
        assert doc1.dedup_key == doc2.dedup_key

    def test_dedup_key_differs_by_uri(self):
        """Different source_uris should produce different dedup_keys."""
        doc1 = RawDocument(
            document_id="id1",
            source_type="rss",
            source_uri="https://example.com/a",
            content_hash="h1",
            title="A",
            raw_content="a",
        )
        doc2 = RawDocument(
            document_id="id2",
            source_type="rss",
            source_uri="https://example.com/b",
            content_hash="h2",
            title="B",
            raw_content="b",
        )
        assert doc1.dedup_key != doc2.dedup_key


# =============================================================================
# AnalyzedDocument
# =============================================================================


class TestAnalyzedDocument:
    """Test AnalyzedDocument dataclass."""

    def test_default_values(self):
        """AnalyzedDocument should have sensible defaults."""
        doc = AnalyzedDocument(
            document_id="test-id",
            source_type="rss",
            source_uri="https://example.com",
            title="Test",
        )
        assert doc.summary == ""
        assert doc.entities == []
        assert doc.topics == []
        assert doc.importance_score == 5
        assert doc.metadata == {}

    def test_to_dict(self):
        """to_dict should produce a complete dictionary."""
        doc = AnalyzedDocument(
            document_id="test-id",
            source_type="rss",
            source_uri="https://example.com",
            title="Test",
            summary="A summary",
            entities=["OpenAI", "GPT-5"],
            topics=["LLM", "Product Launch"],
            importance_score=9,
        )
        d = doc.to_dict()

        assert d["document_id"] == "test-id"
        assert d["entities"] == ["OpenAI", "GPT-5"]
        assert d["topics"] == ["LLM", "Product Launch"]
        assert d["importance_score"] == 9

    def test_from_dict(self):
        """from_dict should reconstruct an AnalyzedDocument."""
        data = {
            "document_id": "test-id",
            "source_type": "arxiv",
            "source_uri": "arxiv:123",
            "title": "Paper",
            "summary": "Summary",
            "entities": ["Entity1"],
            "topics": ["Topic1"],
            "importance_score": 8,
        }
        doc = AnalyzedDocument.from_dict(data)

        assert doc.importance_score == 8
        assert doc.entities == ["Entity1"]

    def test_roundtrip(self):
        """to_dict → from_dict should produce an equivalent object."""
        original = AnalyzedDocument(
            document_id="test-id",
            source_type="rss",
            source_uri="https://example.com",
            title="Test",
            entities=["A", "B"],
            topics=["X", "Y"],
            importance_score=7,
        )
        reconstructed = AnalyzedDocument.from_dict(original.to_dict())

        assert reconstructed.entities == original.entities
        assert reconstructed.topics == original.topics
        assert reconstructed.importance_score == original.importance_score


# =============================================================================
# Pure Utility Functions
# =============================================================================


class TestComputeContentHash:
    """Test compute_content_hash function."""

    def test_deterministic(self):
        """Same content should produce the same hash."""
        h1 = compute_content_hash("hello world")
        h2 = compute_content_hash("hello world")
        assert h1 == h2

    def test_different_content_different_hash(self):
        """Different content should produce different hashes."""
        h1 = compute_content_hash("hello")
        h2 = compute_content_hash("world")
        assert h1 != h2

    def test_returns_hex_string(self):
        """Hash should be a hex string of the expected length."""
        h = compute_content_hash("test")
        assert len(h) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_string(self):
        """Empty string should produce a valid hash."""
        h = compute_content_hash("")
        assert len(h) == 64


class TestMakeDedupKey:
    """Test make_dedup_key function."""

    def test_format(self):
        """Key should follow the expected format."""
        key = make_dedup_key("rss", "https://example.com/article")
        assert key.startswith("news:dedup:rss:")
        assert len(key.split(":")[-1]) == 16

    def test_deterministic(self):
        """Same inputs should produce the same key."""
        k1 = make_dedup_key("arxiv", "arxiv:2601.12345")
        k2 = make_dedup_key("arxiv", "arxiv:2601.12345")
        assert k1 == k2

    def test_different_source_types(self):
        """Different source types should produce different keys."""
        k1 = make_dedup_key("rss", "https://example.com")
        k2 = make_dedup_key("github", "https://example.com")
        assert k1 != k2

    def test_different_uris(self):
        """Different URIs should produce different keys."""
        k1 = make_dedup_key("rss", "https://example.com/a")
        k2 = make_dedup_key("rss", "https://example.com/b")
        assert k1 != k2


class TestMakeDocumentId:
    """Test make_document_id function."""

    def test_returns_uuid_string(self):
        """Should return a valid UUID4 string."""
        import uuid

        doc_id = make_document_id()
        uuid.UUID(doc_id, version=4)  # Raises if invalid

    def test_unique(self):
        """Each call should produce a unique ID."""
        ids = {make_document_id() for _ in range(100)}
        assert len(ids) == 100


class TestMakeKnowledgeTopic:
    """Test make_knowledge_topic function."""

    def test_format(self):
        """Should produce the expected topic path."""
        topic = make_knowledge_topic("rss", "doc-123")
        assert topic == "news/rss/doc-123"

    def test_all_source_types(self):
        """Should work for all source types."""
        assert make_knowledge_topic("rss", "id") == "news/rss/id"
        assert make_knowledge_topic("arxiv", "id") == "news/arxiv/id"
        assert make_knowledge_topic("github", "id") == "news/github/id"


# =============================================================================
# Source-Specific Converters
# =============================================================================


class TestRawDocumentFromRSSEntry:
    """Test raw_document_from_rss_entry conversion."""

    def test_basic_conversion(self, sample_articles):
        """Should convert an RSS entry to a RawDocument."""
        doc = raw_document_from_rss_entry(sample_articles[0])

        assert doc.source_type == "rss"
        assert doc.title == "GPT-5 Released with Major Improvements"
        assert doc.source_uri == "https://example.com/article1"
        assert doc.author == "Jane Doe"
        assert doc.source_name == "AI News Daily"
        assert doc.document_id  # Should be non-empty UUID
        assert doc.content_hash  # Should be non-empty hash
        assert doc.retrieved_at  # Should be non-empty timestamp

    def test_content_includes_title_and_summary(self, sample_articles):
        """raw_content should combine title and summary."""
        doc = raw_document_from_rss_entry(sample_articles[0])
        assert "GPT-5 Released" in doc.raw_content
        assert "OpenAI releases GPT-5" in doc.raw_content

    def test_metadata_preserved(self, sample_articles):
        """Source-specific metadata should be preserved."""
        doc = raw_document_from_rss_entry(sample_articles[0])
        assert doc.metadata["source_category"] == "ai_focused"
        assert "gpt-5" in doc.metadata["tags"]

    def test_source_name_override(self, sample_articles):
        """Explicit source_name should override entry source."""
        doc = raw_document_from_rss_entry(sample_articles[0], source_name="Override")
        assert doc.source_name == "Override"

    def test_empty_entry(self):
        """Should handle an empty entry dict gracefully."""
        doc = raw_document_from_rss_entry({})
        assert doc.source_type == "rss"
        assert doc.title == ""
        assert doc.source_uri == ""


class TestRawDocumentFromArxivPaper:
    """Test raw_document_from_arxiv_paper conversion."""

    def test_basic_conversion(self, sample_papers):
        """Should convert an arXiv paper to a RawDocument."""
        doc = raw_document_from_arxiv_paper(sample_papers[0])

        assert doc.source_type == "arxiv"
        assert doc.title == "Advances in Transformer Architecture"
        assert doc.source_uri == "arxiv:2601.12345"
        assert doc.source_name == "arXiv"
        assert "Alice Researcher" in doc.author

    def test_content_includes_title_and_abstract(self, sample_papers):
        """raw_content should combine title and abstract."""
        doc = raw_document_from_arxiv_paper(sample_papers[0])
        assert "Advances in Transformer" in doc.raw_content
        assert "novel improvements" in doc.raw_content

    def test_metadata_preserved(self, sample_papers):
        """arXiv-specific metadata should be preserved."""
        doc = raw_document_from_arxiv_paper(sample_papers[0])
        assert doc.metadata["arxiv_id"] == "2601.12345"
        assert "cs.LG" in doc.metadata["categories"]

    def test_empty_paper(self):
        """Should handle an empty paper dict gracefully."""
        doc = raw_document_from_arxiv_paper({})
        assert doc.source_type == "arxiv"
        assert doc.source_uri == "arxiv:"


class TestRawDocumentFromGitHubRepo:
    """Test raw_document_from_github_repo conversion."""

    def test_basic_conversion(self, sample_repos):
        """Should convert a GitHub repo to a RawDocument."""
        doc = raw_document_from_github_repo(sample_repos[0])

        assert doc.source_type == "github"
        assert doc.title == "ml-toolkit"
        assert doc.source_uri == "https://github.com/example/ml-toolkit"
        assert doc.source_name == "GitHub"
        assert doc.author is None  # Repos don't have a single author

    def test_metadata_preserved(self, sample_repos):
        """GitHub-specific metadata should be preserved."""
        doc = raw_document_from_github_repo(sample_repos[0])
        assert doc.metadata["stars"] == 5000
        assert doc.metadata["language"] == "Python"
        assert doc.metadata["trending_score"] == 0.85

    def test_empty_repo(self):
        """Should handle an empty repo dict gracefully."""
        doc = raw_document_from_github_repo({})
        assert doc.source_type == "github"
        assert doc.title == ""


# =============================================================================
# JSON Parsing Utilities
# =============================================================================


class TestParseJsonArrayFromText:
    """Test parse_json_array_from_text function."""

    def test_direct_json_array(self):
        """Should parse a direct JSON array."""
        result = parse_json_array_from_text('[{"key": "value"}]')
        assert len(result) == 1
        assert result[0]["key"] == "value"

    def test_wrapped_in_text(self):
        """Should extract JSON array from surrounding text."""
        result = parse_json_array_from_text('Here are results: [{"key": "value"}] Done.')
        assert len(result) == 1

    def test_markdown_code_fence(self):
        """Should handle markdown code fences."""
        text = '```json\n[{"key": "value"}]\n```'
        result = parse_json_array_from_text(text)
        assert len(result) == 1

    def test_dict_with_list_value(self):
        """Should extract list from a dict wrapper."""
        text = '{"results": [{"key": "value"}]}'
        result = parse_json_array_from_text(text)
        assert len(result) == 1

    def test_invalid_json(self):
        """Should return empty list for invalid JSON."""
        result = parse_json_array_from_text("This is not JSON")
        assert result == []

    def test_empty_string(self):
        """Should return empty list for empty string."""
        result = parse_json_array_from_text("")
        assert result == []

    def test_none_like_empty(self):
        """Should return empty list for None-like input."""
        result = parse_json_array_from_text("")
        assert result == []

    def test_empty_array(self):
        """Should return empty list for empty JSON array."""
        result = parse_json_array_from_text("[]")
        assert result == []


class TestParseJsonObjectFromText:
    """Test parse_json_object_from_text function."""

    def test_direct_json_object(self):
        """Should parse a direct JSON object."""
        result = parse_json_object_from_text('{"key": "value"}')
        assert result["key"] == "value"

    def test_wrapped_in_text(self):
        """Should extract JSON object from surrounding text."""
        result = parse_json_object_from_text('Result: {"key": "value"} End.')
        assert result["key"] == "value"

    def test_markdown_code_fence(self):
        """Should handle markdown code fences."""
        text = '```json\n{"key": "value"}\n```'
        result = parse_json_object_from_text(text)
        assert result["key"] == "value"

    def test_invalid_json(self):
        """Should return empty dict for invalid JSON."""
        result = parse_json_object_from_text("Not JSON")
        assert result == {}

    def test_empty_string(self):
        """Should return empty dict for empty string."""
        result = parse_json_object_from_text("")
        assert result == {}
