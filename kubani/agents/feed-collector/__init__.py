"""
Feed Collector Agent - Collects content from data feeds.

Usage:
    from kubani.agents.feed_collector import FeedCollectorAgent

    agent = FeedCollectorAgent()
    result = await agent.collect()
"""

from kubani.agents.feed_collector.agent import (
    CollectionResult,
    FeedCollectorAgent,
    RawArticle,
)

__all__ = [
    "FeedCollectorAgent",
    "CollectionResult",
    "RawArticle",
]
