"""
Digest Publisher Agent - Composes and publishes digests/summaries.

Implements two skills:
- compose-digest: Uses LLM to generate cohesive narrative summaries
- publish-to-discord: Publishes to Discord via MCP server

Usage:
    from agents.digest_publisher import DigestPublisherAgent

    agent = DigestPublisherAgent()
    result = await agent.compose_and_publish(articles, trends)
"""

import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents._base import KubaniAgent

logger = logging.getLogger(__name__)


# ============================================================================
# Models
# ============================================================================


@dataclass
class PublishResult:
    """Result from publishing operations."""

    success: bool = False
    message_id: str | None = None
    chunks_sent: int = 0
    channel: str = ""
    error: str | None = None


@dataclass
class NewsDigest:
    """Complete news digest ready for publishing."""

    digest_id: str
    created_at: datetime
    period_start: datetime
    period_end: datetime
    headline_summary: str = ""
    trending_topics: list[dict[str, Any]] | None = None
    total_articles: int = 0
    sources_used: list[str] | None = None


# ============================================================================
# Prompts
# ============================================================================


DIGEST_PROMPT = """You are a tech news editor creating a digest of AI news.

Write a cohesive, professional summary of these news items. The summary should:
1. Be written as flowing paragraphs, not bullet points
2. Embed source citations inline using markdown links [Source Name](url)
3. Highlight the most important developments first
4. Group related news naturally in the narrative
5. Be concise but comprehensive

Articles to summarize:
{articles}

Trending topics this cycle: {trends}

Write 2-4 paragraphs summarizing the key AI news. Start with the most impactful stories.
Include citations for each fact mentioned. Format citations as [Source](URL)."""


# ============================================================================
# Agent Implementation
# ============================================================================


