"""
News Digest Syndicate - News aggregation and digest generation.

This package provides the deployable News Digest syndicate which
orchestrates feed collection, content analysis, and digest publishing.

Usage:
    # As a script
    news-digest-worker

    # Programmatically
    from news_digest_syndicate import NewsCollectionWorkflow, NewsDigestWorkflow
"""

# Re-export workflows from the framework's syndicate module
from kubani.syndicates.news_digest import NewsCollectionWorkflow, NewsDigestWorkflow

__all__ = ["NewsCollectionWorkflow", "NewsDigestWorkflow"]
__version__ = "0.2.0"
