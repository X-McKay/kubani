"""Temporal activities for the News Digest three-stage pipeline.

This module provides all activities used by the Ingest, Analyze, and Digest
workflows. Activities are thin wrappers around Memory MCP operations, designed
to be independently testable and composable.

Activity groups:
- Content Enrichment: fetch_article_content_activity
- Deduplication: batch_check_duplicates_activity
- Storage: store_raw_documents_activity, store_analyzed_document_activity
- Query: query_analyzed_documents_activity
- Analysis: analyze_document_activity
- Graph: relationships created within store_analyzed_document_activity
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


# =============================================================================
# Content Enrichment Activities
# =============================================================================


@activity.defn
async def fetch_article_content_activity(
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fetch full-text content for a batch of documents.

    For each document that is a candidate for enrichment (RSS with short
    content and a valid URL), fetches the article page and extracts the
    main text using trafilatura.

    Documents that already have substantial content, or that are from
    non-RSS sources, are passed through unchanged.

    Args:
        documents: List of RawDocument dicts.

    Returns:
        Dict with:
            - success: bool
            - documents: list of enriched RawDocument dicts
            - enriched_count: number of documents that were enriched
            - failed_count: number of documents where enrichment failed
            - error: optional error message
    """
    logger.info(f"fetch_article_content_activity: Processing {len(documents)} documents")

    try:
        from kubani.syndicates.news_digest.content_extraction import (
            enrich_document_content,
            fetch_article_content,
            should_enrich_document,
        )

        enriched_docs: list[dict[str, Any]] = []
        enriched_count = 0
        failed_count = 0

        for i, doc in enumerate(documents):
            if should_enrich_document(doc):
                url = doc.get("source_uri", "")
                try:
                    content = fetch_article_content(url)
                    enriched = enrich_document_content(doc, content)
                    enriched_docs.append(enriched)

                    if enriched.get("metadata", {}).get("content_enriched"):
                        enriched_count += 1
                    else:
                        failed_count += 1

                except Exception as e:
                    logger.warning(
                        f"fetch_article_content_activity: Failed to enrich "
                        f"{url}: {e}"
                    )
                    enriched_docs.append(doc)
                    failed_count += 1
            else:
                enriched_docs.append(doc)

            activity.heartbeat(f"Enriched {i + 1}/{len(documents)}")

        logger.info(
            f"fetch_article_content_activity: Enriched {enriched_count}, "
            f"failed {failed_count}, skipped {len(documents) - enriched_count - failed_count}"
        )

        return {
            "success": True,
            "documents": enriched_docs,
            "enriched_count": enriched_count,
            "failed_count": failed_count,
        }

    except Exception as e:
        logger.error(f"fetch_article_content_activity: Failed: {e}")
        return {
            "success": False,
            "documents": documents,  # Return originals on failure
            "enriched_count": 0,
            "failed_count": 0,
            "error": str(e),
        }


# =============================================================================
# Memory Client Factory
# =============================================================================


def _get_memory_client():
    """Get a Memory MCP client instance."""
    from kubani.framework.mcp import get_mcp_client

    return get_mcp_client()


# =============================================================================
# Deduplication Activities
# =============================================================================


@activity.defn
async def batch_check_duplicates_activity(
    dedup_keys: list[str],
) -> dict[str, Any]:
    """Check multiple deduplication keys in a single batch.

    For each key, checks the Memory MCP cache to determine if a document
    with that key has already been stored.

    Args:
        dedup_keys: List of dedup cache keys to check.

    Returns:
        Dict with:
            - success: bool
            - duplicates: dict mapping each key to True (exists) or False (new)
            - error: optional error message
    """
    logger.info(f"batch_check_duplicates_activity: Checking {len(dedup_keys)} keys")

    try:
        client = _get_memory_client()
        duplicates: dict[str, bool] = {}

        for key in dedup_keys:
            try:
                result = await client.memory.cache_get(key=key)
                duplicates[key] = result.get("found", False)
            except Exception:
                # On error, assume not a duplicate to avoid data loss
                duplicates[key] = False

            activity.heartbeat(f"Checked {len(duplicates)}/{len(dedup_keys)}")

        new_count = sum(1 for v in duplicates.values() if not v)
        logger.info(
            f"batch_check_duplicates_activity: {new_count} new, "
            f"{len(dedup_keys) - new_count} duplicates"
        )

        return {
            "success": True,
            "duplicates": duplicates,
        }

    except Exception as e:
        logger.error(f"batch_check_duplicates_activity: Failed: {e}")
        return {
            "success": False,
            "duplicates": {},
            "error": str(e),
        }


