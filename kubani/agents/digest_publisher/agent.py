"""
Digest Publisher Agent - Skills-centric digest composition and publishing.

Delegates to news/publishing skills: compose-digest, compose-executive-digest, publish-discord.

Usage:
    agent = DigestPublisherAgent()
    result = await agent.compose_and_publish(articles, trends)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kubani.agents._base import SkillsOrchestrator

logger = logging.getLogger(__name__)


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
    digest_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    period_start: datetime = field(default_factory=lambda: datetime.now(UTC))
    period_end: datetime = field(default_factory=lambda: datetime.now(UTC))
    headline_summary: str = ""
    trending_topics: list[dict[str, Any]] = field(default_factory=list)
    total_articles: int = 0
    sources_used: list[str] = field(default_factory=list)


@dataclass
class ExecutiveDigest:
    """Rich executive digest with multiple sections."""
    digest_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    digest_type: str = "daily"
    period_start: datetime = field(default_factory=lambda: datetime.now(UTC))
    period_end: datetime = field(default_factory=lambda: datetime.now(UTC))
    sections: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class DigestPublisherAgent(SkillsOrchestrator):
    """Skills-centric digest publisher using compose-digest and publish-discord skills."""

    AGENT_DIR = Path(__file__).parent
    SKILLS_DOMAIN = "news"
    SKILLS_CATEGORY = "publishing"

    def __init__(self, agent_dir: Path | None = None):
        super().__init__(agent_dir)
        self.default_channel = self.config.get("publisher", {}).get("channel", "ai-news")

    async def compose_digest(
        self, articles: list[dict[str, Any]], trends: list[dict[str, Any]]
    ) -> NewsDigest:
        """Compose a news digest using compose-digest skill."""
        if not articles:
            return NewsDigest()

        prompt = f"""Use compose-digest skill to create digest from {len(articles)} articles.
Articles: {json.dumps(articles[:15], default=str)}
Trends: {json.dumps(trends[:5] if trends else [], default=str)}
Return JSON: digest_id, headline_summary, trending_topics, total_articles, sources_used"""

        return self._parse_digest(await self.run(prompt), articles)

    async def compose_executive_digest(
        self,
        articles: list[dict[str, Any]],
        research_deepdives: list[dict[str, Any]] | None = None,
        tool_spotlights: list[dict[str, Any]] | None = None,
        trends: dict[str, Any] | None = None,
        digest_type: str = "daily",
    ) -> ExecutiveDigest:
        """Compose an executive digest using compose-executive-digest skill."""
        prompt = f"""Use compose-executive-digest skill. Type: {digest_type}
Articles: {json.dumps(articles[:10], default=str)}
Papers: {json.dumps((research_deepdives or [])[:3], default=str)}
Repos: {json.dumps((tool_spotlights or [])[:3], default=str)}
Trends: {json.dumps(trends or {}, default=str)}
Return JSON: digest_id, digest_type, sections, metadata"""

        return self._parse_executive_digest(await self.run(prompt), digest_type)

    async def publish_to_discord(self, content: str, channel: str | None = None) -> PublishResult:
        """Publish content to Discord using publish-discord skill."""
        target = channel or self.default_channel
        prompt = f"""Use publish-discord skill to send to #{target}:
```
{content}
```
Return JSON: success, message_id, chunks_sent, channel, error"""

        return self._parse_publish_result(await self.run(prompt), target)

    async def compose_and_publish(
        self, articles: list[dict[str, Any]], trends: list[dict[str, Any]], channel: str | None = None
    ) -> PublishResult:
        """Compose a digest and publish to Discord."""
        if not articles:
            return PublishResult(success=False, error="No articles provided")

        digest = await self.compose_digest(articles, trends)
        content = f"# AI News Digest\n\n{digest.headline_summary}\n\n---\n*{digest.total_articles} articles from {len(digest.sources_used)} sources*"
        result = await self.publish_to_discord(content, channel)
        await self.on_skill_complete("compose_and_publish", {"success": result.success, "articles": len(articles)})
        return result

    async def publish_breaking(self, article: dict[str, Any], channel: str | None = None) -> PublishResult:
        """Publish a breaking news alert."""
        title = article.get("title", "Breaking News")
        summary = article.get("ai_summary", article.get("summary", ""))
        url = article.get("url", "")
        content = f"**BREAKING NEWS**\n\n**{title}**\n\n{summary}\n\nSource: {article.get('source', 'Unknown')}"
        if url:
            content += f"\n[Read more]({url})"
        return await self.publish_to_discord(content, channel)

    def _parse_digest(self, response: str, articles: list[dict[str, Any]]) -> NewsDigest:
        """Parse LLM response into NewsDigest."""
        try:
            data = self._extract_json(response)
            now = datetime.now(UTC)
            return NewsDigest(
                digest_id=data.get("digest_id", f"digest-{now.timestamp():.0f}"),
                created_at=now, period_start=now, period_end=now,
                headline_summary=data.get("headline_summary", ""),
                trending_topics=data.get("trending_topics", []),
                total_articles=data.get("total_articles", len(articles)),
                sources_used=data.get("sources_used", []),
            )
        except Exception as e:
            logger.warning(f"Failed to parse digest: {e}")
            return NewsDigest(total_articles=len(articles))

    def _parse_executive_digest(self, response: str, digest_type: str) -> ExecutiveDigest:
        """Parse LLM response into ExecutiveDigest."""
        try:
            data = self._extract_json(response)
            now = datetime.now(UTC)
            return ExecutiveDigest(
                digest_id=data.get("digest_id", f"exec-{now.timestamp():.0f}"),
                created_at=now, digest_type=data.get("digest_type", digest_type),
                period_start=now, period_end=now,
                sections=data.get("sections", {}), metadata=data.get("metadata", {}),
            )
        except Exception as e:
            logger.warning(f"Failed to parse executive digest: {e}")
            return ExecutiveDigest(digest_type=digest_type)

    def _parse_publish_result(self, response: str, channel: str) -> PublishResult:
        """Parse LLM response into PublishResult."""
        try:
            data = self._extract_json(response)
            return PublishResult(
                success=data.get("success", False), message_id=data.get("message_id"),
                chunks_sent=data.get("chunks_sent", 0), channel=data.get("channel", channel),
                error=data.get("error"),
            )
        except Exception as e:
            logger.warning(f"Failed to parse publish result: {e}")
            return PublishResult(success=False, channel=channel, error=str(e))

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        await self.record_outcome(skill_name, result, success=result.get("success", False))
