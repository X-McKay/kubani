"""News Digest Syndicate Workflows.

This module contains the Temporal workflows for the News Digest syndicate,
organized as a three-stage pipeline:

Stage 1 — Ingest (source-specific, independently scheduled):
    - RSSIngestWorkflow: Collect articles from RSS feeds (every 15-30 min)
    - ArxivIngestWorkflow: Collect papers from arXiv (every 2-4 hours)
    - GitHubIngestWorkflow: Collect trending repos from GitHub (every 6-12 hours)

Stage 2 — Analyze (triggered after each ingest):
    - AnalyzeDocumentWorkflow: Entity extraction, topic classification,
      importance scoring, and graph relationship creation.

Stage 3 — Digest (scheduled 2x/day):
    - NewsDigestWorkflow: Query analyzed documents, compose, and publish
      a structured digest to Discord.

Usage:
    # Register workflows with worker
    worker = Worker(
        client,
        task_queue="news-digest",
        workflows=[
            RSSIngestWorkflow,
            ArxivIngestWorkflow,
            GitHubIngestWorkflow,
            AnalyzeDocumentWorkflow,
            NewsDigestWorkflow,
        ],
        activities=[...],
    )
"""

from .analyze import AnalyzeDocumentWorkflow
from .digest import NewsDigestWorkflow
from .ingest_arxiv import ArxivIngestWorkflow
from .ingest_github import GitHubIngestWorkflow
from .ingest_rss import RSSIngestWorkflow

__all__ = [
    # Stage 1: Ingest
    "RSSIngestWorkflow",
    "ArxivIngestWorkflow",
    "GitHubIngestWorkflow",
    # Stage 2: Analyze
    "AnalyzeDocumentWorkflow",
    # Stage 3: Digest
    "NewsDigestWorkflow",
]