# =============================================================================
# Storage Activities
# =============================================================================


@activity.defn
async def store_raw_documents_activity(
    documents: list[dict[str, Any]],
    ttl_days: int = 14,
) -> dict[str, Any]:
    """Store a batch of raw documents in Memory MCP.

    For each document:
    1. Stores the content as a knowledge entry in Qdrant.
    2. Sets a cache key for deduplication with a TTL.

    Args:
        documents: List of RawDocument dicts (from RawDocument.to_dict()).
        ttl_days: Days to retain the dedup cache key.

    Returns:
        Dict with:
            - success: bool
            - stored_count: number of documents successfully stored
            - document_ids: list of stored document IDs
            - error: optional error message
    """
    logger.info(f"store_raw_documents_activity: Storing {len(documents)} documents")

    try:
        client = _get_memory_client()
        stored_ids: list[str] = []

        for doc in documents:
            try:
                source_type = doc.get("source_type", "rss")
                document_id = doc.get("document_id", "")
                topic = f"news/{source_type}/{document_id}"

                # Build content for knowledge storage
                content = doc.get("raw_content", "")
                if not content:
                    content = doc.get("title", "")

                # Store as knowledge entry
                await client.memory.store_knowledge(
                    topic=topic,
                    content=content,
                    source=doc.get("source_name", source_type),
                    related_topics=[f"source_type:{source_type}"],
                    metadata={
                        "document_id": document_id,
                        "source_type": source_type,
                        "source_uri": doc.get("source_uri", ""),
                        "content_hash": doc.get("content_hash", ""),
                        "title": doc.get("title", ""),
                        "author": doc.get("author"),
                        "published_at": doc.get("published_at"),
                        "retrieved_at": doc.get("retrieved_at", ""),
                        "stage": "raw",
                        **(doc.get("metadata", {})),
                    },
                )

                # Set dedup cache key
                from kubani.syndicates.news_digest.models import make_dedup_key

                dedup_key = make_dedup_key(source_type, doc.get("source_uri", ""))
                await client.memory.cache_set(
                    key=dedup_key,
                    value={
                        "document_id": document_id,
                        "stored_at": datetime.utcnow().isoformat(),
                    },
                    ttl_seconds=ttl_days * 86400,
                )

                stored_ids.append(document_id)
                activity.heartbeat(f"Stored {len(stored_ids)}/{len(documents)}")

            except Exception as e:
                logger.warning(
                    f"store_raw_documents_activity: Failed to store "
                    f"document {doc.get('document_id', '?')}: {e}"
                )

        logger.info(f"store_raw_documents_activity: Stored {len(stored_ids)} documents")

        return {
            "success": True,
            "stored_count": len(stored_ids),
            "document_ids": stored_ids,
        }

    except Exception as e:
        logger.error(f"store_raw_documents_activity: Failed: {e}")
        return {
            "success": False,
            "stored_count": 0,
            "document_ids": [],
            "error": str(e),
        }


