"""
Breaking News Handler.

Handles urgent news that should be posted immediately to a dedicated channel:
- High-impact security vulnerabilities
- Major model releases
- Significant company announcements
- Critical research breakthroughs

Features:
- Urgency classification
- Relevance filtering to avoid noise
- Rate limiting to prevent spam
- Deduplication
"""

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from openai import OpenAI

from news_monitor.models import ArticleCategory, ProcessedArticle

logger = logging.getLogger(__name__)


@dataclass
class BreakingNewsItem:
    """A breaking news item."""

    article: ProcessedArticle
    urgency_score: float  # 0-10
    urgency_reason: str
    category: str  # security, model, company, research
    impact_summary: str
    action_required: str | None = None
    posted_at: datetime | None = None
    message_id: str | None = None


class BreakingNewsClassifier:
    """Classifies news items for breaking news potential."""

    CLASSIFICATION_PROMPT = """Evaluate if this news item qualifies as "breaking news" for an AI/ML engineering audience.

Title: {title}
Source: {source}
Category: {category}
Summary: {summary}

Breaking news criteria:
- Major security vulnerability affecting AI/ML tools or infrastructure
- Significant model release from major labs (OpenAI, Anthropic, Google, Meta, etc.)
- Critical company news (acquisitions, major pivots, shutdowns)
- Research breakthrough with immediate practical implications

Evaluate:
1. Is this truly urgent/breaking? (not just interesting)
2. Is it relevant to AI/ML engineers specifically?
3. What immediate action (if any) should readers take?

Respond as JSON:
{{
    "is_breaking": <true/false>,
    "urgency_score": <0-10>,
    "urgency_reason": "<why this is urgent>",
    "category": "<security|model|company|research|other>",
    "impact_summary": "<one sentence impact>",
    "action_required": "<immediate action or null>",
    "relevance_score": <0-10 for AI/ML engineering relevance>
}}"""

    def __init__(self):
        """Initialize the classifier."""
        self.client = OpenAI(
            api_key="not-needed",  # pragma: allowlist secret
            base_url=os.environ.get(
                "VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1"
            ),
        )
        self.model = os.environ.get("VLLM_MODEL", "nvidia/Qwen3-14B-FP4")

    async def classify(self, article: ProcessedArticle) -> BreakingNewsItem | None:
        """
        Classify an article for breaking news potential.

        Returns BreakingNewsItem if it qualifies, None otherwise.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": self.CLASSIFICATION_PROMPT.format(
                            title=article.title,
                            source=article.source,
                            category=article.category.value,
                            summary=article.ai_summary or article.original_summary,
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=300,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            content = response.choices[0].message.content
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)

            # Parse JSON
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                import json

                data = json.loads(json_match.group())

                # Check if it qualifies
                if (
                    data.get("is_breaking", False)
                    and data.get("urgency_score", 0) >= 7
                    and data.get("relevance_score", 0) >= 6
                ):
                    return BreakingNewsItem(
                        article=article,
                        urgency_score=data["urgency_score"],
                        urgency_reason=data.get("urgency_reason", ""),
                        category=data.get("category", "other"),
                        impact_summary=data.get("impact_summary", ""),
                        action_required=data.get("action_required"),
                    )

        except Exception as e:
            logger.warning(f"Failed to classify breaking news: {e}")

        return None


class BreakingNewsHandler:
    """
    Handles breaking news detection and posting.

    Features:
    - Rate limiting (max N posts per hour)
    - Deduplication (by content hash)
    - Separate channel posting
    """

    def __init__(
        self,
        discord_webhook_url: str | None = None,
        max_per_hour: int = 5,
        min_interval_minutes: int = 10,
    ):
        """Initialize the handler."""
        self.discord_webhook_url = discord_webhook_url or os.environ.get(
            "DISCORD_BREAKING_NEWS_WEBHOOK"
        )
        self.max_per_hour = max_per_hour
        self.min_interval = timedelta(minutes=min_interval_minutes)
        self.classifier = BreakingNewsClassifier()

        # State
        self._posted_hashes: set[str] = set()
        self._recent_posts: list[datetime] = []
        self._last_post_time: datetime | None = None

    def _get_content_hash(self, article: ProcessedArticle) -> str:
        """Get a hash of the article content for deduplication."""
        content = f"{article.title}:{article.source}:{article.url}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _is_rate_limited(self) -> bool:
        """Check if we're rate limited."""
        now = datetime.now(UTC)

        # Check minimum interval
        if self._last_post_time and now - self._last_post_time < self.min_interval:
            return True

        # Check hourly limit
        hour_ago = now - timedelta(hours=1)
        self._recent_posts = [t for t in self._recent_posts if t > hour_ago]
        return len(self._recent_posts) >= self.max_per_hour

    def _is_duplicate(self, article: ProcessedArticle) -> bool:
        """Check if this article was already posted."""
        content_hash = self._get_content_hash(article)
        return content_hash in self._posted_hashes

    async def process_article(
        self,
        article: ProcessedArticle,
    ) -> BreakingNewsItem | None:
        """
        Process an article for breaking news.

        Returns the BreakingNewsItem if posted, None otherwise.
        """
        # Check for duplicates
        if self._is_duplicate(article):
            logger.debug(f"Skipping duplicate: {article.title[:50]}...")
            return None

        # Check rate limiting
        if self._is_rate_limited():
            logger.debug("Rate limited, skipping breaking news check")
            return None

        # Classify
        item = await self.classifier.classify(article)
        if not item:
            return None

        # Post
        success = await self._post_to_discord(item)
        if success:
            # Update state
            content_hash = self._get_content_hash(article)
            self._posted_hashes.add(content_hash)
            self._recent_posts.append(datetime.now(UTC))
            self._last_post_time = datetime.now(UTC)
            item.posted_at = datetime.now(UTC)
            return item

        return None

    async def _post_to_discord(self, item: BreakingNewsItem) -> bool:
        """Post breaking news to Discord."""
        if not self.discord_webhook_url:
            logger.warning("No Discord webhook configured for breaking news")
            return False

        try:
            import httpx

            # Format message
            message = self._format_message(item)

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.discord_webhook_url,
                    json={"content": message},
                    timeout=30.0,
                )

                if response.status_code in (200, 204):
                    logger.info(f"Posted breaking news: {item.article.title[:50]}...")
                    return True
                else:
                    logger.error(f"Failed to post breaking news: {response.status_code}")

        except Exception as e:
            logger.error(f"Error posting breaking news: {e}")

        return False

    def _format_message(self, item: BreakingNewsItem) -> str:
        """Format a breaking news message for Discord."""
        emoji_map = {
            "security": "🚨",
            "model": "🤖",
            "company": "🏢",
            "research": "📚",
            "other": "📰",
        }
        emoji = emoji_map.get(item.category, "📰")

        lines = [
            f"{emoji} **BREAKING: {item.article.title}**",
            "",
            f"*{item.impact_summary}*",
            "",
            f"**Source:** {item.article.source}",
            f"**Urgency:** {item.urgency_reason}",
        ]

        if item.action_required:
            lines.extend(
                [
                    "",
                    f"⚡ **Action Required:** {item.action_required}",
                ]
            )

        lines.extend(
            [
                "",
                f"[Read more]({item.article.url})",
                "",
                "React: 🔥 Important | 👀 Following | ❓ Need more info",
            ]
        )

        return "\n".join(lines)


