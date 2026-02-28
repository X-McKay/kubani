"""
News Digest Syndicate — Three-stage AI news pipeline.

This package provides the deployable News Digest syndicate which
orchestrates a three-stage pipeline: Ingest → Analyze → Digest.

Usage:
    # As a script
    news-digest-worker

    # Programmatically
    from news_digest_syndicate import (
        RSSIngestWorkflow,
        ArxivIngestWorkflow,
        GitHubIngestWorkflow,
        AnalyzeDocumentWorkflow,
        NewsDigestWorkflow,
    )
"""

# Re-export workflows from the framework's syndicate module
from kubani.syndicates.news_digest import (
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
__version__ = "2.0.0"
