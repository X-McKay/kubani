"""News Digest Syndicate Workflows.

This module contains the Temporal workflows for the News Digest syndicate:

- NewsCollectionWorkflow: Continuous ambient collection (every 30 min)
  Collects articles and stores them in Memory MCP for later digest composition.
  Detects breaking news for immediate notification.

- NewsDigestWorkflow: Scheduled digest composition (2x/day)
  Queries collected articles from Memory MCP, analyzes trends,
  and publishes executive digests to Discord.

Usage:
    # Register workflows with worker
    worker = Worker(
        client,
        task_queue="news-digest",
        workflows=[NewsCollectionWorkflow, NewsDigestWorkflow],
        activities=[...],
    )
"""

from .collection import NewsCollectionWorkflow
from .digest import NewsDigestWorkflow

__all__ = [
    "NewsCollectionWorkflow",
    "NewsDigestWorkflow",
]
