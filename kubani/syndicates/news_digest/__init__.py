"""
News Digest Syndicate - AI news collection and publishing.

Orchestrates article collection, analysis, and digest publishing.

Usage:
    from syndicates.news_digest import NewsDigestSyndicate

    syndicate = NewsDigestSyndicate()
    await syndicate.start()
"""

from .syndicate import NewsDigestSyndicate

__all__ = ["NewsDigestSyndicate"]
