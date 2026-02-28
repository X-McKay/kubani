"""
News Digest Syndicate — AI news collection, analysis, and publishing.

Orchestrates a three-stage pipeline through Temporal workflows:

Stage 1 — Ingest:
    RSSIngestWorkflow: Collect articles from RSS feeds
    ArxivIngestWorkflow: Collect papers from arXiv
    GitHubIngestWorkflow: Collect trending repos from GitHub

Stage 2 — Analyze:
    AnalyzeDocumentWorkflow: Entity extraction, topic classification,
    importance scoring, and graph relationship creation

Stage 3 — Digest:
    NewsDigestWorkflow: Compose and publish news digests to Discord

Uses dedicated Temporal namespace 'news-digest' for isolation.

Usage:
    # Start the worker
    news-digest-worker

    # Or programmatically
    from kubani.syndicates.news_digest.workflows import (
        RSSIngestWorkflow,
        ArxivIngestWorkflow,
        GitHubIngestWorkflow,
        AnalyzeDocumentWorkflow,
        NewsDigestWorkflow,
    )
"""

from .workflows import (
    AnalyzeDocumentWorkflow,
    ArxivIngestWorkflow,
    GitHubIngestWorkflow,
    NewsDigestWorkflow,
    RSSIngestWorkflow,
)

__all__ = [
    "RSSIngestWorkflow",
    "ArxivIngestWorkflow",
    "GitHubIngestWorkflow",
    "AnalyzeDocumentWorkflow",
    "NewsDigestWorkflow",
]
