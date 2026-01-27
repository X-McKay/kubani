"""
Digest Publisher Agent - Composes and publishes digests/summaries.

Implements three skills:
- compose-digest: Basic LLM-generated narrative summaries
- compose-executive-digest: Rich multi-section digest with research, tools, trends
- publish-to-discord: Publishes to Discord via MCP server

Usage:
    from agents.digest_publisher import DigestPublisherAgent

    agent = DigestPublisherAgent()
    result = await agent.compose_and_publish(articles, trends)

    # Or use the executive digest for richer content:
    result = await agent.compose_executive_digest(
        articles=articles,
        research_deepdives=papers,
        tool_spotlights=repos,
        company_updates=company_articles,
        trends=trend_analysis,
    )
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from kubani.agents._base import KubaniAgent

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


@dataclass
class ExecutiveDigest:
    """Rich executive digest with multiple sections."""

    digest_id: str
    created_at: datetime
    digest_type: str  # daily, weekly, breaking
    period_start: datetime
    period_end: datetime
    sections: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "digest_id": self.digest_id,
            "created_at": self.created_at.isoformat(),
            "digest_type": self.digest_type,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "sections": self.sections,
            "metadata": self.metadata,
        }


@dataclass
class ExecutiveDigestResult:
    """Result from compose-executive-digest skill."""

    digest: ExecutiveDigest
    discord_messages: list[str] = field(default_factory=list)
    sections_included: list[str] = field(default_factory=list)


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


EXECUTIVE_SUMMARY_PROMPT = """Write an executive summary (2-3 paragraphs) for AI practitioners covering:

**Key Developments:**
{key_developments}

**Trending Topics:**
{trends}

Focus on:
1. Most impactful business/research developments
2. Emerging patterns practitioners should watch
3. Actionable insights

Write in a professional, concise style. Start with the most important item."""


RESEARCH_DEEPDIVE_PROMPT = """Write a research deep-dive section for this paper:

**Title:** {title}
**Authors:** {authors}
**Key Innovation:** {key_innovation}
**Practitioner Summary:** {practitioner_summary}
**Key Takeaways:** {key_takeaways}

Write 2-3 paragraphs suitable for an AI newsletter. Focus on:
1. What this paper achieves
2. Why practitioners should care
3. Potential applications

Include the arXiv link: https://arxiv.org/abs/{arxiv_id}"""


