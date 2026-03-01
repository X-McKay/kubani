"""Tests for the content_extraction module.

These tests validate the pure functions for full-text content extraction,
document enrichment, and enrichment eligibility. All functions are tested
in isolation — no network calls, no Temporal.

Test groups:
- extract_text_from_html: HTML → text extraction via trafilatura
- fetch_article_content: URL → text (mocked HTTP)
- enrich_document_content: Document enrichment logic
- should_enrich_document: Enrichment eligibility rules
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from kubani.syndicates.news_digest.content_extraction import (
    MAX_CONTENT_LENGTH,
    MIN_USEFUL_CONTENT_LENGTH,
    enrich_document_content,
    extract_text_from_html,
    fetch_article_content,
    should_enrich_document,
)


# =============================================================================
# Fixtures
# =============================================================================


def _make_rss_doc(
    raw_content: str = "Short snippet",
    source_uri: str = "https://example.com/article",
    source_type: str = "rss",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a minimal RawDocument dict for testing."""
    return {
        "document_id": "test-001",
        "source_type": source_type,
        "source_uri": source_uri,
        "title": "Test Article",
        "raw_content": raw_content,
        "metadata": metadata or {},
    }


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Article</title></head>
<body>
<nav>Navigation links here</nav>
<article>
<h1>Test Article Title</h1>
<p>This is the first paragraph of the article. It contains important information
about the topic being discussed. The article goes into detail about various
aspects of the subject matter.</p>
<p>The second paragraph provides additional context and analysis. It references
several key findings and includes quotes from experts in the field. This
paragraph is particularly relevant to understanding the broader implications.</p>
<p>In conclusion, the article summarizes the main points and offers a forward-looking
perspective on what these developments might mean for the future of the industry.</p>
</article>
<footer>Copyright 2026</footer>
</body>
</html>
"""


# =============================================================================
# Tests: extract_text_from_html
# =============================================================================


class TestExtractTextFromHtml:
    """Test the HTML → text extraction function."""

    def test_extracts_article_text(self) -> None:
        """Extracts main content from a well-structured HTML page."""
        text = extract_text_from_html(SAMPLE_HTML)
        assert len(text) > 0
        # Should contain article content
        assert "first paragraph" in text or "important information" in text

    def test_empty_html_returns_empty(self) -> None:
        """Empty or whitespace HTML returns empty string."""
        assert extract_text_from_html("") == ""
        assert extract_text_from_html("   ") == ""
        assert extract_text_from_html(None) == ""  # type: ignore[arg-type]

    def test_minimal_html(self) -> None:
        """Handles minimal HTML with just text."""
        text = extract_text_from_html("<p>Hello world</p>")
        # trafilatura may or may not extract this depending on heuristics
        # The important thing is it doesn't crash
        assert isinstance(text, str)

    def test_strips_whitespace(self) -> None:
        """Result is stripped of leading/trailing whitespace."""
        html = "<article><p>  Content with spaces  </p></article>"
        text = extract_text_from_html(html)
        if text:  # trafilatura may not extract from minimal HTML
            assert text == text.strip()

    def test_handles_trafilatura_exception(self) -> None:
        """Returns empty string if trafilatura raises."""
        import trafilatura as traf_module

        original_extract = traf_module.extract
        traf_module.extract = MagicMock(side_effect=RuntimeError("parse error"))
        try:
            text = extract_text_from_html("<p>test</p>")
            assert text == ""
        finally:
            traf_module.extract = original_extract


# =============================================================================
# Tests: fetch_article_content
# =============================================================================


class TestFetchArticleContent:
    """Test the URL → text fetching function."""

    def test_invalid_url_returns_empty(self) -> None:
        """Invalid URLs return empty string without making requests."""
        assert fetch_article_content("") == ""
        assert fetch_article_content("not-a-url") == ""
        assert fetch_article_content("ftp://example.com") == ""

    @patch(
        "kubani.syndicates.news_digest.content_extraction._download_html",
        return_value="",
    )
    def test_download_failure_returns_empty(self, mock_dl: MagicMock) -> None:
        """Returns empty string if download fails."""
        text = fetch_article_content("https://example.com/article")
        assert text == ""

    @patch(
        "kubani.syndicates.news_digest.content_extraction._download_html",
        return_value=SAMPLE_HTML,
    )
    def test_successful_extraction(self, mock_dl: MagicMock) -> None:
        """Successfully extracts text from downloaded HTML."""
        text = fetch_article_content("https://example.com/article")
        assert len(text) > 0

    @patch(
        "kubani.syndicates.news_digest.content_extraction._download_html",
    )
    def test_truncates_long_content(self, mock_dl: MagicMock) -> None:
        """Content longer than MAX_CONTENT_LENGTH is truncated."""
        # Create HTML that will produce very long text
        long_text = "A" * (MAX_CONTENT_LENGTH + 5000)
        mock_dl.return_value = f"<article><p>{long_text}</p></article>"

        with patch(
            "kubani.syndicates.news_digest.content_extraction.extract_text_from_html",
            return_value=long_text,
        ):
            text = fetch_article_content("https://example.com/long-article")
            assert len(text) <= MAX_CONTENT_LENGTH + 50  # +50 for truncation notice
            assert "[Content truncated]" in text


# =============================================================================
# Tests: enrich_document_content
# =============================================================================


class TestEnrichDocumentContent:
    """Test the document enrichment logic."""

    def test_enriches_with_longer_content(self) -> None:
        """Replaces short snippet with longer fetched content."""
        doc = _make_rss_doc(raw_content="Short snippet")
        long_content = "A" * 500  # Well above MIN_USEFUL_CONTENT_LENGTH

        enriched = enrich_document_content(doc, long_content)

        assert enriched["raw_content"] == long_content
        assert enriched["metadata"]["content_enriched"] is True
        assert enriched["metadata"]["original_snippet"] == "Short snippet"
        assert enriched["metadata"]["enriched_content_length"] == 500

    def test_keeps_original_when_fetch_too_short(self) -> None:
        """Keeps original content if fetched content is too short."""
        doc = _make_rss_doc(raw_content="Short snippet")
        short_content = "A" * 50  # Below MIN_USEFUL_CONTENT_LENGTH

        enriched = enrich_document_content(doc, short_content)

        assert enriched["raw_content"] == "Short snippet"
        assert enriched["metadata"]["content_enriched"] is False

    def test_keeps_original_when_fetch_empty(self) -> None:
        """Keeps original content if fetched content is empty."""
        doc = _make_rss_doc(raw_content="Short snippet")

        enriched = enrich_document_content(doc, "")

        assert enriched["raw_content"] == "Short snippet"
        assert enriched["metadata"]["content_enriched"] is False

    def test_keeps_original_when_fetch_not_much_longer(self) -> None:
        """Keeps original if fetched content isn't 1.5x longer."""
        original = "A" * 300
        fetched = "B" * 350  # Only ~1.17x longer, not 1.5x
        doc = _make_rss_doc(raw_content=original)

        enriched = enrich_document_content(doc, fetched)

        assert enriched["raw_content"] == original
        assert enriched["metadata"]["content_enriched"] is False

    def test_does_not_mutate_input(self) -> None:
        """Input document is not modified."""
        doc = _make_rss_doc(raw_content="Original")
        original_doc = dict(doc)

        enrich_document_content(doc, "A" * 500)

        assert doc == original_doc

    def test_preserves_existing_metadata(self) -> None:
        """Existing metadata fields are preserved."""
        doc = _make_rss_doc(
            raw_content="Short",
            metadata={"existing_key": "existing_value"},
        )

        enriched = enrich_document_content(doc, "A" * 500)

        assert enriched["metadata"]["existing_key"] == "existing_value"
        assert enriched["metadata"]["content_enriched"] is True


