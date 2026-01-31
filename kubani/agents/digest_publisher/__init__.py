"""
Digest Publisher Agent - Skills-centric digest composition and publishing.

Usage:
    from kubani.agents.digest_publisher import DigestPublisherAgent

    agent = DigestPublisherAgent()
    result = await agent.compose_and_publish(articles, trends)
"""

from .agent import (
    DigestPublisherAgent,
    ExecutiveDigest,
    NewsDigest,
    PublishResult,
)

__all__ = [
    "DigestPublisherAgent",
    "ExecutiveDigest",
    "NewsDigest",
    "PublishResult",
]
