"""Data models for the News Digest three-stage pipeline.

This module defines the core data structures that flow through the pipeline:

Stage 1 (Ingest) produces → RawDocument
Stage 2 (Analyze) produces → AnalyzedDocument
Stage 3 (Digest) consumes → AnalyzedDocument

All models are plain dataclasses for Temporal serialization compatibility.
Pure functions are provided for hashing, deduplication key generation,
and conversion between stages.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

# =============================================================================
# Source Types
# =============================================================================

SourceType = Literal["rss", "arxiv", "github"]


# =============================================================================
# Stage 1: Raw Document (output of Ingest)
# =============================================================================


@dataclass
class RawDocument:
    """A raw document produced by an ingest workflow.

    This is the standardized output of all source-specific collectors.
    It contains the minimal information needed for deduplication and
    downstream analysis, without any enrichment.

    Attributes:
        document_id: Unique identifier (UUID) for this document.
        source_type: The type of source this document came from.
        source_uri: The unique URI of the source (URL, arXiv ID, etc.).
        content_hash: SHA-256 hash of the primary content for dedup.
        title: Document title.
        raw_content: The full text or primary content of the document.
        author: Author name(s), if available.
        source_name: Human-readable name of the source feed/site.
        published_at: ISO format publication date, if available.
        retrieved_at: ISO format timestamp of when this was collected.
        metadata: Source-specific metadata (stars, categories, etc.).
    """

    document_id: str
    source_type: SourceType
    source_uri: str
    content_hash: str
    title: str
    raw_content: str
    author: str | None = None
    source_name: str = ""
    published_at: str | None = None
    retrieved_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        """Compute the deduplication cache key for this document.

        Returns:
            A cache key string in the format ``news:dedup:{source_type}:{hash}``.
        """
        return make_dedup_key(self.source_type, self.source_uri)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary for Temporal transport."""
        return {
            "document_id": self.document_id,
            "source_type": self.source_type,
            "source_uri": self.source_uri,
            "content_hash": self.content_hash,
            "title": self.title,
            "raw_content": self.raw_content,
            "author": self.author,
            "source_name": self.source_name,
            "published_at": self.published_at,
            "retrieved_at": self.retrieved_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawDocument:
        """Deserialize from a plain dictionary."""
        return cls(
            document_id=data.get("document_id", ""),
            source_type=data.get("source_type", "rss"),
            source_uri=data.get("source_uri", ""),
            content_hash=data.get("content_hash", ""),
            title=data.get("title", ""),
            raw_content=data.get("raw_content", ""),
            author=data.get("author"),
            source_name=data.get("source_name", ""),
            published_at=data.get("published_at"),
            retrieved_at=data.get("retrieved_at", ""),
            metadata=data.get("metadata", {}),
        )


# =============================================================================
# Stage 2: Analyzed Document (output of Analyze)
# =============================================================================


@dataclass
class AnalyzedDocument:
    """An enriched document produced by the analysis workflow.

    Extends the raw document with structured analysis results including
    entity extraction, topic classification, importance scoring, and
    a concise AI-generated summary.

    Attributes:
        document_id: Same ID as the source RawDocument.
        source_type: Inherited from RawDocument.
        source_uri: Inherited from RawDocument.
        title: Inherited from RawDocument.
        summary: AI-generated concise summary of the content.
        entities: Extracted entities (people, companies, products).
        topics: Classified topics/themes.
        importance_score: Significance score from 1-10.
        source_name: Human-readable source name.
        published_at: ISO format publication date.
        analyzed_at: ISO format timestamp of when analysis completed.
        metadata: Merged metadata from raw + analysis.
    """

    document_id: str
    source_type: SourceType
    source_uri: str
    title: str
    summary: str = ""
    entities: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    importance_score: int = 5
    source_name: str = ""
    published_at: str | None = None
    analyzed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary for Temporal transport."""
        return {
            "document_id": self.document_id,
            "source_type": self.source_type,
            "source_uri": self.source_uri,
            "title": self.title,
            "summary": self.summary,
            "entities": self.entities,
            "topics": self.topics,
            "importance_score": self.importance_score,
            "source_name": self.source_name,
            "published_at": self.published_at,
            "analyzed_at": self.analyzed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalyzedDocument:
        """Deserialize from a plain dictionary."""
        return cls(
            document_id=data.get("document_id", ""),
            source_type=data.get("source_type", "rss"),
            source_uri=data.get("source_uri", ""),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            entities=data.get("entities", []),
            topics=data.get("topics", []),
            importance_score=data.get("importance_score", 5),
            source_name=data.get("source_name", ""),
            published_at=data.get("published_at"),
            analyzed_at=data.get("analyzed_at", ""),
            metadata=data.get("metadata", {}),
        )


# =============================================================================
# Pure Utility Functions
# =============================================================================


def compute_content_hash(content: str) -> str:
    """Compute a SHA-256 hash of content for deduplication.

    Args:
        content: The text content to hash.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def make_dedup_key(source_type: SourceType, source_uri: str) -> str:
    """Generate a deterministic cache key for deduplication.

    The key format is: ``news:dedup:{source_type}:{hash}``

    Args:
        source_type: The source type (rss, arxiv, github).
        source_uri: The unique URI of the source.

    Returns:
        A cache key string suitable for Redis/Memory MCP.
    """
    uri_hash = hashlib.sha256(source_uri.encode("utf-8")).hexdigest()[:16]
    return f"news:dedup:{source_type}:{uri_hash}"


def make_document_id(seed: str = "") -> str:
    """Generate a unique document ID.

    Uses UUID5 (deterministic, SHA-1 based) when a seed is provided,
    which is safe inside Temporal's workflow sandbox. Falls back to
    UUID4 when no seed is given (for use outside workflows).

    Args:
        seed: Optional seed string (e.g. source_uri or content_hash).

    Returns:
        A UUID string.
    """
    if seed:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))
    return str(uuid.uuid4())