@activity.defn
async def store_analyzed_document_activity(
    document: dict[str, Any],
) -> dict[str, Any]:
    """Store an analyzed document in Memory MCP with graph relationships.

    This activity:
    1. Stores the enriched document as a knowledge entry with analysis metadata.
    2. Creates graph relationships between the document, its entities, and topics.

    Args:
        document: An AnalyzedDocument dict (from AnalyzedDocument.to_dict()).

    Returns:
        Dict with:
            - success: bool
            - document_id: the stored document ID
            - relationships_created: number of graph relationships created
            - error: optional error message
    """
    document_id = document.get("document_id", "")
    logger.info(f"store_analyzed_document_activity: Storing analyzed doc {document_id}")

    try:
        client = _get_memory_client()

        source_type = document.get("source_type", "rss")
        topic = f"news/{source_type}/{document_id}"

        # Build enriched content
        title = document.get("title", "")
        summary = document.get("summary", "")
        content = f"{title}\n\n{summary}" if summary else title

        # Build related topics from entities and topics
        entities = document.get("entities", [])
        topics = document.get("topics", [])
        related = (
            [f"entity:{e}" for e in entities[:10]]
            + [f"topic:{t}" for t in topics[:10]]
            + [f"source_type:{source_type}"]
        )

        # Store as knowledge entry with analysis metadata
        await client.memory.store_knowledge(
            topic=topic,
            content=content,
            source=document.get("source_name", source_type),
            related_topics=related,
            metadata={
                "document_id": document_id,
                "source_type": source_type,
                "source_uri": document.get("source_uri", ""),
                "title": title,
                "summary": summary,
                "entities": entities,
                "topics": topics,
                "importance_score": document.get("importance_score", 5),
                "source_name": document.get("source_name", ""),
                "published_at": document.get("published_at"),
                "analyzed_at": document.get("analyzed_at", ""),
                "stage": "analyzed",
                **(document.get("metadata", {})),
            },
        )

        # Create graph relationships
        relationships_created = 0
        try:
            # Document → Entity relationships
            for entity in entities[:10]:
                await client.memory.create_relationship(
                    from_entity=topic,
                    to_entity=f"entity:{entity}",
                    relationship_type="MENTIONS",
                    properties={"source_type": source_type},
                )
                relationships_created += 1

            # Document → Topic relationships
            for t in topics[:10]:
                await client.memory.create_relationship(
                    from_entity=topic,
                    to_entity=f"topic:{t}",
                    relationship_type="DISCUSSES",
                    properties={"importance": document.get("importance_score", 5)},
                )
                relationships_created += 1

        except Exception as e:
            # Graph relationship creation is non-critical
            logger.warning(f"store_analyzed_document_activity: Graph error: {e}")

        # Update the dedup cache to mark as analyzed
        from kubani.syndicates.news_digest.models import make_dedup_key

        dedup_key = make_dedup_key(source_type, document.get("source_uri", ""))
        await client.memory.cache_set(
            key=dedup_key,
            value={
                "document_id": document_id,
                "stage": "analyzed",
                "analyzed_at": datetime.utcnow().isoformat(),
            },
            ttl_seconds=30 * 86400,  # 30 days
        )

        return {
            "success": True,
            "document_id": document_id,
            "relationships_created": relationships_created,
        }

    except Exception as e:
        logger.error(f"store_analyzed_document_activity: Failed: {e}")
        return {
            "success": False,
            "document_id": document_id,
            "relationships_created": 0,
            "error": str(e),
        }


# =============================================================================
# Query Activities
# =============================================================================


