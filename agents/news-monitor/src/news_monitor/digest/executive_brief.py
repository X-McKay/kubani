"""
Executive Brief Digest Format.

Generates structured, professional news digests in the "5-minute Executive Brief" format:
- Topline summary (key takeaways)
- Research deep dives with practical implications
- Tools/MCP servers mini-briefs
- Patterns & practices
- Security alerts
- Trends with momentum indicators

This format is designed for busy professionals who need actionable intelligence.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from openai import OpenAI

from news_monitor.models import ProcessedArticle, TrendingTopic, TrendStatus

logger = logging.getLogger(__name__)


class ContentCategory(Enum):
    """Categories for executive brief sections."""

    RESEARCH = "research"
    TOOLS = "tools"
    PATTERNS = "patterns"
    SECURITY = "security"
    MODELS = "models"
    COMPANY = "company"


class NewsUrgency(Enum):
    """Urgency level for news items."""

    BREAKING = "breaking"  # Immediate attention required
    HIGH = "high"  # Should know today
    NORMAL = "normal"  # Can wait for digest
    LOW = "low"  # Nice to know


@dataclass
class DeepDive:
    """A deep dive section for research papers or significant developments."""

    title: str
    source: str
    source_url: str
    one_paragraph_summary: str
    key_takeaways: list[str]
    practical_implications: list[str]
    caveats: list[str] = field(default_factory=list)
    reference_id: str = ""  # e.g., arXiv:2601.01234


@dataclass
class MiniBrief:
    """A mini-brief for tools, patterns, or other items."""

    title: str
    category: ContentCategory
    what_it_is: str
    why_interesting: str
    who_its_for: str
    maturity_signals: str = ""
    quick_takeaway: str = ""
    url: str = ""


@dataclass
class SecurityAlert:
    """A security vulnerability or alert."""

    title: str
    impact: str
    affected: str
    mitigation: str
    reference: str = ""  # CVE number or advisory


@dataclass
class TrendIndicator:
    """A trend with momentum indicator."""

    topic: str
    direction: str  # ↑ rising, → stable, ↓ declining
    description: str


@dataclass
class ExecutiveBrief:
    """Complete executive brief digest."""

    period_start: datetime
    period_end: datetime
    topline: list[str]  # 3-5 key takeaways
    deep_dives: list[DeepDive]
    tools_briefs: list[MiniBrief]
    patterns_briefs: list[MiniBrief]
    security_alerts: list[SecurityAlert]
    model_updates: list[str]
    company_news: list[str]
    trends: list[TrendIndicator]
    total_sources: int = 0

    def to_discord_message(self) -> str:
        """Format as a Discord message."""
        lines = []

        # Header
        time_range = f"{self.period_start.strftime('%b %d, %Y')} · {self.period_start.strftime('%H:%M')}–{self.period_end.strftime('%H:%M')} ET"
        lines.append("## 📰 5-minute Executive Brief")
        lines.append(f"*{time_range}*")
        lines.append("")

        # Topline
        lines.append("### Topline")
        for item in self.topline:
            lines.append(f"• {item}")
        lines.append("")

        # Research Deep Dives
        if self.deep_dives:
            lines.append("### Research (arXiv) — Deep Dives")
            for i, dive in enumerate(self.deep_dives, 1):
                lines.append(f"**Paper {i} — {dive.title}**")
                lines.append("*One-paragraph summary:*")
                lines.append(f"{dive.one_paragraph_summary}")
                if dive.reference_id:
                    lines.append(f"({dive.reference_id})")
                lines.append("")
                lines.append("*Key takeaways*")
                for takeaway in dive.key_takeaways:
                    lines.append(f"• {takeaway}")
                lines.append("")
                if dive.practical_implications:
                    lines.append("*Practical implications (what to do this week)*")
                    for impl in dive.practical_implications:
                        lines.append(f"• {impl}")
                    lines.append("")
                if dive.caveats:
                    lines.append("*Caveats / open questions*")
                    for caveat in dive.caveats:
                        lines.append(f"• {caveat}")
                    lines.append("")

        # Tools / MCP servers
        if self.tools_briefs:
            lines.append("### Tools / MCP servers / repos (mini-briefs)")
            for brief in self.tools_briefs:
                lines.append(f"**Tool — {brief.title}**")
                lines.append(f"*What it is:* {brief.what_it_is}")
                lines.append(f"*Why it's interesting:* {brief.why_interesting}")
                lines.append(f"*Who it's for:* {brief.who_its_for}")
                if brief.maturity_signals:
                    lines.append(f"*Maturity signals:* {brief.maturity_signals}")
                if brief.quick_takeaway:
                    lines.append(f"*Quick takeaway:* {brief.quick_takeaway}")
                lines.append("")

        # Patterns & practices
        if self.patterns_briefs:
            lines.append("### Patterns & practices (short but not shallow)")
            for brief in self.patterns_briefs:
                lines.append(f"**{brief.title}**")
                lines.append(f"{brief.what_it_is}")
                if brief.quick_takeaway:
                    lines.append("")
                    lines.append("*Steal this pattern*")
                    lines.append(brief.quick_takeaway)
                lines.append("")

        # Models
        lines.append("### Models")
        if self.model_updates:
            for update in self.model_updates:
                lines.append(f"• {update}")
        else:
            lines.append("No notable model releases in this window.")
        lines.append("")

        # Company news
        lines.append("### Company news")
        if self.company_news:
            for news in self.company_news:
                lines.append(f"• {news}")
        else:
            lines.append("No notable updates in the last 4 hours.")
        lines.append("")

        # Security
        if self.security_alerts:
            lines.append("### Security & vulnerabilities (mini-brief)")
            for alert in self.security_alerts:
                lines.append(f"**{alert.title}**")
                lines.append(f"*Impact:* {alert.impact}")
                lines.append(f"*Affected:* {alert.affected}")
                lines.append(f"*Mitigation:* {alert.mitigation}")
                if alert.reference:
                    lines.append(f"({alert.reference})")
                lines.append("")

        # Trends
        if self.trends:
            lines.append("### Trends (momentum)")
            for trend in self.trends:
                lines.append(f"{trend.direction} {trend.topic} ({trend.description})")
            lines.append("")

        return "\n".join(lines)

    def to_granular_messages(self) -> list[dict[str, Any]]:
        """
        Split into granular messages for individual posting.

        Returns list of dicts with 'category', 'content', and 'reactions' fields.
        Reactions are suggested emoji for feedback.
        """
        messages = []

        # Topline as its own message
        if self.topline:
            topline_content = "## 📰 Executive Brief Topline\n"
            topline_content += f"*{self.period_start.strftime('%b %d, %Y %H:%M')} ET*\n\n"
            for item in self.topline:
                topline_content += f"• {item}\n"
            messages.append(
                {
                    "category": "topline",
                    "content": topline_content,
                    "reactions": ["👍", "🔥", "🤔"],
                }
            )

        # Each deep dive as its own message
        for i, dive in enumerate(self.deep_dives):
            content = f"## 📚 Research Deep Dive #{i + 1}\n"
            content += f"**{dive.title}**\n\n"
            content += f"{dive.one_paragraph_summary}\n"
            if dive.reference_id:
                content += f"*{dive.reference_id}*\n"
            content += "\n**Key takeaways:**\n"
            for takeaway in dive.key_takeaways:
                content += f"• {takeaway}\n"
            if dive.practical_implications:
                content += "\n**What to do this week:**\n"
                for impl in dive.practical_implications:
                    content += f"• {impl}\n"
            messages.append(
                {
                    "category": "research",
                    "content": content,
                    "reactions": ["📖", "💡", "🎯", "❓"],
                }
            )

        # Tools as individual messages
        for brief in self.tools_briefs:
            content = "## 🔧 Tool Spotlight\n"
            content += f"**{brief.title}**\n\n"
            content += f"*What:* {brief.what_it_is}\n"
            content += f"*Why:* {brief.why_interesting}\n"
            content += f"*For:* {brief.who_its_for}\n"
            if brief.quick_takeaway:
                content += f"\n💡 {brief.quick_takeaway}"
            messages.append(
                {
                    "category": "tools",
                    "content": content,
                    "reactions": ["🛠️", "⭐", "📌", "🔜"],
                }
            )

        # Patterns
        for brief in self.patterns_briefs:
            content = "## 🎯 Pattern\n"
            content += f"**{brief.title}**\n\n"
            content += f"{brief.what_it_is}\n"
            if brief.quick_takeaway:
                content += f"\n*Steal this:* {brief.quick_takeaway}"
            messages.append(
                {
                    "category": "patterns",
                    "content": content,
                    "reactions": ["✅", "🔄", "📝"],
                }
            )

        # Security alerts
        for alert in self.security_alerts:
            content = "## ⚠️ Security Alert\n"
            content += f"**{alert.title}**\n\n"
            content += f"*Impact:* {alert.impact}\n"
            content += f"*Affected:* {alert.affected}\n"
            content += f"*Action:* {alert.mitigation}\n"
            if alert.reference:
                content += f"\n{alert.reference}"
            messages.append(
                {
                    "category": "security",
                    "content": content,
                    "reactions": ["🚨", "✅", "🔍"],
                }
            )

        # Trends summary
        if self.trends:
            content = "## 📈 Trends\n"
            for trend in self.trends:
                content += f"{trend.direction} **{trend.topic}** — {trend.description}\n"
            messages.append(
                {
                    "category": "trends",
                    "content": content,
                    "reactions": ["📊", "🔮"],
                }
            )

        return messages


class ExecutiveBriefComposer:
    """Composes executive briefs from processed articles."""

    CLASSIFICATION_PROMPT = """Classify this news item for an executive brief.

