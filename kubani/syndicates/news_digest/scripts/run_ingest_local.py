#!/usr/bin/env python3
"""Local runner for the ingest pipeline — no Temporal required.

This script demonstrates how to run the full ingest pipeline locally
using the ``LocalContext`` with mock data. It is useful for:

- Rapid iteration on pipeline logic
- Debugging data transformations
- Inspecting intermediate outputs at each stage
- Testing with custom fixture data

Usage::

    python -m kubani.syndicates.news_digest.scripts.run_ingest_local
    python -m kubani.syndicates.news_digest.scripts.run_ingest_local --source rss
    python -m kubani.syndicates.news_digest.scripts.run_ingest_local --source arxiv
    python -m kubani.syndicates.news_digest.scripts.run_ingest_local --source github
    python -m kubani.syndicates.news_digest.scripts.run_ingest_local --source rss --with-duplicates
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

# Ensure the project root is importable
sys.path.insert(0, ".")

from kubani.syndicates.news_digest.models import (
    raw_document_from_arxiv_paper,
    raw_document_from_github_repo,
    raw_document_from_rss_entry,
)
from kubani.syndicates.news_digest.pipeline import run_ingest_pipeline
from kubani.syndicates.news_digest.pipeline.contexts.local_context import LocalContext


# =============================================================================
# Mock Data Fixtures
# =============================================================================


def make_rss_fixtures() -> list[dict[str, Any]]:
    """Generate mock RSS feed entries."""
    entries = [
        {
            "title": "OpenAI Releases GPT-5 with Reasoning Capabilities",
            "url": "https://example.com/gpt5-release",
            "source": "TechCrunch",
            "published_date": "2026-02-28T10:00:00Z",
            "summary": "OpenAI has released GPT-5, featuring advanced reasoning.",
            "author": "Jane Smith",
            "source_category": "ai_labs",
        },
        {
            "title": "Google DeepMind Achieves Breakthrough in Protein Folding",
            "url": "https://example.com/deepmind-protein",
            "source": "Nature",
            "published_date": "2026-02-28T08:00:00Z",
            "summary": "DeepMind's latest model predicts protein structures with 99% accuracy.",
            "author": "John Doe",
            "source_category": "research",
        },
        {
            "title": "Anthropic Introduces Constitutional AI v2",
            "url": "https://example.com/anthropic-cai-v2",
            "source": "The Verge",
            "published_date": "2026-02-27T14:00:00Z",
            "summary": "Anthropic's new approach to AI safety shows promising results.",
            "author": "Alice Johnson",
            "source_category": "ai_labs",
        },
    ]
    return [raw_document_from_rss_entry(e).to_dict() for e in entries]


def make_arxiv_fixtures() -> list[dict[str, Any]]:
    """Generate mock arXiv paper entries."""
    papers = [
        {
            "arxiv_id": "2602.00001",
            "title": "Scaling Laws for Mixture-of-Experts Models",
            "authors": ["Alice Researcher", "Bob Scientist"],
            "abstract": "We study scaling laws for MoE architectures...",
            "categories": ["cs.LG", "cs.AI"],
            "published_at": "2026-02-28",
        },
        {
            "arxiv_id": "2602.00002",
            "title": "Efficient Fine-Tuning with Sparse Adapters",
            "authors": ["Carol Expert"],
            "abstract": "We propose a new method for parameter-efficient fine-tuning...",
            "categories": ["cs.CL", "cs.LG"],
            "published_at": "2026-02-27",
        },
    ]
    return [raw_document_from_arxiv_paper(p).to_dict() for p in papers]


def make_github_fixtures() -> list[dict[str, Any]]:
    """Generate mock GitHub repo entries."""
    repos = [
        {
            "repo_url": "https://github.com/example/awesome-llm",
            "name": "awesome-llm",
            "description": "A curated list of LLM resources and tools",
            "stars": 15000,
            "language": "Python",
            "topics": ["llm", "ai", "machine-learning"],
            "forks": 2000,
            "trending_score": 0.95,
        },
        {
            "repo_url": "https://github.com/example/fast-inference",
            "name": "fast-inference",
            "description": "High-performance inference engine for transformer models",
            "stars": 8000,
            "language": "Rust",
            "topics": ["inference", "transformers", "performance"],
            "forks": 500,
            "trending_score": 0.82,
        },
    ]
    return [raw_document_from_github_repo(r).to_dict() for r in repos]


FIXTURE_MAP = {
    "rss": make_rss_fixtures,
    "arxiv": make_arxiv_fixtures,
    "github": make_github_fixtures,
}


# =============================================================================
# Mock Callables
# =============================================================================


def make_fetcher(
    source_type: str,
) -> Any:
    """Create a mock fetcher that returns fixture data."""

    async def fetcher(src_type: str, **kwargs: Any) -> list[dict[str, Any]]:
        fixture_fn = FIXTURE_MAP.get(src_type)
        if fixture_fn is None:
            raise ValueError(f"No fixtures for source type: {src_type}")
        docs = fixture_fn()
        print(f"\n  [fetcher] Returning {len(docs)} {src_type} documents")
        return docs

    return fetcher


def make_duplicate_checker(
    duplicate_uris: set[str] | None = None,
) -> Any:
    """Create a mock duplicate checker.

    Args:
        duplicate_uris: Set of source_uri values to treat as duplicates.
            If None, all documents are treated as new.
    """
    from kubani.syndicates.news_digest.models import make_dedup_key

    # Pre-compute dedup keys for known duplicates
    known_keys: set[str] = set()
    if duplicate_uris:
        for uri in duplicate_uris:
            # Try each source type since we don't know which one
            for st in ("rss", "arxiv", "github"):
                known_keys.add(make_dedup_key(st, uri))

    async def checker(dedup_keys: list[str]) -> dict[str, bool]:
        result = {key: key in known_keys for key in dedup_keys}
        dup_count = sum(1 for v in result.values() if v)
        print(f"  [dedup] Checked {len(dedup_keys)} keys: {dup_count} duplicates")
        return result

    return checker


def make_storer() -> Any:
    """Create a mock storer that logs documents and returns the count."""
    stored_docs: list[dict[str, Any]] = []

    async def storer(documents: list[dict[str, Any]]) -> int:
        stored_docs.extend(documents)
        print(f"  [storer] Stored {len(documents)} documents:")
        for doc in documents:
            print(f"    - [{doc.get('source_type')}] {doc.get('title', 'untitled')}")
        return len(documents)

    storer._stored_docs = stored_docs  # type: ignore[attr-defined]
    return storer


def make_analysis_trigger() -> Any:
    """Create a mock analysis trigger."""

    async def trigger(documents: list[dict[str, Any]], source_type: str) -> None:
        print(f"  [trigger] Would trigger analysis for {len(documents)} {source_type} docs")

    return trigger


# =============================================================================
# Main
# =============================================================================


async def run(source_type: str, with_duplicates: bool = False) -> None:
    """Run the ingest pipeline locally with mock data."""
    print(f"\n{'=' * 60}")
    print(f"  Running {source_type.upper()} ingest pipeline (local)")
    print(f"{'=' * 60}\n")

    # Set up duplicate URIs if requested
    duplicate_uris: set[str] | None = None
    if with_duplicates:
        if source_type == "rss":
            duplicate_uris = {"https://example.com/gpt5-release"}
        elif source_type == "arxiv":
            duplicate_uris = {"arxiv:2602.00001"}
        elif source_type == "github":
            duplicate_uris = {"https://github.com/example/awesome-llm"}

    ctx = LocalContext(
        fetcher=make_fetcher(source_type),
        duplicate_checker=make_duplicate_checker(duplicate_uris),
        storer=make_storer(),
        analysis_trigger=make_analysis_trigger(),
        verbose=True,
    )

    result = await run_ingest_pipeline(ctx, source_type)

    # Print summary
    ctx.print_summary()
    print(f"\nResult: {json.dumps(result.to_dict(), indent=2)}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run the ingest pipeline locally with mock data."
    )
    parser.add_argument(
        "--source",
        choices=["rss", "arxiv", "github"],
        default="rss",
        help="Source type to ingest (default: rss)",
    )
    parser.add_argument(
        "--with-duplicates",
        action="store_true",
        help="Simulate some documents being duplicates",
    )
    args = parser.parse_args()

    asyncio.run(run(args.source, args.with_duplicates))


if __name__ == "__main__":
    main()
