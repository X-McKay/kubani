"""
News Digest Syndicate - News aggregation and digest generation.

This package provides the deployable News Digest syndicate which
orchestrates feed collection, content analysis, and digest publishing.

Usage:
    # As a script
    news-digest-worker

    # Programmatically
    from news_digest_syndicate import NewsDigestSyndicate

    syndicate = NewsDigestSyndicate()
    await syndicate.start()
"""

# Re-export from the framework's syndicate module
from kubani.syndicates.news_digest import NewsDigestSyndicate

__all__ = ["NewsDigestSyndicate"]
__version__ = "0.2.0"