Title: {title}
Source: {source}
Summary: {summary}
Category: {category}

Determine:
1. urgency: "breaking" (immediate), "high" (today), "normal" (digest), "low" (nice to know)
2. content_type: "research", "tools", "patterns", "security", "models", "company"
3. is_deep_dive_worthy: true if it's a research paper or significant development worth a deep dive
4. relevance_score: 0-10 for AI/ML engineering relevance

Respond as JSON:
{{
    "urgency": "<urgency>",
    "content_type": "<type>",
    "is_deep_dive_worthy": <true/false>,
    "relevance_score": <0-10>
}}"""

    DEEP_DIVE_PROMPT = """Create a deep dive analysis for this research/development.

Title: {title}
Source: {source}
URL: {url}
Full content: {content}

Generate a structured deep dive with:
1. One-paragraph summary (what the paper/development argues or does)
2. 3-4 key takeaways (bullet points)
3. 2-3 practical implications (what to do this week)
4. 1-2 caveats or open questions

Respond as JSON:
{{
    "one_paragraph_summary": "<summary>",
    "key_takeaways": ["<takeaway1>", ...],
    "practical_implications": ["<implication1>", ...],
    "caveats": ["<caveat1>", ...]
}}"""

    TOPLINE_PROMPT = """Generate 3-5 topline bullet points for an executive brief.

