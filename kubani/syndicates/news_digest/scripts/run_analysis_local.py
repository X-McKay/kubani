"""Local analysis runner — test the analysis pipeline without Temporal.

This script allows you to:
1. Fetch real RSS articles, enrich them with full text, and run analysis locally.
2. Load previously ingested documents from a JSON file and re-run analysis.
3. Iterate on the analysis prompt and inspect outputs without deploying.

The script uses the OpenAI-compatible API (configured via OPENAI_API_KEY env var)
to call the LLM directly, bypassing the agent framework. This makes it easy
to test prompt changes in isolation.

Usage::

    # Mode 1: Fetch live RSS articles, enrich, and analyze
    python -m kubani.syndicates.news_digest.scripts.run_analysis_local --mode live

    # Mode 2: Load documents from a JSON file and re-analyze
    python -m kubani.syndicates.news_digest.scripts.run_analysis_local --mode file --input docs.json

    # Mode 3: Analyze a single URL
    python -m kubani.syndicates.news_digest.scripts.run_analysis_local --mode url --url https://example.com/article

    # Save outputs for comparison
    python -m kubani.syndicates.news_digest.scripts.run_analysis_local --mode live --output results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any

# Ensure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from kubani.syndicates.news_digest.content_extraction import (
    enrich_document_content,
    fetch_article_content,
    should_enrich_document,
)
from kubani.syndicates.news_digest.models import (
    RawDocument,
    parse_json_object_from_text,
    raw_document_from_rss_entry,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# =============================================================================
# LLM Analysis (standalone, no agent framework)
# =============================================================================


def build_analysis_prompt(document: dict[str, Any]) -> str:
    """Build the analysis prompt for a document.

    This is the same prompt used in ``analyze_document_activity``,
    extracted here so it can be iterated on locally.

    Args:
        document: A RawDocument dict.

    Returns:
        The prompt string.
    """
    title = document.get("title", "")
    source_type = document.get("source_type", "rss")
    raw_content = document.get("raw_content", "")
    content_enriched = document.get("metadata", {}).get("content_enriched", False)

    content_limit = 6000 if content_enriched else 2000
    content_snippet = raw_content[:content_limit]

    return f"""Analyze this {source_type} document and return a JSON object.

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


async def analyze_document_local(
    document: dict[str, Any],
    model: str = "gpt-4.1-mini",
) -> dict[str, Any]:
    """Analyze a document using the OpenAI-compatible API directly.

    Args:
        document: A RawDocument dict.
        model: The model to use for analysis.

    Returns:
        An AnalyzedDocument dict.
    """
    try:
        from openai import OpenAI

        client = OpenAI()

        prompt = build_analysis_prompt(document)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise content analyst. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1000,
        )

        result_text = response.choices[0].message.content or ""
        analysis = parse_json_object_from_text(result_text)

        return {
            "document_id": document.get("document_id", ""),
            "source_type": document.get("source_type", "rss"),
            "source_uri": document.get("source_uri", ""),
            "title": document.get("title", ""),
            "summary": analysis.get("summary", ""),
            "entities": analysis.get("entities", []),
            "topics": analysis.get("topics", []),
            "importance_score": min(10, max(1, int(analysis.get("importance_score", 5)))),
            "source_name": document.get("source_name", ""),
            "published_at": document.get("published_at"),
            "analyzed_at": datetime.utcnow().isoformat(),
            "metadata": {
                **document.get("metadata", {}),
                "model_used": model,
                "content_length_analyzed": len(document.get("raw_content", "")),
            },
            "_raw_llm_response": result_text,
        }

    except Exception as e:
        logger.error(f"Analysis failed for '{document.get('title', '?')}': {e}")
        return {
            "document_id": document.get("document_id", ""),
            "title": document.get("title", ""),
            "error": str(e),
        }


# =============================================================================
# Document Sources
# =============================================================================


def fetch_sample_rss_documents() -> list[dict[str, Any]]:
    """Fetch a small set of real RSS articles for testing.

    Uses feedparser to grab a few articles from well-known AI/tech feeds.
    """
    try:
        import feedparser
    except ImportError:
        logger.error("feedparser not installed. Run: pip install feedparser")
        return _get_hardcoded_sample_documents()

    feeds = [
        "https://news.ycombinator.com/rss",
        "https://feeds.arstechnica.com/arstechnica/technology-lab",
    ]

    documents = []
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:  # 3 per feed
                doc = raw_document_from_rss_entry(
                    {
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "summary": entry.get("summary", ""),
                        "author": entry.get("author", ""),
                        "published_date": entry.get("published", ""),
                        "source": feed_url,
                    },
                    source_name=feed_url.split("/")[2],
                )
                documents.append(doc.to_dict())
        except Exception as e:
            logger.warning(f"Failed to fetch {feed_url}: {e}")

    return documents


def _get_hardcoded_sample_documents() -> list[dict[str, Any]]:
    """Return hardcoded sample documents when feedparser is unavailable."""
    return [
        raw_document_from_rss_entry(
            {
                "title": "OpenAI Announces GPT-5 with Improved Reasoning",
                "url": "https://example.com/gpt5-announcement",
                "summary": "OpenAI has released GPT-5, featuring significant improvements in reasoning and code generation.",
                "source": "TechNews",
            },
            source_name="TechNews",
        ).to_dict(),
        raw_document_from_rss_entry(
            {
                "title": "Google DeepMind Publishes New Robotics Research",
                "url": "https://example.com/deepmind-robotics",
                "summary": "DeepMind researchers demonstrate new approach to robot manipulation.",
                "source": "AI Weekly",
            },
            source_name="AI Weekly",
        ).to_dict(),
    ]


