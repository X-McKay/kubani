"""
Digest Publisher Agent - Composes and publishes digests.

Usage:
    from agents.digest_publisher import DigestPublisherAgent

    agent = DigestPublisherAgent()
    result = await agent.compose_and_publish(articles, trends)
"""

from agents.digest_publisher.agent import DigestPublisherAgent, PublishResult

__all__ = ["DigestPublisherAgent", "PublishResult"]
