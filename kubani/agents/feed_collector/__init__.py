"""
Feed Collector Agent - Collects content from data feeds.

Usage:
    from agents.feed_collector import FeedCollectorAgent

    agent = FeedCollectorAgent()
    result = await agent.collect()
"""

from agents.feed_collector.agent import (
    CollectionResult,
    FeedCollectorAgent,
    RawArticle,
)

__all__ = [
    "FeedCollectorAgent",
    "CollectionResult",
    "RawArticle",
]
