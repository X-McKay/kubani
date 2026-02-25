"""
UI Event Publishing Helpers.

Provides functions for syndicates and agents to publish events to the UI
activity feed and approval queue via Redis Streams.

Usage:
    from kubani.framework.ui_events import publish_activity, publish_approval

    # Publish an activity event
    await publish_activity(
        source="news-digest",
        event_type="syndicate_output",
        title="Daily AI News Digest — January 28, 2026",
        content=digest_markdown,
        severity="info",
        metadata={"articles_processed": 12},
    )

    # Publish an approval request
    await publish_approval(
        approval_type="skill_proposal",
        source="learning-system/skill-synthesizer",
        title="New Skill: pod-restart-diagnostics",
        summary="Analyzes pod restart patterns...",
        spec=skill_yaml,
        metadata={"confidence": 0.85},
    )
"""

import json
import logging
from typing import Literal

import redis.asyncio as redis

from kubani.framework.config import get_config

logger = logging.getLogger(__name__)

ACTIVITY_STREAM = "kubani:activity"
APPROVALS_STREAM = "kubani:approvals"


async def publish_activity(
    source: str,
    event_type: str,
    title: str,
    content: str = "",
    severity: Literal["info", "warning", "error", "success"] = "info",
    metadata: dict | None = None,
    redis_url: str | None = None,
) -> str:
    """Publish an activity event to the UI feed.

    Args:
        source: Syndicate/agent name (e.g., 'news-digest', 'k8s-monitor')
        event_type: Event category. Common types:
            - 'syndicate_output': Output from a syndicate workflow
            - 'agent_activity': Agent action or decision
            - 'alert': Warning or critical notification
            - 'workflow': Temporal workflow status
            - 'learning': Learning system insight
            - 'system': System-level event
        title: Short title for the feed card
        content: Rich markdown content for detail view
        severity: Event severity level
        metadata: Additional structured data (will be JSON serialized)
        redis_url: Optional Redis URL override. When provided, uses this
            URL directly instead of get_config().memory.redis.url.
            Useful in containers that set REDIS_URL but not REDIS_HOST/PORT.

    Returns:
        Redis stream entry ID
    """
    if redis_url is None:
        config = get_config()
        redis_url = config.memory.redis.url

    r = redis.from_url(redis_url)

    try:
        entry = {
            "source": source,
            "type": event_type,
            "title": title,
            "content": content,
            "severity": severity,
            "metadata": json.dumps(metadata or {}),
        }

        entry_id = await r.xadd(ACTIVITY_STREAM, entry)
        logger.debug(f"Published activity event {entry_id}: {title}")
        return entry_id.decode() if isinstance(entry_id, bytes) else entry_id
    finally:
        await r.aclose()


async def publish_approval(
    approval_type: str,
    source: str,
    title: str,
    summary: str,
    spec: str = "",
    metadata: dict | None = None,
    redis_url: str | None = None,
) -> str:
    """Publish an approval request to the UI.

    Args:
        approval_type: Type of approval request. Common types:
            - 'skill_proposal': New skill from learning system
            - 'agent_proposal': New agent configuration
            - 'action_request': Action requiring human approval
        source: Origin (e.g., 'learning-system/skill-synthesizer')
        title: Short title for the approval card
        summary: Brief description shown in the approval list
        spec: Full specification (YAML, markdown, etc.) for detail view
        metadata: Structured data (confidence scores, triggers, etc.)
        redis_url: Optional Redis URL override. When provided, uses this
            URL directly instead of get_config().memory.redis.url.

    Returns:
        Redis stream entry ID
    """
    if redis_url is None:
        config = get_config()
        redis_url = config.memory.redis.url

    r = redis.from_url(redis_url)

    try:
        entry = {
            "type": approval_type,
            "source": source,
            "title": title,
            "summary": summary,
            "spec": spec,
            "metadata": json.dumps(metadata or {}),
        }

        entry_id = await r.xadd(APPROVALS_STREAM, entry)
        logger.debug(f"Published approval request {entry_id}: {title}")
        return entry_id.decode() if isinstance(entry_id, bytes) else entry_id
    finally:
        await r.aclose()