# =============================================================================
# Tests: should_enrich_document
# =============================================================================


class TestShouldEnrichDocument:
    """Test the enrichment eligibility rules."""

    def test_rss_with_short_content_and_url(self) -> None:
        """RSS document with short content and valid URL → should enrich."""
        doc = _make_rss_doc(
            raw_content="Short snippet",
            source_uri="https://example.com/article",
            source_type="rss",
        )
        assert should_enrich_document(doc) is True

    def test_arxiv_not_enriched(self) -> None:
        """arXiv documents are never enriched."""
        doc = _make_rss_doc(source_type="arxiv")
        assert should_enrich_document(doc) is False

    def test_github_not_enriched(self) -> None:
        """GitHub documents are never enriched."""
        doc = _make_rss_doc(source_type="github")
        assert should_enrich_document(doc) is False

    def test_rss_with_long_content_not_enriched(self) -> None:
        """RSS document with substantial content → skip enrichment."""
        doc = _make_rss_doc(raw_content="A" * 1500)
        assert should_enrich_document(doc) is False

    def test_rss_with_exactly_1000_chars_enriched(self) -> None:
        """RSS document with exactly 1000 chars → still enriched."""
        doc = _make_rss_doc(raw_content="A" * 1000)
        assert should_enrich_document(doc) is True

    def test_rss_with_1001_chars_not_enriched(self) -> None:
        """RSS document with 1001 chars → not enriched."""
        doc = _make_rss_doc(raw_content="A" * 1001)
        assert should_enrich_document(doc) is False

    def test_rss_without_url_not_enriched(self) -> None:
        """RSS document without a fetchable URL → skip enrichment."""
        doc = _make_rss_doc(source_uri="not-a-url")
        assert should_enrich_document(doc) is False

    def test_rss_with_non_http_url_not_enriched(self) -> None:
        """RSS document with non-HTTP URL → skip enrichment."""
        doc = _make_rss_doc(source_uri="ftp://example.com/file")
        assert should_enrich_document(doc) is False

    def test_empty_source_type_not_enriched(self) -> None:
        """Document with empty source_type → not enriched."""
        doc = _make_rss_doc(source_type="")
        assert should_enrich_document(doc) is False

    def test_missing_fields_handled_gracefully(self) -> None:
        """Minimal document dict doesn't crash."""
        assert should_enrich_document({}) is False
        assert should_enrich_document({"source_type": "rss"}) is False
