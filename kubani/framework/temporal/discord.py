"""Discord MCP integration for Temporal workflows.

This module provides Temporal activities for Discord notifications,
specifically designed for breaking news alerts and digest publishing.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


def _get_mcp_client():
    """Get MCP client for Discord operations."""
    from kubani.framework.mcp import get_mcp_client

    return get_mcp_client()


def _format_breaking_news_embed(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Format breaking news articles as a Discord embed.

    Args:
        articles: List of breaking news articles with title, url, reason, urgency

    Returns:
        Discord embed dict ready for sending
    """
    # Sort by urgency (highest first)
    sorted_articles = sorted(articles, key=lambda a: a.get("urgency", 0), reverse=True)

    # Build embed fields for each article
    fields = []
    for article in sorted_articles[:5]:  # Limit to 5 articles per embed
        urgency = article.get("urgency", 0)
        urgency_indicator = "🔴" if urgency >= 9 else "🟠" if urgency >= 7 else "🟡"

        fields.append(
            {
                "name": f"{urgency_indicator} {article.get('title', 'Unknown')}",
                "value": f"{article.get('reason', 'Breaking news')}\n[Read more]({article.get('url', '')})",
                "inline": False,
            }
        )

    now = datetime.now(UTC)
    return {
        "title": "🚨 Breaking AI News",
        "description": f"**{len(articles)} breaking {'story' if len(articles) == 1 else 'stories'}** detected",
        "color": 0xFF4444,  # Red color for breaking news
        "fields": fields,
        "footer": f"Kubani News Monitor • {now.strftime('%Y-%m-%d %H:%M UTC')}",
        "timestamp": now,
    }


@activity.defn
async def send_breaking_news_activity(
    channel_name: str,
    articles: list[dict[str, Any]],
) -> dict[str, Any]:
    """Send breaking news notification to Discord.

    Args:
        channel_name: Discord channel name (without #)
        articles: List of breaking articles with title, url, reason, urgency

    Returns:
        Dict with success status, message_id, and articles_notified count
    """
    if not articles:
        logger.info("send_breaking_news_activity: No articles to notify")
        return {
            "success": True,
            "message_id": None,
            "articles_notified": 0,
        }

    logger.info(
        f"send_breaking_news_activity: Sending {len(articles)} breaking articles to #{channel_name}"
    )

    try:
        client = _get_mcp_client()

        # Format articles as embed
        embed = _format_breaking_news_embed(articles)

        # Send to Discord via MCP
        response = await client.discord.send_message_to_channel_name(
            channel_name=channel_name,
            content=None,  # No plain text, just embed
            embed=embed,
        )

        if not response.success:
            logger.error(f"send_breaking_news_activity: Discord error: {response.error}")
            return {
                "success": False,
                "error": response.error,
                "articles_notified": 0,
            }

        message_id = response.data.get("message_id") if response.data else None
        logger.info(f"send_breaking_news_activity: Sent notification, message_id={message_id}")

        return {
            "success": True,
            "message_id": message_id,
            "channel_name": channel_name,
            "articles_notified": len(articles),
        }

    except Exception as e:
        logger.error(f"send_breaking_news_activity: Failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "articles_notified": 0,
        }


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "send_breaking_news_activity",
]
