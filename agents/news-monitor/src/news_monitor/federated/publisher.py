"""
News Publisher Agent - Executes action skills.

This federated agent handles:
- compose-digest: Create formatted news digest
- publish-to-discord: Post to Discord webhook

It uses the skill definitions for configuration and the existing
implementation code for actual execution.

Updated to use ExecutiveBrief format for professional 5-minute briefs.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from core_agents.skills import record_skill_outcome_to_registry
from news_monitor.agents.composer import DigestComposerAgent
from news_monitor.agents.publisher import DiscordPublisherAgent
from news_monitor.federated.skills import get_news_skill
from news_monitor.memory import (
    store_digest_record,
    try_claim_breaking_alert,
    try_claim_digest_publish,
)
from news_monitor.models import NewsDigest, ProcessedArticle, TrendingTopic

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """Result from publishing operations."""

    success: bool = False
    message_id: str | None = None
    digest: NewsDigest | None = None
    error: str | None = None


class NewsPublisherAgent:
    """
    Federated agent that executes news publishing skills.

    Skills used:
    - news/action/compose-digest
    - news/action/publish-to-discord

    Uses ExecutiveBrief format for professional 5-minute digests with:
    - Topline summary points
    - Research deep dives
    - Tool/MCP server mini-briefs
    - Security alerts
    - Trend momentum indicators
    """

    def __init__(self):
        """Initialize the publisher agent."""
        self._skill_compose = None
        self._skill_publish = None
        self._composer = None
        self._executive_brief_composer = None
        self._publisher = None

    async def _load_skills(self) -> None:
        """Load skill definitions."""
        if self._skill_compose is None:
            self._skill_compose = await get_news_skill("news/action/compose-digest")
        if self._skill_publish is None:
            self._skill_publish = await get_news_skill("news/action/publish-to-discord")

    def _get_composer(self) -> DigestComposerAgent:
        """Get or create digest composer (used for breaking alerts)."""
        if self._composer is None:
            self._composer = DigestComposerAgent()
        return self._composer

    def _get_executive_brief_composer(self):
        """Get or create executive brief composer."""
        # Import here to avoid circular imports and allow linter to see usage
        from news_monitor.digest.executive_brief import ExecutiveBriefComposer

        if self._executive_brief_composer is None:
            self._executive_brief_composer = ExecutiveBriefComposer()
        return self._executive_brief_composer

    def _get_publisher(self) -> DiscordPublisherAgent:
        """Get or create Discord publisher."""
        if self._publisher is None:
            self._publisher = DiscordPublisherAgent()
        return self._publisher

    async def compose_digest(
        self,
        articles: list[ProcessedArticle],
        trends: list[TrendingTopic],
        period_hours: int = 12,
    ) -> NewsDigest:
        """
        Compose a news digest using ExecutiveBrief format.

        Generates a professional 5-minute executive brief with:
        - Topline summary (3-5 key points)
        - Research deep dives with practical implications
        - Tool/MCP server mini-briefs
        - Security alerts
        - Trend momentum indicators (↑ ↓ →)

        The formatted content is stored in headline_summary for publishing.

        Args:
            articles: Processed articles to include
            trends: Trending topics to highlight
            period_hours: Hours covered by digest

        Returns:
            Composed NewsDigest with executive brief format in headline_summary
        """
        await self._load_skills()

        period_end = datetime.now(UTC)
        period_start = period_end - timedelta(hours=period_hours)

        logger.info(f"Composing executive brief from {len(articles)} articles")

        # Generate executive brief format
        exec_composer = self._get_executive_brief_composer()
        executive_brief = await exec_composer.compose_executive_brief(
            articles, trends, period_start, period_end
        )

        # Format for Discord
        formatted_content = executive_brief.to_discord_message()

        # Create NewsDigest with the executive brief content
        # We still use DigestComposerAgent to create the base digest structure
        # but override headline_summary with the executive brief format
        composer = self._get_composer()
        digest = composer.compose_digest(articles, trends, period_start, period_end)

        # Replace the flowing paragraph summary with executive brief format
        digest.headline_summary = formatted_content

        logger.info(
            f"Executive brief composed: {len(executive_brief.topline)} toplines, "
            f"{len(executive_brief.deep_dives)} deep dives, "
            f"{len(executive_brief.tools_briefs)} tool briefs"
        )

        return digest

    async def publish_digest(
        self,
        digest: NewsDigest,
    ) -> PublishResult:
        """
        Publish a digest to Discord (from publish-to-discord skill).

        Uses atomic claim to prevent duplicate publishing from activity retries.

        Steps:
        1. Atomically claim the digest
        2. Validate webhook configuration
        3. Format content for Discord
        4. Split if > 1900 chars
        5. Post to webhook

        Args:
            digest: The digest to publish

        Returns:
            PublishResult with success status and message ID
        """
        await self._load_skills()

        result = PublishResult()

        # Atomically claim the right to publish this digest
        claim_status = try_claim_digest_publish(digest.digest_id)
        if claim_status is False:
            logger.info(f"Digest already published (skipping duplicate): {digest.digest_id}")
            result.error = "already_published"
            # Mark as success since the digest was published (just not by us)
            result.success = True
            result.digest = digest
            return result
        elif claim_status is None:
            logger.warning(f"Cannot claim digest (Redis unavailable): {digest.digest_id}")
            result.error = "claim_unavailable"
            return result

        logger.info(f"Publishing digest {digest.digest_id}")

        try:
            # Use the pre-formatted executive brief content from headline_summary
            # This was generated by compose_digest using ExecutiveBriefComposer
            formatted = digest.headline_summary

            publisher = self._get_publisher()
            message_id = publisher.publish_digest(digest, formatted)

            if message_id:
                digest.published = True
                digest.discord_message_id = message_id

                # Store digest record
                article_urls = []
                if digest.sections:
                    for section in digest.sections:
                        article_urls.extend([a.url for a in section.articles])

                store_digest_record(
                    digest.digest_id,
                    article_urls,
                    [t.topic for t in digest.trending_topics],
                    message_id,
                )

                result.success = True
                result.message_id = message_id
                result.digest = digest
            else:
                result.error = "Failed to publish - no message ID returned"

        except Exception as e:
            logger.error(f"Failed to publish digest: {e}")
            result.error = str(e)

        # Record skill outcome to registry
        await record_skill_outcome_to_registry(
            skill_id="news/action/publish-to-discord",
            success=result.success,
            skill_name="Publish to Discord",
            domain="news",
            category="action",
        )

        return result

    async def publish_breaking_alert(
        self,
        article: ProcessedArticle,
        reason: str = "High-importance breaking news detected",
    ) -> PublishResult:
        """
        Publish a breaking news alert (from publish-to-discord skill).

        Uses atomic claim to prevent race conditions.

        Steps:
        1. Atomically claim the alert
        2. Format as Discord embed
        3. Post with @here mention

        Args:
            article: The breaking news article
            reason: Reason for the alert

        Returns:
            PublishResult with success status
        """
        await self._load_skills()

        result = PublishResult()

        # Atomically claim the right to publish this alert
        claim_status = try_claim_breaking_alert(article.url)
        if claim_status is False:
            logger.info(f"Breaking alert already claimed: {article.title[:50]}...")
            result.error = "already_claimed"
            return result
        elif claim_status is None:
            logger.warning(f"Cannot claim alert (Redis unavailable): {article.title[:50]}...")
            result.error = "claim_unavailable"
            return result

        logger.info(f"Publishing breaking alert: {article.title[:50]}...")

        try:
            composer = self._get_composer()
            formatted = composer.format_breaking_alert(article, reason)

            publisher = self._get_publisher()
            message_id = publisher.publish_breaking_alert(article, formatted)

            if message_id:
                result.success = True
                result.message_id = message_id
            else:
                result.error = "Failed to publish alert"

        except Exception as e:
            logger.error(f"Failed to publish breaking alert: {e}")
            result.error = str(e)

        # Record skill outcome (only if we actually attempted to publish)
        if claim_status is True:  # Only record if we claimed and attempted
            await record_skill_outcome_to_registry(
                skill_id="news/action/publish-to-discord",
                success=result.success,
                skill_name="Publish to Discord",
                domain="news",
                category="action",
            )

        return result

    async def compose_and_publish(
        self,
        articles: list[ProcessedArticle],
        trends: list[TrendingTopic],
        period_hours: int = 12,
    ) -> PublishResult:
        """
        Compose and publish a digest in one operation.

        Convenience method that runs both skills.

        Args:
            articles: Articles for the digest
            trends: Trending topics
            period_hours: Period covered

        Returns:
            PublishResult
        """
        digest = await self.compose_digest(articles, trends, period_hours)
        return await self.publish_digest(digest)


async def run_publish(
    articles: list[ProcessedArticle],
    trends: list[TrendingTopic],
    period_hours: int = 12,
) -> PublishResult:
    """
    Run the publish pipeline.

    Args:
        articles: Articles for digest
        trends: Trending topics
        period_hours: Period covered

    Returns:
        PublishResult
    """
    publisher = NewsPublisherAgent()
    return await publisher.compose_and_publish(articles, trends, period_hours)