@activity.defn
async def query_analyzed_documents_activity(
    start_date: str | None = None,
    end_date: str | None = None,
    source_type: str | None = None,
    min_importance: int = 0,
    topics_filter: list[str] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Query analyzed documents from Memory MCP.

    Performs a semantic search for analyzed documents, then applies
    structured filters on the metadata.

    Args:
        start_date: ISO format start date for filtering.
        end_date: ISO format end date for filtering.
        source_type: Filter by source type (rss, arxiv, github).
        min_importance: Minimum importance score (1-10).
        topics_filter: Only include documents with these topics.
        limit: Maximum number of results.

    Returns:
        Dict with:
            - success: bool
            - documents: list of AnalyzedDocument dicts
            - count: number of results
            - error: optional error message
    """
    logger.info("query_analyzed_documents_activity: Querying analyzed documents")

    try:
        client = _get_memory_client()

        # Build semantic query
        query_parts = ["AI ML news articles research"]
        if source_type:
            query_parts.append(f"from {source_type}")
        if topics_filter:
            query_parts.append(f"about {', '.join(topics_filter[:5])}")

        query = " ".join(query_parts)

        # Over-fetch to account for post-filtering
        entries = await client.memory.query_knowledge(
            query=query,
            limit=limit * 3,
        )

        # Normalize entries
        if isinstance(entries, dict):
            entries = entries.get("entries", entries.get("knowledge", []))
        if not isinstance(entries, list):
            entries = []

        # Filter to analyzed news documents
        documents: list[dict[str, Any]] = []
        for entry in entries:
            metadata = entry.get("metadata", {})

            # Must be an analyzed document
            if metadata.get("stage") != "analyzed":
                continue

            # Source type filter
            if source_type and metadata.get("source_type") != source_type:
                continue

            # Importance filter
            importance = metadata.get("importance_score", 5)
            if importance < min_importance:
                continue

            # Date filtering
            published_at = metadata.get("published_at")
            if published_at and start_date:
                try:
                    from kubani.framework.temporal.memory import _parse_iso_date

                    pub_dt = _parse_iso_date(published_at)
                    start_dt = _parse_iso_date(start_date)
                    if pub_dt and start_dt and pub_dt < start_dt:
                        continue
                except Exception:
                    pass

            if published_at and end_date:
                try:
                    from kubani.framework.temporal.memory import _parse_iso_date

                    pub_dt = _parse_iso_date(published_at)
                    end_dt = _parse_iso_date(end_date)
                    if pub_dt and end_dt and pub_dt > end_dt:
                        continue
                except Exception:
                    pass

            # Topics filter
            if topics_filter:
                doc_topics = metadata.get("topics", [])
                if not any(t in doc_topics for t in topics_filter):
                    continue

            documents.append(
                {
                    "document_id": metadata.get("document_id", ""),
                    "source_type": metadata.get("source_type", "rss"),
                    "source_uri": metadata.get("source_uri", ""),
                    "title": metadata.get("title", entry.get("content", "").split("\n")[0]),
                    "summary": metadata.get("summary", ""),
                    "entities": metadata.get("entities", []),
                    "topics": metadata.get("topics", []),
                    "importance_score": importance,
                    "source_name": metadata.get("source_name", ""),
                    "published_at": published_at,
                    "analyzed_at": metadata.get("analyzed_at", ""),
                    "metadata": {
                        k: v
                        for k, v in metadata.items()
                        if k
                        not in {
                            "document_id",
                            "source_type",
                            "source_uri",
                            "title",
                            "summary",
                            "entities",
                            "topics",
                            "importance_score",
                            "source_name",
                            "published_at",
                            "analyzed_at",
                            "stage",
                        }
                    },
                }
            )

            if len(documents) >= limit:
                break

        # Sort by importance descending
        documents.sort(key=lambda d: d.get("importance_score", 0), reverse=True)

        logger.info(f"query_analyzed_documents_activity: Found {len(documents)} documents")

        return {
            "success": True,
            "documents": documents,
            "count": len(documents),
        }

    except Exception as e:
        logger.error(f"query_analyzed_documents_activity: Failed: {e}")
        return {
            "success": False,
            "documents": [],
            "count": 0,
            "error": str(e),
        }


# =============================================================================
# Analysis Activities
# =============================================================================


@activity.defn
async def analyze_document_activity(
    document: dict[str, Any],
) -> dict[str, Any]:
    """Analyze a raw document using the content-analyst agent.

    Extracts entities, classifies topics, rates importance, and generates
    a concise summary. Returns an AnalyzedDocument dict.

    Args:
        document: A RawDocument dict.

    Returns:
        Dict with:
            - success: bool
            - analyzed_document: AnalyzedDocument dict
            - error: optional error message
    """
    document_id = document.get("document_id", "")
    title = document.get("title", "")
    logger.info(f"analyze_document_activity: Analyzing '{title}' ({document_id})")

    try:
        from kubani.framework.temporal.activities import _get_agent

        agent = _get_agent("content-analyst")
        activity.heartbeat(f"Analyzing document: {title[:50]}")

        source_type = document.get("source_type", "rss")
        raw_content = document.get("raw_content", "")
        content_enriched = document.get("metadata", {}).get("content_enriched", False)

        # Use more content when full-text is available
        content_limit = 6000 if content_enriched else 2000
        content_snippet = raw_content[:content_limit]

        prompt = f"""Analyze this {source_type} document and return a JSON object.

Title: {title}
Content ({len(raw_content)} chars total, showing first {len(content_snippet)}):
{content_snippet}

Return ONLY a valid JSON object (no markdown fences, no explanation):
{{
    "summary": "<2-3 sentence summary capturing the key facts and significance>",
    "entities": ["<NAMED entities only — see rules below>"],
    "topics": ["<topic classifications — see rules below>"],
    "importance_score": <integer 1-10>
}}

ENTITY RULES (strict):
- Include ONLY proper nouns: specific people, companies, products, or named technologies.
- Examples of VALID entities: "OpenAI", "GPT-4", "Elon Musk", "PyTorch", "Google DeepMind"
- Examples of INVALID entities: "AI models", "machine learning", "neural networks", "researchers"
  (these are topics, not entities)
- If no specific named entities are mentioned, return an empty list.
- Maximum 10 entities.

TOPIC RULES (strict):
- Topics are broad thematic categories, NOT named entities.
- Use consistent, lowercase labels from this taxonomy when applicable:
  "large language models", "computer vision", "reinforcement learning",
  "natural language processing", "robotics", "ai safety", "ai regulation",
  "open source", "cloud computing", "developer tools", "funding",
  "semiconductor", "autonomous systems", "healthcare ai", "ai research"
- You may add 1-2 custom topics if none of the above fit.
- Return 2-5 topics.

IMPORTANCE SCORING:
- 9-10: Major product launches, breakthrough research, significant regulatory changes
- 7-8: Notable company updates, important tool releases, significant findings
- 5-6: Interesting but not critical news, minor updates
- 3-4: Routine updates, minor announcements
- 1-2: Low relevance, listicles, or duplicate information
- If the content is too short or vague to assess, score 3."""

        result = await agent.run(prompt)

        from kubani.syndicates.news_digest.models import parse_json_object_from_text

        analysis = parse_json_object_from_text(result)

        analyzed_doc = {
            "document_id": document_id,
            "source_type": source_type,
            "source_uri": document.get("source_uri", ""),
            "title": title,
            "summary": analysis.get("summary", raw_content[:200]),
            "entities": analysis.get("entities", []),
            "topics": analysis.get("topics", []),
            "importance_score": min(10, max(1, int(analysis.get("importance_score", 5)))),
            "source_name": document.get("source_name", ""),
            "published_at": document.get("published_at"),
            "analyzed_at": datetime.utcnow().isoformat(),
            "metadata": document.get("metadata", {}),
        }

        return {
            "success": True,
            "analyzed_document": analyzed_doc,
        }

    except Exception as e:
        logger.error(f"analyze_document_activity: Failed for {document_id}: {e}")
        # Return a minimal analyzed document on failure
        return {
            "success": False,
            "analyzed_document": {
                "document_id": document_id,
                "source_type": document.get("source_type", "rss"),
                "source_uri": document.get("source_uri", ""),
                "title": document.get("title", ""),
                "summary": document.get("raw_content", "")[:200],
                "entities": [],
                "topics": [],
                "importance_score": 5,
                "source_name": document.get("source_name", ""),
                "published_at": document.get("published_at"),
                "analyzed_at": datetime.utcnow().isoformat(),
                "metadata": document.get("metadata", {}),
            },
            "error": str(e),
        }