class RelevanceFilter:
    """
    Filters news for relevance to avoid noise.

    Uses a combination of:
    - Keyword matching
    - Source reputation
    - Category filtering
    - LLM-based relevance scoring
    """

    # High-value sources for AI/ML news
    TRUSTED_SOURCES = {
        "arxiv",
        "openai",
        "anthropic",
        "google ai",
        "deepmind",
        "meta ai",
        "hugging face",
        "nvidia",
        "microsoft research",
        "pytorch",
        "tensorflow",
    }

    # Keywords that indicate high relevance
    HIGH_RELEVANCE_KEYWORDS = {
        "llm",
        "large language model",
        "gpt",
        "claude",
        "gemini",
        "transformer",
        "fine-tuning",
        "rag",
        "retrieval augmented",
        "agent",
        "mcp",
        "model context protocol",
        "embedding",
        "vector",
        "qdrant",
        "pinecone",
        "langchain",
        "llamaindex",
        "vllm",
        "ollama",
        "mlops",
        "inference",
        "quantization",
    }

    # Keywords that indicate low relevance (noise)
    LOW_RELEVANCE_KEYWORDS = {
        "stock price",
        "earnings call",
        "quarterly results",
        "investor",
        "market cap",
        "ipo",
        "lawsuit",
        "celebrity",
        "entertainment",
    }

    def __init__(self, min_relevance_score: float = 0.5):
        """Initialize the filter."""
        self.min_relevance_score = min_relevance_score

    def is_relevant(self, article: ProcessedArticle) -> tuple[bool, float]:
        """
        Check if an article is relevant.

        Returns (is_relevant, score).
        """
        score = 0.5  # Base score

        title_lower = article.title.lower()
        summary_lower = (article.ai_summary or article.original_summary or "").lower()
        content = f"{title_lower} {summary_lower}"

        # Check source
        source_lower = article.source.lower()
        if any(s in source_lower for s in self.TRUSTED_SOURCES):
            score += 0.2

        # Check high relevance keywords
        high_matches = sum(1 for kw in self.HIGH_RELEVANCE_KEYWORDS if kw in content)
        score += min(high_matches * 0.1, 0.3)

        # Check low relevance keywords (penalty)
        low_matches = sum(1 for kw in self.LOW_RELEVANCE_KEYWORDS if kw in content)
        score -= min(low_matches * 0.15, 0.4)

        # Category bonus
        if article.category in (ArticleCategory.RESEARCH, ArticleCategory.PRODUCT):
            score += 0.1

        # Clamp score
        score = max(0.0, min(1.0, score))

        return score >= self.min_relevance_score, score

    def filter_articles(
        self,
        articles: list[ProcessedArticle],
    ) -> list[tuple[ProcessedArticle, float]]:
        """
        Filter a list of articles for relevance.

        Returns list of (article, score) tuples for relevant articles.
        """
        relevant = []
        for article in articles:
            is_relevant, score = self.is_relevant(article)
            if is_relevant:
                relevant.append((article, score))

        # Sort by score descending
        relevant.sort(key=lambda x: x[1], reverse=True)
        return relevant
