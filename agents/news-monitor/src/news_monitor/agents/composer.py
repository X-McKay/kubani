"""
Digest Composer Agent - Creates formatted news digests.

Responsible for:
- Organizing articles by importance and category
- Generating cohesive summary paragraphs with embedded citations
- Formatting for Discord readability
- Adapting length based on content volume
"""

import logging
import os
from datetime import datetime
from uuid import uuid4

from openai import OpenAI

from news_monitor.models import (
    NewsDigest,
    ProcessedArticle,
    TrendingTopic,
    TrendStatus,
)

logger = logging.getLogger(__name__)


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


class DigestComposerAgent:
    """Agent for composing news digests."""

    def __init__(self):
        """Initialize the composer with LLM client."""
        self.client = OpenAI(
            api_key="not-needed",
            base_url=os.environ.get(
                "VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1"
            ),
        )
        self.model = os.environ.get("VLLM_MODEL", "Qwen/Qwen3-14B-FP8")

    def compose_digest(
        self,
        articles: list[ProcessedArticle],
        trends: list[TrendingTopic],
        period_start: datetime,
        period_end: datetime,
    ) -> NewsDigest:
        """
        Compose a complete news digest.

        Args:
            articles: Processed articles to include
            trends: Identified trends
            period_start: Start of the digest period
            period_end: End of the digest period

        Returns:
            Formatted NewsDigest
        """
        # Sort articles by importance
        sorted_articles = sorted(articles, key=lambda a: a.importance_score, reverse=True)

        # Select top articles (variable based on importance)
        high_importance = [a for a in sorted_articles if a.importance_score >= 7]
        medium_importance = [a for a in sorted_articles if 5 <= a.importance_score < 7]

        # Include all high importance + some medium
        selected_articles = high_importance + medium_importance[:5]

        if not selected_articles:
            # If nothing notable, take top 5 by score
            selected_articles = sorted_articles[:5]

        # Generate the summary
        headline_summary = self._generate_summary(selected_articles, trends)

        # Get unique sources
        sources_used = list(set(a.source for a in selected_articles))

        digest = NewsDigest(
            digest_id=f"digest-{uuid4().hex[:8]}",
            created_at=datetime.utcnow(),
            period_start=period_start,
            period_end=period_end,
            headline_summary=headline_summary,
            trending_topics=trends[:5],  # Top 5 trends
            total_articles=len(selected_articles),
            sources_used=sources_used,
        )

        logger.info(f"Composed digest {digest.digest_id} with {len(selected_articles)} articles")
        return digest

    def _generate_summary(
        self,
        articles: list[ProcessedArticle],
        trends: list[TrendingTopic],
    ) -> str:
        """
        Generate a cohesive summary of the articles using LLM.

        Args:
            articles: Articles to summarize
            trends: Current trends

        Returns:
            Formatted summary string with embedded citations
        """
        # Format articles for prompt
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"""
{i}. {article.title}
   Source: {article.source}
   URL: {article.url}
   Category: {article.category.value}
   Importance: {article.importance_score}/10
   Summary: {article.ai_summary or article.original_summary}
"""

        # Format trends
        trends_text = (
            ", ".join(f"{t.topic} ({t.status.value})" for t in trends[:5])
            or "No significant trends"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
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
            # Strip any thinking tags that might appear
            import re

            summary = re.sub(r"<think>.*?</think>", "", summary, flags=re.DOTALL)
            return summary.strip()

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            # Fallback to basic formatting
            return self._fallback_summary(articles)

    def _fallback_summary(self, articles: list[ProcessedArticle]) -> str:
        """
        Create a basic summary without LLM (fallback).

        Args:
            articles: Articles to summarize

        Returns:
            Basic formatted summary
        """
        lines = ["**Today's AI News Highlights:**\n"]

        for article in articles[:5]:
            lines.append(
                f"- [{article.title}]({article.url}) ({article.source}): "
                f"{article.ai_summary or article.original_summary[:150]}..."
            )

        return "\n".join(lines)

    def format_for_discord(self, digest: NewsDigest) -> str:
        """
        Format the digest for Discord posting.

        Args:
            digest: The composed digest

        Returns:
            Discord-formatted string (markdown)
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
        hot_trends = [t for t in digest.trending_topics if t.status == TrendStatus.HOT]
        rising_trends = [t for t in digest.trending_topics if t.status == TrendStatus.RISING]

        if hot_trends:
            lines.append("**Trending Topics:**")
            for trend in hot_trends[:3]:
                lines.append(f"- {trend.topic} (covered by {len(trend.sources)} sources)")
            lines.append("")

        if rising_trends:
            lines.append("**Emerging Themes:**")
            for trend in rising_trends[:2]:
                lines.append(f"- {trend.topic}")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append(f"*{digest.total_articles} articles from {len(digest.sources_used)} sources*")

        return "\n".join(lines)

    def format_breaking_alert(
        self,
        article: ProcessedArticle,
        reason: str,
    ) -> str:
        """
        Format a breaking news alert for Discord.

        Args:
            article: The breaking news article
            reason: Why this is breaking news

        Returns:
            Discord-formatted alert string
        """
        lines = [
            "**BREAKING: AI News Alert**",
            "",
            f"**{article.title}**",
            "",
            f"{article.ai_summary or article.original_summary}",
            "",
            f"[Read more]({article.url}) | Source: {article.source}",
            "",
            f"*{reason}*",
        ]

        return "\n".join(lines)