TOOL_SPOTLIGHT_PROMPT = """Write a tool spotlight for this repository:

**Repository:** {full_name}
**Description:** {description}
**Stars:** {stars}
**Category:** {category}
**Best For:** {best_for}
**Spotlight Summary:** {spotlight_summary}

Write 1-2 paragraphs for an AI newsletter. Focus on:
1. What problem it solves
2. Who should use it
3. Getting started

Include the GitHub link: {url}"""


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

    # ========================================================================
    # compose-executive-digest skill implementation
    # ========================================================================

    # Major AI companies for grouping
    MAJOR_COMPANIES = [
        "openai",
        "anthropic",
        "google",
        "deepmind",
        "meta",
        "microsoft",
        "nvidia",
        "huggingface",
        "hugging face",
        "mistral",
        "cohere",
        "xai",
    ]

    def _identify_company(self, article: dict[str, Any]) -> str | None:
        """Identify which major company an article is about."""
        title = article.get("title", "").lower()
        source = article.get("source", "").lower()
        text = f"{title} {source}"

        for company in self.MAJOR_COMPANIES:
            if company in text:
                # Normalize company names
                if company in ("huggingface", "hugging face"):
                    return "Hugging Face"
                elif company == "deepmind":
                    return "Google/DeepMind"
                elif company == "xai":
                    return "xAI"
                return company.title()
        return None

    def _generate_executive_summary(
        self,
        articles: list[dict[str, Any]],
        trends: dict[str, Any] | None,
    ) -> str:
        """Generate executive summary using LLM."""
        # Select top articles for summary
        top_articles = sorted(
            articles,
            key=lambda a: a.get("importance_score", 5),
            reverse=True,
        )[:7]

        # Format key developments
        developments = []
        for a in top_articles:
            developments.append(
                f"- {a.get('title', 'Untitled')}: {a.get('ai_summary', a.get('summary', ''))[:200]}"
            )

        # Format trends
        trends_text = "No significant trends"
        if trends:
            trend_items = trends.get("trends", [])[:5]
            if trend_items:
                trends_text = ", ".join(
                    f"{t.get('entity', '')} ({t.get('velocity_class', 'stable')})"
                    for t in trend_items
                )

        try:
            client = self._get_llm_client()
            response = client.chat.completions.create(
                model=self._get_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional AI news editor. Write clear, engaging executive summaries.",
                    },
                    {
                        "role": "user",
                        "content": EXECUTIVE_SUMMARY_PROMPT.format(
                            key_developments="\n".join(developments),
                            trends=trends_text,
                        ),
                    },
                ],
                temperature=0.5,
                max_tokens=800,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            summary = response.choices[0].message.content
            summary = re.sub(r"<think>.*?</think>", "", summary, flags=re.DOTALL)
            return summary.strip()

        except Exception as e:
            logger.error(f"Failed to generate executive summary: {e}")
            return self._fallback_executive_summary(top_articles)

    def _fallback_executive_summary(self, articles: list[dict[str, Any]]) -> str:
        """Fallback executive summary without LLM."""
        lines = ["**Key Developments:**\n"]
        for a in articles[:5]:
            lines.append(f"- **{a.get('title', 'Untitled')}**: {a.get('ai_summary', '')[:150]}...")
        return "\n".join(lines)

    def _format_research_section(
        self,
        research_deepdives: list[dict[str, Any]],
        max_papers: int = 3,
    ) -> str:
        """Format research deep-dives section."""
        if not research_deepdives:
            return ""

        # Sort by relevance and take top papers
        sorted_papers = sorted(
            research_deepdives,
            key=lambda p: p.get("relevance_scores", {}).get("overall", 0),
            reverse=True,
        )[:max_papers]

        lines = ["## Research Deep-dives\n"]

        for paper in sorted_papers:
            arxiv_id = paper.get("arxiv_id", "")
            title = paper.get("title", "Untitled")
            authors = paper.get("authors", [])[:3]  # Limit authors
            summary = paper.get("practitioner_summary", "")
            takeaways = paper.get("key_takeaways", [])[:3]
            scores = paper.get("relevance_scores", {})

            lines.append(f"### [{title}](https://arxiv.org/abs/{arxiv_id})")
            lines.append(f"**Authors**: {', '.join(authors)}")
            if paper.get("main_claim"):
                lines.append(f"**Key Finding**: {paper.get('main_claim')}")
            lines.append("")
            lines.append(summary)
            lines.append("")

            if takeaways:
                lines.append("**Key Takeaways**:")
                for t in takeaways:
                    lines.append(f"- {t}")
                lines.append("")

            overall = scores.get("overall", 5)
            lines.append(f"**Relevance**: {overall}/10")
            lines.append("")

        return "\n".join(lines)

    def _format_tools_section(
        self,
        tool_spotlights: list[dict[str, Any]],
        max_tools: int = 3,
    ) -> str:
        """Format tool spotlights section."""
        if not tool_spotlights:
            return ""

        # Filter to spotlight-worthy tools
        worthy_tools = [t for t in tool_spotlights if t.get("spotlight_worthy", False)]
        if not worthy_tools:
            worthy_tools = tool_spotlights[:max_tools]
        else:
            worthy_tools = worthy_tools[:max_tools]

        lines = ["## Tool Spotlights\n"]

        for tool in worthy_tools:
            name = tool.get("name", "")
            full_name = tool.get("full_name", name)
            url = tool.get("url", f"https://github.com/{full_name}")
            stars = tool.get("stars", 0)
            language = tool.get("language", "")
            topics = tool.get("topics", [])[:3]
            summary = tool.get("spotlight_summary", tool.get("description", ""))
            best_for = tool.get("best_for", "")

            lines.append(f"### [{name}]({url}) ⭐ {stars:,}")
            meta_parts = []
            if language:
                meta_parts.append(f"**Language**: {language}")
            if topics:
                meta_parts.append(f"**Topics**: {', '.join(topics)}")
            if meta_parts:
                lines.append(" | ".join(meta_parts))
            lines.append("")
            lines.append(summary)
            if best_for:
                lines.append(f"\n**Best For**: {best_for}")
            lines.append("")

        return "\n".join(lines)

    def _format_company_section(
        self,
        company_updates: list[dict[str, Any]],
        max_per_company: int = 3,
    ) -> str:
        """Format company updates section grouped by company."""
        if not company_updates:
            return ""

        # Group by company
        by_company: dict[str, list[dict[str, Any]]] = {}
        for article in company_updates:
            company = self._identify_company(article)
            if company:
                if company not in by_company:
                    by_company[company] = []
                by_company[company].append(article)

        if not by_company:
            return ""

        lines = ["## Company Updates\n"]

        # Sort companies by total importance
        sorted_companies = sorted(
            by_company.items(),
            key=lambda x: sum(a.get("importance_score", 5) for a in x[1]),
            reverse=True,
        )

        for company, articles in sorted_companies[:5]:
            lines.append(f"### {company}")

            # Sort articles by importance and limit
            sorted_articles = sorted(
                articles,
                key=lambda a: a.get("importance_score", 5),
                reverse=True,
            )[:max_per_company]

            for article in sorted_articles:
                title = article.get("title", "Untitled")
                url = article.get("url", "")
                summary = article.get("ai_summary", article.get("summary", ""))[:100]
                lines.append(f"- [{title}]({url}) - {summary}...")
            lines.append("")

        return "\n".join(lines)

    def _format_trends_section(
        self,
        trends: dict[str, Any] | None,
    ) -> str:
        """Format trend watch section."""
        if not trends:
            return ""

        trend_items = trends.get("trends", [])
        emerging = trends.get("emerging_topics", [])
        declining = trends.get("declining_topics", [])
        summary = trends.get("summary", "")

        if not (trend_items or emerging or declining):
            return ""

        lines = ["## Trend Watch\n"]

        # Rising/Surging topics
        rising = [t for t in trend_items if t.get("velocity_class") in ("surging", "rising")]
        if rising:
            rising_text = ", ".join(
                f"{t.get('entity', '').title()} (↑ {abs(t.get('velocity_percent', 0)):.0f}%)"
                for t in rising[:3]
            )
            lines.append(f"**Rising**: {rising_text}")

        if emerging:
            lines.append(f"**Emerging**: {', '.join(e.title() for e in emerging[:3])}")

        if declining:
            lines.append(f"**Fading**: {', '.join(d.title() for d in declining[:3])}")

        if summary:
            lines.append("")
            lines.append(summary)

        lines.append("")
        return "\n".join(lines)

    def _format_executive_header(
        self,
        digest_type: str,
        period_hours: int,
        article_count: int,
        source_count: int,
    ) -> str:
        """Format digest header."""
        now = datetime.now(UTC)
        date_str = now.strftime("%B %d, %Y")

        if digest_type == "weekly":
            edition = "Weekly Edition"
        elif digest_type == "breaking":
            edition = "Breaking Alert"
        else:
            time_label = "Morning" if now.hour < 12 else "Evening"
            edition = f"{time_label} Edition"

        return f"""# AI News Digest - {date_str}
*{edition} | {article_count} articles from {source_count} sources*

---
"""

    def _format_executive_footer(self) -> str:
        """Format digest footer."""
        return """---
*Generated by Kubani News Service | [Feedback](https://github.com/kubani)*
"""

    async def compose_executive_digest(
        self,
        articles: list[dict[str, Any]],
        research_deepdives: list[dict[str, Any]] | None = None,
        tool_spotlights: list[dict[str, Any]] | None = None,
        company_updates: list[dict[str, Any]] | None = None,
        trends: dict[str, Any] | None = None,
        digest_type: str = "daily",
        period_hours: int = 24,
    ) -> ExecutiveDigestResult:
        """
        Compose a rich executive digest with multiple sections.

        Implements the compose-executive-digest skill.

        Args:
            articles: Processed news articles
            research_deepdives: Analyzed arXiv papers (max 3 featured)
            tool_spotlights: Analyzed GitHub repos (max 3 featured)
            company_updates: Articles about major AI companies
            trends: Trend analysis with velocity data
            digest_type: "daily", "weekly", or "breaking"
            period_hours: Hours covered by this digest

        Returns:
            ExecutiveDigestResult with digest, discord messages, and sections list
        """
        now = datetime.now(UTC)

        # Validate minimum content
        if not articles and not research_deepdives:
            raise ValueError("Insufficient content: need at least 3 articles or 1 research paper")

        logger.info(
            f"Composing executive digest: {len(articles)} articles, "
            f"{len(research_deepdives or [])} papers, "
            f"{len(tool_spotlights or [])} repos"
        )

        sections: dict[str, Any] = {}
        sections_included: list[str] = []

        # Step 1: Generate executive summary
        executive_summary = self._generate_executive_summary(articles, trends)
        sections["executive_summary"] = executive_summary
        sections_included.append("executive_summary")

        # Step 2: Research deep-dives (max 3)
        if research_deepdives:
            research_section = self._format_research_section(research_deepdives)
            if research_section:
                sections["research_deepdives"] = research_deepdives[:3]
                sections_included.append("research_deepdives")

        # Step 3: Tool spotlights (max 3)
        if tool_spotlights:
            tools_section = self._format_tools_section(tool_spotlights)
            if tools_section:
                sections["tool_spotlights"] = tool_spotlights[:3]
                sections_included.append("tool_spotlights")

        # Step 4: Company updates
        if company_updates:
            company_section = self._format_company_section(company_updates)
            if company_section:
                sections["company_updates"] = company_updates
                sections_included.append("company_updates")

        # Step 5: Trends (for weekly or if provided)
        if trends:
            trends_section = self._format_trends_section(trends)
            if trends_section:
                sections["trends"] = trends
                sections_included.append("trends")

        # Build metadata
        metadata = {
            "article_count": len(articles),
            "source_count": len({a.get("source") for a in articles}),
            "papers_featured": len(research_deepdives[:3]) if research_deepdives else 0,
            "tools_featured": len(tool_spotlights[:3]) if tool_spotlights else 0,
        }

        # Create digest object
        digest = ExecutiveDigest(
            digest_id=f"digest-{uuid4().hex[:8]}",
            created_at=now,
            digest_type=digest_type,
            period_start=now - timedelta(hours=period_hours),
            period_end=now,
            sections=sections,
            metadata=metadata,
        )

        # Format for Discord
        discord_messages = self._format_executive_for_discord(
            digest=digest,
            executive_summary=executive_summary,
            research_deepdives=research_deepdives,
            tool_spotlights=tool_spotlights,
            company_updates=company_updates,
            trends=trends,
        )

        logger.info(
            f"Executive digest composed: {digest.digest_id}, "
            f"{len(sections_included)} sections, {len(discord_messages)} discord chunks"
        )

        return ExecutiveDigestResult(
            digest=digest,
            discord_messages=discord_messages,
            sections_included=sections_included,
        )

    def _format_executive_for_discord(
        self,
        digest: ExecutiveDigest,
        executive_summary: str,
        research_deepdives: list[dict[str, Any]] | None,
        tool_spotlights: list[dict[str, Any]] | None,
        company_updates: list[dict[str, Any]] | None,
        trends: dict[str, Any] | None,
    ) -> list[str]:
        """Format executive digest for Discord with smart chunking."""
        parts = []

        # Header + Executive Summary
        header = self._format_executive_header(
            digest_type=digest.digest_type,
            period_hours=int((digest.period_end - digest.period_start).total_seconds() / 3600),
            article_count=digest.metadata.get("article_count", 0),
            source_count=digest.metadata.get("source_count", 0),
        )
        parts.append(header + "## Executive Summary\n\n" + executive_summary)

        # Research section
        if research_deepdives:
            research_section = self._format_research_section(research_deepdives)
            if research_section:
                parts.append(research_section)

        # Tools section
        if tool_spotlights:
            tools_section = self._format_tools_section(tool_spotlights)
            if tools_section:
                parts.append(tools_section)

        # Company section
        if company_updates:
            company_section = self._format_company_section(company_updates)
            if company_section:
                parts.append(company_section)

        # Trends section
        if trends:
            trends_section = self._format_trends_section(trends)
            if trends_section:
                parts.append(trends_section)

        # Footer
        parts.append(self._format_executive_footer())

        # Smart chunking for Discord (max 1900 chars per message)
        discord_messages = []
        for part in parts:
            chunks = self._split_message(part, max_length=1900)
            discord_messages.extend(chunks)

        return discord_messages

    async def compose_and_publish_executive(
        self,
        articles: list[dict[str, Any]],
        research_deepdives: list[dict[str, Any]] | None = None,
        tool_spotlights: list[dict[str, Any]] | None = None,
        company_updates: list[dict[str, Any]] | None = None,
        trends: dict[str, Any] | None = None,
        digest_type: str = "daily",
        period_hours: int = 24,
        channel_name: str | None = None,
    ) -> PublishResult:
        """
        Compose executive digest and publish to Discord.

        Combines compose-executive-digest and publish-to-discord skills.
        """
        try:
            result = await self.compose_executive_digest(
                articles=articles,
                research_deepdives=research_deepdives,
                tool_spotlights=tool_spotlights,
                company_updates=company_updates,
                trends=trends,
                digest_type=digest_type,
                period_hours=period_hours,
            )

            # Publish each chunk
            channel = channel_name or self.default_channel
            message_id = None

            for i, chunk in enumerate(result.discord_messages):
                pub_result = self._publish_digest(chunk, channel)
                if i == 0:
                    message_id = pub_result.message_id

            return PublishResult(
                success=True,
                message_id=message_id,
                chunks_sent=len(result.discord_messages),
                channel=channel,
            )

        except Exception as e:
            logger.error(f"Failed to compose/publish executive digest: {e}")
            return PublishResult(
                success=False,
                error=str(e),
                channel=channel_name or self.default_channel,
            )

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("success", False)
        await self.record_outcome(skill_name, result, success=success)
