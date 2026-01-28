"""
News Digest Syndicate - AI news collection and publishing.

Orchestrates article collection, analysis, and digest publishing through
Temporal workflows. Uses dedicated namespace 'news-digest' for isolation.

Workflows:
    NewsCollectionWorkflow: Collect articles from multiple sources
    NewsDigestWorkflow: Compose and publish news digests

Usage:
    # Start the worker
    news-digest-worker

    # Or programmatically
    from kubani.syndicates.news_digest.workflows import (
        NewsCollectionWorkflow,
        NewsDigestWorkflow,
    )
"""

from .workflows import NewsCollectionWorkflow, NewsDigestWorkflow

__all__ = ["NewsCollectionWorkflow", "NewsDigestWorkflow"]