def make_knowledge_topic(source_type: SourceType, document_id: str) -> str:
    """Generate a knowledge topic path for storing a document.

    Args:
        source_type: The source type.
        document_id: The document's unique ID.

    Returns:
        A topic path string like ``news/rss/{document_id}``.
    """
    return f"news/{source_type}/{document_id}"


def raw_document_from_rss_entry(entry: dict[str, Any], source_name: str = "") -> RawDocument:
    """Convert an RSS feed entry dict into a RawDocument.

    Args:
        entry: A dict with keys: title, url, source, published_date, summary, author,
               source_category.
        source_name: Override source name if not in entry.

    Returns:
        A RawDocument instance.
    """
    title = entry.get("title", "")
    summary = entry.get("summary", "")
    content = f"{title}\n\n{summary}" if summary else title

    return RawDocument(
        document_id=make_document_id(entry.get("url", "")),
        source_type="rss",
        source_uri=entry.get("url", ""),
        content_hash=compute_content_hash(content),
        title=title,
        raw_content=content,
        author=entry.get("author"),
        source_name=source_name or entry.get("source", ""),
        published_at=entry.get("published_date") or entry.get("published_at"),
        retrieved_at=datetime.utcnow().isoformat(),
        metadata={
            "source_category": entry.get("source_category", ""),
            "tags": entry.get("tags", []),
        },
    )


def raw_document_from_arxiv_paper(paper: dict[str, Any]) -> RawDocument:
    """Convert an arXiv paper dict into a RawDocument.

    Args:
        paper: A dict with keys: arxiv_id, title, abstract, authors,
               categories, published_at.

    Returns:
        A RawDocument instance.
    """
    arxiv_id = paper.get("arxiv_id", "")
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")
    content = f"{title}\n\n{abstract}"

    return RawDocument(
        document_id=make_document_id(f"arxiv:{arxiv_id}"),
        source_type="arxiv",
        source_uri=f"arxiv:{arxiv_id}",
        content_hash=compute_content_hash(content),
        title=title,
        raw_content=content,
        author=", ".join(paper.get("authors", [])),
        source_name="arXiv",
        published_at=paper.get("published_at") or paper.get("published_date"),
        retrieved_at=datetime.utcnow().isoformat(),
        metadata={
            "arxiv_id": arxiv_id,
            "categories": paper.get("categories", []),
            "authors": paper.get("authors", []),
        },
    )


def raw_document_from_github_repo(repo: dict[str, Any]) -> RawDocument:
    """Convert a GitHub repo dict into a RawDocument.

    Args:
        repo: A dict with keys: repo_url, name, description, stars,
              language, topics, forks, trending_score.

    Returns:
        A RawDocument instance.
    """
    name = repo.get("name", "")
    description = repo.get("description", "")
    content = f"{name}\n\n{description}" if description else name

    return RawDocument(
        document_id=make_document_id(repo.get("repo_url", "")),
        source_type="github",
        source_uri=repo.get("repo_url", ""),
        content_hash=compute_content_hash(content),
        title=name,
        raw_content=content,
        author=None,
        source_name="GitHub",
        published_at=None,
        retrieved_at=datetime.utcnow().isoformat(),
        metadata={
            "stars": repo.get("stars", 0),
            "forks": repo.get("forks", 0),
            "language": repo.get("language"),
            "topics": repo.get("topics", []),
            "trending_score": repo.get("trending_score", 0.0),
        },
    )


def parse_json_array_from_text(text: str) -> list[dict[str, Any]]:
    """Safely extract a JSON array from agent output text.

    Handles common cases where the JSON is wrapped in markdown
    code fences or surrounded by explanatory text.

    Args:
        text: Raw text that may contain a JSON array.

    Returns:
        A list of dicts, or empty list if parsing fails.
    """
    import json

    if not text:
        return []

    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (fences)
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    # Try direct parse first
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and any(isinstance(v, list) for v in result.values()):
            # Return the first list value found
            for v in result.values():
                if isinstance(v, list):
                    return v
    except json.JSONDecodeError:
        pass

    # Fall back to bracket extraction
    try:
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError:
        pass

    return []


def parse_json_object_from_text(text: str) -> dict[str, Any]:
    """Safely extract a JSON object from agent output text.

    Args:
        text: Raw text that may contain a JSON object.

    Returns:
        A dict, or empty dict if parsing fails.
    """
    import json

    if not text:
        return {}

    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    # Try direct parse first
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Fall back to brace extraction
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError:
        pass

    return {}