def document_from_url(url: str) -> dict[str, Any]:
    """Create a RawDocument from a URL by fetching its content."""
    content = fetch_article_content(url)
    if not content:
        logger.warning(f"Could not fetch content from {url}")
        content = "(content fetch failed)"

    doc = RawDocument(
        document_id=f"local-{hash(url) % 10000:04d}",
        source_type="rss",
        source_uri=url,
        content_hash="",
        title=url.split("/")[-1].replace("-", " ").title(),
        raw_content=content,
        source_name="local",
        retrieved_at=datetime.utcnow().isoformat(),
        metadata={"content_enriched": True, "enriched_content_length": len(content)},
    )
    return doc.to_dict()


# =============================================================================
# Enrichment
# =============================================================================


def enrich_documents_locally(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enrich documents with full-text content using trafilatura."""
    enriched = []
    for doc in documents:
        if should_enrich_document(doc):
            url = doc.get("source_uri", "")
            logger.info(f"  Fetching full text: {url}")
            content = fetch_article_content(url)
            doc = enrich_document_content(doc, content)
            was_enriched = doc.get("metadata", {}).get("content_enriched", False)
            logger.info(
                f"    → {'Enriched' if was_enriched else 'Kept original'} "
                f"({len(doc.get('raw_content', ''))} chars)"
            )
        enriched.append(doc)
    return enriched


# =============================================================================
# Display
# =============================================================================


def print_analysis_result(result: dict[str, Any], index: int) -> None:
    """Pretty-print an analysis result."""
    print(f"\n{'='*70}")
    print(f"Document {index + 1}: {result.get('title', '?')}")
    print(f"{'='*70}")

    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return

    print(f"  Source:     {result.get('source_type', '?')} / {result.get('source_name', '?')}")
    print(f"  URI:        {result.get('source_uri', '?')}")
    print(f"  Score:      {result.get('importance_score', '?')}/10")
    print(f"  Entities:   {result.get('entities', [])}")
    print(f"  Topics:     {result.get('topics', [])}")
    print(f"  Summary:    {result.get('summary', '(none)')}")

    content_len = result.get("metadata", {}).get("content_length_analyzed", 0)
    enriched = result.get("metadata", {}).get("content_enriched", False)
    print(f"  Content:    {content_len} chars {'(enriched)' if enriched else '(snippet only)'}")


# =============================================================================
# Main
# =============================================================================


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local analysis runner for news_digest pipeline",
    )
    parser.add_argument(
        "--mode",
        choices=["live", "file", "url"],
        default="live",
        help="Document source: 'live' (fetch RSS), 'file' (load JSON), 'url' (single URL)",
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to JSON file with documents (for --mode file)",
    )
    parser.add_argument(
        "--url",
        type=str,
        help="URL to analyze (for --mode url)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Path to save analysis results as JSON",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4.1-mini",
        help="LLM model to use for analysis (default: gpt-4.1-mini)",
    )
    parser.add_argument(
        "--skip-enrich",
        action="store_true",
        help="Skip full-text enrichment (analyze snippets only)",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=5,
        help="Maximum number of documents to analyze (default: 5)",
    )

    args = parser.parse_args()

    # Load documents
    print("\n" + "=" * 70)
    print("NEWS DIGEST — Local Analysis Runner")
    print("=" * 70)

    if args.mode == "file":
        if not args.input:
            print("ERROR: --input required for --mode file")
            sys.exit(1)
        with open(args.input) as f:
            documents = json.load(f)
        print(f"\nLoaded {len(documents)} documents from {args.input}")

    elif args.mode == "url":
        if not args.url:
            print("ERROR: --url required for --mode url")
            sys.exit(1)
        print(f"\nFetching content from: {args.url}")
        documents = [document_from_url(args.url)]

    else:  # live
        print("\nFetching live RSS articles...")
        documents = fetch_sample_rss_documents()
        print(f"Fetched {len(documents)} articles")

    # Cap documents
    documents = documents[: args.max_docs]

    # Enrich
    if not args.skip_enrich and args.mode != "url":
        print(f"\nEnriching {len(documents)} documents with full-text content...")
        documents = enrich_documents_locally(documents)

    # Analyze
    print(f"\nAnalyzing {len(documents)} documents with {args.model}...")
    results = []
    for i, doc in enumerate(documents):
        title = doc.get("title", "?")[:50]
        print(f"\n  [{i + 1}/{len(documents)}] Analyzing: {title}...")
        result = await analyze_document_local(doc, model=args.model)
        results.append(result)
        print_analysis_result(result, i)

    # Save results
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    successful = [r for r in results if "error" not in r]
    print(f"  Analyzed:    {len(successful)}/{len(documents)}")
    if successful:
        avg_score = sum(r.get("importance_score", 0) for r in successful) / len(successful)
        print(f"  Avg score:   {avg_score:.1f}/10")
        all_entities = [e for r in successful for e in r.get("entities", [])]
        all_topics = [t for r in successful for t in r.get("topics", [])]
        print(f"  Entities:    {len(set(all_entities))} unique")
        print(f"  Topics:      {len(set(all_topics))} unique")
        enriched = sum(
            1 for r in successful if r.get("metadata", {}).get("content_enriched")
        )
        print(f"  Enriched:    {enriched}/{len(successful)}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