Articles covered:
{articles}

Trends observed:
{trends}

Create concise, impactful topline statements that:
1. Highlight the most important developments
2. Are actionable or insightful
3. Cover different aspects (research, tools, security, etc.)

Respond as JSON:
{{
    "toplines": ["<topline1>", "<topline2>", ...]
}}"""

    def __init__(self):
        """Initialize the composer."""
        self.client = OpenAI(
            api_key="not-needed",  # pragma: allowlist secret
            base_url=os.environ.get(
                "VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1"
            ),
        )
        self.model = os.environ.get("VLLM_MODEL", "nvidia/Qwen3-14B-FP4")

    async def compose_executive_brief(
        self,
        articles: list[ProcessedArticle],
        trends: list[TrendingTopic],
        period_start: datetime,
        period_end: datetime,
    ) -> ExecutiveBrief:
        """
        Compose a full executive brief from articles.

        Args:
            articles: Processed articles
            trends: Identified trends
            period_start: Start of period
            period_end: End of period

        Returns:
            ExecutiveBrief
        """
        # Classify articles
        classified = await self._classify_articles(articles)

        # Filter by relevance
        relevant = [c for c in classified if c["relevance_score"] >= 5]

        # Separate by type
        research = [c for c in relevant if c["content_type"] == "research"]
        tools = [c for c in relevant if c["content_type"] == "tools"]
        patterns = [c for c in relevant if c["content_type"] == "patterns"]
        security = [c for c in relevant if c["content_type"] == "security"]
        models = [c for c in relevant if c["content_type"] == "models"]
        company = [c for c in relevant if c["content_type"] == "company"]

        # Generate deep dives for worthy items
        deep_dives = []
        deep_dive_worthy = [c for c in research if c.get("is_deep_dive_worthy")]
        for item in deep_dive_worthy[:2]:  # Max 2 deep dives
            dive = await self._generate_deep_dive(item["article"])
            if dive:
                deep_dives.append(dive)

        # Generate mini-briefs
        tools_briefs = [self._create_tool_brief(c["article"]) for c in tools[:3]]
        patterns_briefs = [self._create_pattern_brief(c["article"]) for c in patterns[:2]]

        # Security alerts
        security_alerts = [self._create_security_alert(c["article"]) for c in security]

        # Model and company updates
        model_updates = [c["article"].title for c in models]
        company_updates = [c["article"].title for c in company]

        # Generate toplines
        toplines = await self._generate_toplines(relevant, trends)

        # Convert trends
        trend_indicators = [
            TrendIndicator(
                topic=t.topic,
                direction="↑"
                if t.status == TrendStatus.HOT
                else "→"
                if t.status == TrendStatus.RISING
                else "↓",
                description=self._get_trend_description(t),
            )
            for t in trends[:5]
        ]

        return ExecutiveBrief(
            period_start=period_start,
            period_end=period_end,
            topline=toplines,
            deep_dives=deep_dives,
            tools_briefs=tools_briefs,
            patterns_briefs=patterns_briefs,
            security_alerts=security_alerts,
            model_updates=model_updates,
            company_news=company_updates,
            trends=trend_indicators,
            total_sources=len({a.source for a in articles}),
        )

    async def _classify_articles(
        self,
        articles: list[ProcessedArticle],
    ) -> list[dict[str, Any]]:
        """Classify articles by type and relevance."""
        classified = []

        for article in articles:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": self.CLASSIFICATION_PROMPT.format(
                                title=article.title,
                                source=article.source,
                                summary=article.ai_summary or article.original_summary,
                                category=article.category.value,
                            ),
                        },
                    ],
                    temperature=0.2,
                    max_tokens=200,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )

                content = response.choices[0].message.content
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)

                # Parse JSON
                json_match = re.search(r"\{.*\}", content, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    data["article"] = article
                    classified.append(data)

            except Exception as e:
                logger.warning(f"Failed to classify article: {e}")
                # Default classification
                classified.append(
                    {
                        "article": article,
                        "urgency": "normal",
                        "content_type": "company",
                        "is_deep_dive_worthy": False,
                        "relevance_score": article.importance_score,
                    }
                )

        return classified

    async def _generate_deep_dive(self, article: ProcessedArticle) -> DeepDive | None:
        """Generate a deep dive for an article."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": self.DEEP_DIVE_PROMPT.format(
                            title=article.title,
                            source=article.source,
                            url=article.url,
                            content=article.ai_summary or article.original_summary,
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=1000,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            content = response.choices[0].message.content
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)

            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return DeepDive(
                    title=article.title,
                    source=article.source,
                    source_url=article.url,
                    one_paragraph_summary=data.get("one_paragraph_summary", ""),
                    key_takeaways=data.get("key_takeaways", []),
                    practical_implications=data.get("practical_implications", []),
                    caveats=data.get("caveats", []),
                )

        except Exception as e:
            logger.warning(f"Failed to generate deep dive: {e}")

        return None

    async def _generate_toplines(
        self,
        classified: list[dict[str, Any]],
        trends: list[TrendingTopic],
    ) -> list[str]:
        """Generate topline summary points."""
        try:
            articles_text = "\n".join(
                f"- {c['article'].title} ({c['content_type']})" for c in classified[:10]
            )
            trends_text = ", ".join(t.topic for t in trends[:5])

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": self.TOPLINE_PROMPT.format(
                            articles=articles_text,
                            trends=trends_text,
                        ),
                    },
                ],
                temperature=0.4,
                max_tokens=500,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            content = response.choices[0].message.content
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)

            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("toplines", [])

        except Exception as e:
            logger.warning(f"Failed to generate toplines: {e}")

        # Fallback
        return [c["article"].title for c in classified[:3]]

    def _create_tool_brief(self, article: ProcessedArticle) -> MiniBrief:
        """Create a mini-brief for a tool."""
        return MiniBrief(
            title=article.title,
            category=ContentCategory.TOOLS,
            what_it_is=article.ai_summary or article.original_summary[:200],
            why_interesting="Relevant to AI/ML engineering workflows",
            who_its_for="Developers and platform teams",
            url=article.url,
        )

    def _create_pattern_brief(self, article: ProcessedArticle) -> MiniBrief:
        """Create a mini-brief for a pattern."""
        return MiniBrief(
            title=article.title,
            category=ContentCategory.PATTERNS,
            what_it_is=article.ai_summary or article.original_summary[:200],
            why_interesting="Emerging best practice",
            who_its_for="Engineering teams",
            url=article.url,
        )

    def _create_security_alert(self, article: ProcessedArticle) -> SecurityAlert:
        """Create a security alert from an article."""
        return SecurityAlert(
            title=article.title,
            impact="See article for details",
            affected="Check vendor advisory",
            mitigation="Review and patch as needed",
            reference=article.url,
        )

    def _get_trend_description(self, trend: TrendingTopic) -> str:
        """Get a description for a trend."""
        if trend.status == TrendStatus.HOT:
            return "high activity"
        elif trend.status == TrendStatus.RISING:
            return "gaining momentum"
        else:
            return "stable"