class DigestPublisherAgent(KubaniAgent):
    """
    Composes and publishes digests/summaries.

    Implements compose-digest and publish-to-discord skill logic.
    """

    AGENT_DIR = Path(__file__).parent

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Digest Publisher agent."""
        super().__init__(agent_dir)

        # Publisher-specific configuration
        publisher_config = self.config.get("publisher", {})
        self.default_channel = publisher_config.get("channel", "ai-news")

        # LLM client - lazy initialization
        self._llm_client = None

    def _get_llm_client(self):
        """Get or create LLM client."""
        if self._llm_client is None:
            from openai import OpenAI

            self._llm_client = OpenAI(
                api_key="not-needed",
                base_url=os.environ.get(
                    "VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1"
                ),
            )
        return self._llm_client

    def _get_model(self) -> str:
        """Get the LLM model name."""
        return os.environ.get("VLLM_MODEL", "nvidia/Qwen3-14B-FP4")

    # ========================================================================
    # compose-digest skill implementation
    # ========================================================================

    def _select_articles(
        self,
        articles: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Select articles by importance per compose-digest skill.

        Step 1: Sort by importance and select:
        - All high importance (score >= 7)
        - Top 5 medium importance (score 5-6)
        - Fallback: Top 5 if nothing notable
        """
        # Sort by importance score (descending)
        sorted_articles = sorted(
            articles,
            key=lambda a: a.get("importance_score", 5),
            reverse=True,
        )

        high_importance = [a for a in sorted_articles if a.get("importance_score", 5) >= 7]
        medium_importance = [a for a in sorted_articles if 5 <= a.get("importance_score", 5) < 7]

        # Include all high + some medium
        selected = high_importance + medium_importance[:5]

        if not selected:
            # Fallback: take top 5 by score
            selected = sorted_articles[:5]

        return selected

    def _generate_summary(
        self,
        articles: list[dict[str, Any]],
        trends: list[dict[str, Any]],
    ) -> str:
        """
        Generate LLM summary per compose-digest skill.

        Step 2-3: Call LLM and parse response.
        """
        # Format articles for prompt
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"""
{i}. {article.get("title", "Untitled")}
   Source: {article.get("source", "Unknown")}
   URL: {article.get("url", "")}
   Importance: {article.get("importance_score", 5)}/10
   Summary: {article.get("summary", article.get("ai_summary", ""))}
"""

        # Format trends
        trends_text = (
            ", ".join(
                f"{t.get('topic', '')} ({t.get('status', 'rising')})" for t in (trends or [])[:5]
            )
            or "No significant trends"
        )

        try:
            client = self._get_llm_client()
            response = client.chat.completions.create(
                model=self._get_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional tech news editor. Write clear, engaging summaries with proper citations.",
                    },
                    {
                        "role": "user",
                        "content": DIGEST_PROMPT.format(
                            articles=articles_text,
                            trends=trends_text,
                        ),
                    },
                ],
                temperature=0.5,
                max_tokens=1500,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            summary = response.choices[0].message.content

            # Step 3: Clean up response - strip thinking tags
            summary = re.sub(r"<think>.*?</think>", "", summary, flags=re.DOTALL)
            return summary.strip()

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return self._fallback_summary(articles)

    def _fallback_summary(self, articles: list[dict[str, Any]]) -> str:
        """
        Fallback summary without LLM per skill spec.
        """
        lines = ["**Today's AI News Highlights:**\n"]

        for article in articles[:5]:
            title = article.get("title", "Untitled")
            url = article.get("url", "")
            source = article.get("source", "Unknown")
            summary = article.get("summary", article.get("ai_summary", ""))[:150]
            lines.append(f"- [{title}]({url}) ({source}): {summary}...")

        return "\n".join(lines)

    def _compose_digest(
        self,
        articles: list[dict[str, Any]],
        trends: list[dict[str, Any]],
        period_hours: int = 12,
    ) -> tuple[NewsDigest, str]:
        """
        Compose a complete news digest.

        Returns:
            Tuple of (NewsDigest, formatted_content_for_discord)
        """
        # Step 1: Select articles
        selected = self._select_articles(articles)

        # Step 2-3: Generate summary
        headline_summary = self._generate_summary(selected, trends)

        # Step 4: Build NewsDigest
        now = datetime.now(UTC)
        digest = NewsDigest(
            digest_id=f"digest-{uuid4().hex[:8]}",
            created_at=now,
            period_start=now - timedelta(hours=period_hours),
            period_end=now,
            headline_summary=headline_summary,
            trending_topics=trends[:5] if trends else [],
            total_articles=len(selected),
            sources_used=list({a.get("source", "Unknown") for a in selected}),
        )

        # Step 5: Format for Discord
        formatted = self._format_for_discord(digest, trends)

        logger.info(f"Composed digest {digest.digest_id} with {len(selected)} articles")
        return digest, formatted

    def _format_for_discord(
        self,
        digest: NewsDigest,
        trends: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Format digest for Discord posting per skill spec.
        """
        lines = []

        # Header
        period = digest.period_start.strftime("%B %d, %Y")
        time_label = "Morning" if digest.created_at.hour < 12 else "Evening"
        lines.append(f"# AI News Digest - {period} ({time_label})\n")

        # Main summary
        lines.append(digest.headline_summary)
        lines.append("")

        # Trending section (if notable trends)
        if trends:
            hot_trends = [t for t in trends if t.get("status") == "hot"]
            rising_trends = [t for t in trends if t.get("status") == "rising"]

            if hot_trends:
                lines.append("**Trending Topics:**")
                for trend in hot_trends[:3]:
                    sources_count = len(trend.get("sources", []))
                    lines.append(f"- {trend.get('topic', '')} (covered by {sources_count} sources)")
                lines.append("")

            if rising_trends:
                lines.append("**Emerging Themes:**")
                for trend in rising_trends[:2]:
                    lines.append(f"- {trend.get('topic', '')}")
                lines.append("")

        # Footer
        lines.append("---")
        sources_count = len(digest.sources_used) if digest.sources_used else 0
        lines.append(f"*{digest.total_articles} articles from {sources_count} sources*")

        return "\n".join(lines)

    # ========================================================================
    # publish-to-discord skill implementation
    # ========================================================================

    def _is_discord_configured(self) -> bool:
        """Check if Discord MCP is configured."""
        return os.environ.get("DISCORD_MCP_URL") is not None

    def _split_message(self, content: str, max_length: int = 1900) -> list[str]:
        """
        Split message into chunks per publish-to-discord skill.

        Step 4: Handle chunking for Discord's 2000 char limit.
        """
        if len(content) <= max_length:
            return [content]

        chunks = []
        current_chunk = ""

        # Split by paragraphs (double newline)
        paragraphs = content.split("\n\n")

        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 <= max_length:
                if current_chunk:
                    current_chunk += "\n\n"
                current_chunk += para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                # If single paragraph too long, split by lines
                if len(para) > max_length:
                    lines = para.split("\n")
                    current_chunk = ""
                    for line in lines:
                        if len(current_chunk) + len(line) + 1 <= max_length:
                            if current_chunk:
                                current_chunk += "\n"
                            current_chunk += line
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = line
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _publish_digest(
        self,
        content: str,
        channel_name: str | None = None,
    ) -> PublishResult:
        """
        Publish digest content to Discord.

        Steps 1-4 of publish-to-discord skill.
        """
        channel = channel_name or self.default_channel

        # Step 1: Validate configuration
        if not self._is_discord_configured():
            logger.warning("Cannot publish digest - Discord MCP not configured")
            return PublishResult(
                success=False,
                error="Discord MCP not configured",
                channel=channel,
            )

        try:
            from core_agents.integrations.discord_mcp import send_discord_message_sync

            # Step 4: Split if needed
            chunks = self._split_message(content)

            message_id = None
            for i, chunk in enumerate(chunks):
                # Step 3: Post content
                result = send_discord_message_sync(
                    content=chunk,
                    channel_name=channel,
                    agent_name="news-monitor",
                )

                # Get message ID from first chunk
                if i == 0:
                    message_id = result

            logger.info(f"Published digest to #{channel} ({len(chunks)} chunks)")
            return PublishResult(
                success=True,
                message_id=message_id,
                chunks_sent=len(chunks),
                channel=channel,
            )

        except Exception as e:
            logger.error(f"Failed to publish digest to Discord: {e}")
            return PublishResult(
                success=False,
                error=str(e),
                channel=channel,
            )

    def _publish_breaking_alert(
        self,
        article: dict[str, Any],
        channel_name: str | None = None,
    ) -> PublishResult:
        """
        Publish breaking news alert with embed.

        Step 2-3 for breaking_alert type per skill spec.
        """
        channel = channel_name or self.default_channel

        if not self._is_discord_configured():
            logger.warning("Cannot publish alert - Discord MCP not configured")
            return PublishResult(
                success=False,
                error="Discord MCP not configured",
                channel=channel,
            )

        try:
            from core_agents.integrations.discord_mcp import send_discord_message_sync

            # Build embed per skill spec
            embed = {
                "title": f"BREAKING: {article.get('title', 'Breaking News')}",
                "description": article.get("ai_summary", article.get("summary", "")),
                "url": article.get("url", ""),
                "color": 15158332,  # Red color
                "fields": [
                    {"name": "Source", "value": article.get("source", "Unknown"), "inline": True},
                    {
                        "name": "Category",
                        "value": article.get("category", "general").title(),
                        "inline": True,
                    },
                ],
                "footer": {"text": "AI News Monitor - Breaking Alert"},
            }

            message_id = send_discord_message_sync(
                content="@here **Breaking AI News**",
                embed=embed,
                channel_name=channel,
                agent_name="news-monitor",
            )

            logger.info(f"Published breaking alert for: {article.get('title', '')[:50]}...")
            return PublishResult(
                success=True,
                message_id=message_id,
                chunks_sent=1,
                channel=channel,
            )

        except Exception as e:
            logger.error(f"Failed to publish breaking alert: {e}")
            return PublishResult(
                success=False,
                error=str(e),
                channel=channel,
            )

    # ========================================================================
    # Public API
    # ========================================================================

    async def compose_and_publish(
        self,
        articles: list[dict[str, Any]],
        trends: list[dict[str, Any]],
        channel_name: str | None = None,
    ) -> PublishResult:
        """
        Compose digest and publish to Discord.

        Main entry point combining compose-digest and publish-to-discord skills.

        Args:
            articles: Processed articles to include
            trends: Identified trends
            channel_name: Target Discord channel (default: ai-news)

        Returns:
            PublishResult with success status and message ID
        """
        if not articles:
            logger.info("No articles to publish")
            return PublishResult(success=False, error="No articles provided")

        # Compose the digest
        digest, formatted_content = self._compose_digest(articles, trends)

        # Publish to Discord
        result = self._publish_digest(formatted_content, channel_name)

        if result.success:
            logger.info(f"Published digest {digest.digest_id}")

        return result

    async def publish_breaking(
        self,
        article: dict[str, Any],
        channel_name: str | None = None,
    ) -> PublishResult:
        """
        Publish a breaking news alert.

        Args:
            article: Breaking news article
            channel_name: Target Discord channel

        Returns:
            PublishResult with success status
        """
        return self._publish_breaking_alert(article, channel_name)

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("success", False)
        await self.record_outcome(skill_name, result, success=success)
