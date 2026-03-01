"""Full-text content extraction from article URLs.

This module provides pure functions for extracting readable article text
from web pages. It uses trafilatura as the primary extraction engine with
a requests-based fallback for downloading.

These functions are fully testable in isolation — they take a URL or HTML
string and return extracted text. No Temporal, no MCP, no side effects
beyond HTTP fetching.

Usage::

    # Extract from a URL (fetches + extracts)
    text = fetch_article_content("https://example.com/article")

    # Extract from already-downloaded HTML
    text = extract_text_from_html(html_string)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Maximum content length to store (chars). Longer articles are truncated.
MAX_CONTENT_LENGTH = 15_000

# Minimum content length to consider an extraction successful (chars).
# Below this threshold, the extraction is treated as a failure and the
# original snippet is kept.
MIN_USEFUL_CONTENT_LENGTH = 200

# Request timeout in seconds for fetching article HTML.
FETCH_TIMEOUT_SECONDS = 15

# User-Agent header for HTTP requests.
USER_AGENT = (
    "Mozilla/5.0 (compatible; KubaniBot/1.0; "
    "+https://github.com/X-McKay/kubani)"
)


# =============================================================================
# Pure Extraction Functions
# =============================================================================


def extract_text_from_html(html: str) -> str:
    """Extract the main article text from an HTML string.

    Uses trafilatura to parse the HTML and extract readable content,
    stripping navigation, ads, comments, and boilerplate.

    Args:
        html: Raw HTML content of a web page.

    Returns:
        Extracted article text, or empty string if extraction fails.
    """
    if not html or not html.strip():
        return ""

    try:
        import trafilatura

        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_recall=True,
        )
        return (text or "").strip()

    except Exception as e:
        logger.warning(f"trafilatura extraction failed: {e}")
        return ""


def fetch_article_content(url: str) -> str:
    """Fetch a web page and extract its main article text.

    Attempts to download the page using trafilatura's built-in fetcher
    first, then falls back to requests if that fails. The downloaded
    HTML is then passed through ``extract_text_from_html``.

    The result is truncated to ``MAX_CONTENT_LENGTH`` characters.

    Args:
        url: The URL of the article to fetch.

    Returns:
        Extracted article text, or empty string if fetching/extraction
        fails. Never raises — all errors are caught and logged.
    """
    if not url or not url.startswith(("http://", "https://")):
        return ""

    html = _download_html(url)
    if not html:
        return ""

    text = extract_text_from_html(html)

    # Truncate to max length
    if len(text) > MAX_CONTENT_LENGTH:
        text = text[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated]"

    return text


def _download_html(url: str) -> str:
    """Download HTML from a URL with trafilatura + requests fallback.

    Args:
        url: The URL to download.

    Returns:
        Raw HTML string, or empty string on failure.
    """
    # Try trafilatura's built-in fetcher first
    try:
        import trafilatura

        html = trafilatura.fetch_url(url)
        if html:
            return html
    except Exception as e:
        logger.debug(f"trafilatura fetch failed for {url}: {e}")

    # Fall back to requests
    try:
        import requests

        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=FETCH_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        response.raise_for_status()
        return response.text

    except Exception as e:
        logger.warning(f"Failed to download {url}: {e}")
        return ""


# =============================================================================
# Batch Enrichment (Pure Logic)
# =============================================================================


def enrich_document_content(
    document: dict[str, Any],
    fetched_content: str,
) -> dict[str, Any]:
    """Enrich a RawDocument dict with fetched full-text content.

    If the fetched content is substantially longer than the existing
    ``raw_content``, it replaces it. Otherwise, the original content
    is kept. The original snippet is always preserved in
    ``metadata["original_snippet"]``.

    This is a pure function — it returns a new dict without mutating
    the input.

    Args:
        document: A RawDocument dict.
        fetched_content: The full-text content fetched from the article URL.

    Returns:
        A new RawDocument dict with enriched content.
    """
    enriched = dict(document)
    metadata = dict(document.get("metadata", {}))

    original_content = document.get("raw_content", "")

    # Only replace if fetched content is meaningfully better
    if (
        fetched_content
        and len(fetched_content) >= MIN_USEFUL_CONTENT_LENGTH
        and len(fetched_content) > len(original_content) * 1.5
    ):
        metadata["original_snippet"] = original_content
        metadata["content_enriched"] = True
        metadata["enriched_content_length"] = len(fetched_content)
        enriched["raw_content"] = fetched_content
    else:
        metadata["content_enriched"] = False

    enriched["metadata"] = metadata
    return enriched


def should_enrich_document(document: dict[str, Any]) -> bool:
    """Determine whether a document should have its content enriched.

    Only RSS documents with short content and a valid URL are candidates
    for enrichment. arXiv papers already have abstracts, and GitHub repos
    have descriptions — neither benefits from URL fetching.

    Args:
        document: A RawDocument dict.

    Returns:
        True if the document should be enriched.
    """
    source_type = document.get("source_type", "")
    if source_type != "rss":
        return False

    # Already has substantial content
    raw_content = document.get("raw_content", "")
    if len(raw_content) > 1000:
        return False

    # Must have a fetchable URL
    source_uri = document.get("source_uri", "")
    if not source_uri.startswith(("http://", "https://")):
        return False

    return True

