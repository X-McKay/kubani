"""
News Explorer Agent - Source discovery and coverage gap analysis.

The News Explorer agent analyzes coverage patterns and discovers new sources:
1. Analyzes recent articles to find coverage gaps
2. Identifies trending topics with limited source coverage
3. Discovers potential RSS feeds to fill gaps
4. Submits source proposals for human approval

This enables continuous expansion of the news monitoring coverage.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from core_agents import create_agent
from core_agents.approvals import ApprovalRequest, ApprovalStatus, get_discord_approver
from core_agents.events import EventBus, EventType, get_event_bus
from core_agents.observability import record_event_published
from news_monitor.feeds import AI_KEYWORDS, FEEDS
from news_monitor.memory import _extract_search_results, get_memory

logger = logging.getLogger(__name__)


@dataclass
class CoverageGap:
    """A topic or entity with insufficient source coverage."""

    topic: str
    source_count: int
    article_count: int
    sources: list[str] = field(default_factory=list)
    importance_score: float = 0.0


class SourceProposal(BaseModel):
    """A proposed new RSS feed source."""

    name: str = Field(description="Human-readable name for the source")
    url: str = Field(description="RSS feed URL")
    category: str = Field(description="Feed category")
    topic: str = Field(description="Primary topic this covers")
    priority: int = Field(default=5, ge=1, le=10)
    reason: str = Field(description="Why this source should be added")
    discovered_via: str = Field(
        default="manual",
        description="How this source was discovered",
    )


class SourceValidation(BaseModel):
    """Validation result for a proposed source."""

    valid: bool = Field(description="Whether the source is valid")
    url: str
    title: str | None = None
    article_count: int = 0
    update_frequency: str | None = None
    sample_titles: list[str] = Field(default_factory=list)
    error: str | None = None


class NewsExplorerAgent:
    """
    Discovers new RSS sources based on coverage gaps.

    The News Explorer analyzes article patterns to find:
    - Topics with few covering sources
    - Trending entities without dedicated feeds
    - Categories underrepresented in current sources
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        source_name: str = "news-explorer",
        min_sources_for_gap: int = 2,
        lookback_days: int = 7,
    ):
        """
        Initialize the News Explorer agent.

        Args:
            event_bus: Event bus for publishing events
            source_name: Source identifier for events
            min_sources_for_gap: Minimum sources before a topic is a "gap"
            lookback_days: Days to look back for coverage analysis
        """
        self._event_bus = event_bus
        self.source_name = source_name
        self.min_sources_for_gap = min_sources_for_gap
        self.lookback_days = lookback_days
        self._discovery_agent = None
        self._memory = None

    async def _ensure_initialized(self) -> None:
        """Lazy initialization of dependencies."""
        if self._event_bus is None:
            self._event_bus = await get_event_bus()
        if self._memory is None:
            try:
                # get_memory() is synchronous - returns Memory singleton
                self._memory = get_memory()
            except Exception as e:
                logger.warning(f"Memory not available: {e}")

    def _get_discovery_agent(self):
        """Get or create the LLM agent for source discovery."""
        if self._discovery_agent is None:
            try:
                self._discovery_agent = create_agent(
                    name="source_discoverer",
                    system_prompt=DISCOVERY_PROMPT,
                    tools=[],
                )
            except Exception as e:
                logger.warning(f"Could not create discovery agent: {e}")
        return self._discovery_agent

    async def analyze_coverage_gaps(self) -> list[CoverageGap]:
        """
        Analyze recent articles to find coverage gaps.

        A coverage gap is a topic that appears frequently but
        is covered by few unique sources.

        Returns:
            List of coverage gaps sorted by importance
        """
        await self._ensure_initialized()

        # Try to get articles from memory
        articles = await self._get_recent_articles()

        if not articles:
            logger.info("No recent articles found for gap analysis")
            return []

        # Build topic -> sources mapping
        topic_sources: dict[str, set[str]] = defaultdict(set)
        topic_counts: dict[str, int] = defaultdict(int)

        for article in articles:
            # Extract entities/topics from article
            entities = article.get("entities", [])
            source = article.get("source", "unknown")

            for entity in entities:
                if self._is_important_topic(entity):
                    topic_sources[entity].add(source)
                    topic_counts[entity] += 1

        # Find gaps (topics with many articles but few sources)
        gaps = []
        for topic, sources in topic_sources.items():
            source_count = len(sources)
            article_count = topic_counts[topic]

            # A gap has many mentions but few sources
            if source_count < self.min_sources_for_gap and article_count >= 3:
                importance = article_count / max(source_count, 1)
                gaps.append(
                    CoverageGap(
                        topic=topic,
                        source_count=source_count,
                        article_count=article_count,
                        sources=list(sources),
                        importance_score=importance,
                    )
                )

        # Sort by importance (most important first)
        gaps.sort(key=lambda g: g.importance_score, reverse=True)

        logger.info(f"Found {len(gaps)} coverage gaps")
        return gaps[:10]  # Limit to top 10

    def _is_important_topic(self, topic: str) -> bool:
        """Check if a topic is worth tracking."""
        # Skip very short or very long topics
        if len(topic) < 3 or len(topic) > 50:
            return False

        # Skip common stopwords
        stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for"}
        if topic.lower() in stopwords:
            return False

        # Prefer AI-related topics
        return any(kw.lower() in topic.lower() for kw in AI_KEYWORDS[:20])

    async def _get_recent_articles(self) -> list[dict[str, Any]]:
        """Get recent articles from memory."""
        if self._memory is None:
            return []

        try:
            # Query memory for recent articles
            # user_id must match what's used in store_article()
            raw_results = self._memory.search(
                query="recent AI news articles",
                user_id="news-monitor-articles",
                limit=100,
            )

            # Use helper to handle different mem0 result formats
            articles = []
            for result in _extract_search_results(raw_results):
                # Parse memory result into article dict
                metadata = result.get("metadata", {})
                if metadata.get("type") == "article":
                    articles.append(metadata)

            return articles
        except Exception as e:
            logger.warning(f"Failed to get articles from memory: {e}")
            return []

    async def discover_sources(self, gap: CoverageGap) -> list[SourceProposal]:
        """
        Discover potential RSS sources to fill a coverage gap.

        Args:
            gap: The coverage gap to fill

        Returns:
            List of source proposals
        """
        await self._ensure_initialized()

        proposals = []

        # Try LLM-based discovery
        agent = self._get_discovery_agent()
        if agent:
            try:
                llm_proposals = await self._llm_discover(gap)
                proposals.extend(llm_proposals)
            except Exception as e:
                logger.warning(f"LLM discovery failed: {e}")

        # Add template-based suggestions
        template_proposals = self._template_discover(gap)
        proposals.extend(template_proposals)

        # Deduplicate by URL
        seen_urls = set()
        unique_proposals = []
        for p in proposals:
            if p.url not in seen_urls:
                seen_urls.add(p.url)
                unique_proposals.append(p)

        return unique_proposals

    async def _llm_discover(self, gap: CoverageGap) -> list[SourceProposal]:
        """Use LLM to suggest sources for a gap."""
        existing_sources = [f.name for f in FEEDS]

        prompt = f"""
        Find RSS feeds that cover this topic: "{gap.topic}"

        Current coverage:
        - {gap.article_count} articles found
        - Only {gap.source_count} sources: {", ".join(gap.sources)}

        Existing sources we already have:
        {", ".join(existing_sources[:10])}

        Suggest 2-3 RSS feeds that would improve coverage.
        For each, provide:
        SOURCE_NAME: Human readable name
        RSS_URL: The RSS/Atom feed URL
        CATEGORY: ai_focused, research, company_blogs, general_tech, business, or security
        PRIORITY: 1-10 (higher = more important)
        REASON: Brief explanation

        Focus on reliable, frequently-updated sources.
        """

        result = str(self._discovery_agent(prompt))
        return self._parse_source_proposals(result, gap.topic)

    def _parse_source_proposals(self, text: str, topic: str) -> list[SourceProposal]:
        """Parse LLM response into source proposals."""
        import re

        proposals = []

        # Split by SOURCE_NAME to find each proposal
        sections = re.split(r"SOURCE_NAME:", text, flags=re.IGNORECASE)

        for section in sections[1:]:  # Skip first empty section
            try:
                name_match = re.search(r"^([^\n]+)", section)
                url_match = re.search(r"RSS_URL:\s*([^\n\s]+)", section, re.IGNORECASE)
                category_match = re.search(r"CATEGORY:\s*([^\n]+)", section, re.IGNORECASE)
                priority_match = re.search(r"PRIORITY:\s*(\d+)", section, re.IGNORECASE)
                reason_match = re.search(
                    r"REASON:\s*(.+?)(?:SOURCE_NAME|$)", section, re.IGNORECASE | re.DOTALL
                )

                if name_match and url_match:
                    name = name_match.group(1).strip()
                    url = url_match.group(1).strip()
                    category = category_match.group(1).strip() if category_match else "general_tech"
                    priority = int(priority_match.group(1)) if priority_match else 5
                    reason = reason_match.group(1).strip() if reason_match else f"Covers {topic}"

                    proposals.append(
                        SourceProposal(
                            name=name,
                            url=url,
                            category=category,
                            topic=topic,
                            priority=min(max(priority, 1), 10),
                            reason=reason[:200],
                            discovered_via="llm_discovery",
                        )
                    )
            except Exception as e:
                logger.debug(f"Failed to parse proposal section: {e}")
                continue

        return proposals

    def _template_discover(self, gap: CoverageGap) -> list[SourceProposal]:
        """Generate template-based source suggestions."""
        proposals = []

        topic_lower = gap.topic.lower()

        # Suggest category-specific sources based on topic
        if any(kw in topic_lower for kw in ["paper", "research", "study", "arxiv"]):
            proposals.append(
                SourceProposal(
                    name=f"{gap.topic} Research",
                    url=f"https://rss.arxiv.org/search/?query={gap.topic.replace(' ', '+')}&searchtype=all",
                    category="research",
                    topic=gap.topic,
                    priority=6,
                    reason=f"ArXiv search for {gap.topic} research papers",
                    discovered_via="template",
                )
            )

        if any(kw in topic_lower for kw in ["company", "startup", "funding", "launch"]):
            proposals.append(
                SourceProposal(
                    name=f"{gap.topic} on TechCrunch",
                    url=f"https://techcrunch.com/tag/{gap.topic.lower().replace(' ', '-')}/feed/",
                    category="business",
                    topic=gap.topic,
                    priority=6,
                    reason=f"TechCrunch coverage of {gap.topic}",
                    discovered_via="template",
                )
            )

        # Reddit as a source
        if gap.importance_score > 5:
            topic_slug = gap.topic.lower().replace(" ", "")
            proposals.append(
                SourceProposal(
                    name=f"r/{topic_slug} subreddit",
                    url=f"https://www.reddit.com/r/{topic_slug}/.rss",
                    category="general_tech",
                    topic=gap.topic,
                    priority=4,
                    reason=f"Reddit community discussion of {gap.topic}",
                    discovered_via="template",
                )
            )

        return proposals

    async def validate_source(self, proposal: SourceProposal) -> SourceValidation:
        """
        Validate that a proposed source is actually a working RSS feed.

        Args:
            proposal: The source proposal to validate

        Returns:
            Validation result with feed details
        """
        import aiohttp

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(proposal.url, timeout=10) as response,
            ):
                if response.status != 200:
                    return SourceValidation(
                        valid=False,
                        url=proposal.url,
                        error=f"HTTP {response.status}",
                    )

                content = await response.text()

                # Check if it looks like RSS/Atom
                if "<rss" not in content.lower() and "<feed" not in content.lower():
                    return SourceValidation(
                        valid=False,
                        url=proposal.url,
                        error="Not an RSS/Atom feed",
                    )

                # Extract some basic info
                import re

                title_match = re.search(r"<title>([^<]+)</title>", content)
                title = title_match.group(1) if title_match else None

                # Count items
                item_count = content.lower().count("<item") + content.lower().count("<entry")

                # Get sample titles
                item_titles = re.findall(
                    r"<item[^>]*>.*?<title>([^<]+)</title>", content, re.DOTALL
                )[:3]
                entry_titles = re.findall(
                    r"<entry[^>]*>.*?<title>([^<]+)</title>", content, re.DOTALL
                )[:3]
                sample_titles = item_titles or entry_titles

                return SourceValidation(
                    valid=True,
                    url=proposal.url,
                    title=title,
                    article_count=item_count,
                    update_frequency="unknown",
                    sample_titles=sample_titles,
                )

        except Exception as e:
            return SourceValidation(
                valid=False,
                url=proposal.url,
                error=str(e),
            )

    async def submit_for_approval(self, proposal: SourceProposal) -> bool:
        """
        Submit a source proposal for human approval via Discord.

        Args:
            proposal: The source proposal to submit

        Returns:
            True if approved, False otherwise
        """
        try:
            approver = get_discord_approver()
        except ValueError:
            logger.warning("Discord approver not configured")
            return False

        # Validate first
        validation = await self.validate_source(proposal)

        if not validation.valid:
            logger.warning(f"Source validation failed: {validation.error}")
            return False

        message = f"""
**New Source Proposal: {proposal.name}**
URL: `{proposal.url}`
Category: {proposal.category}
Topic: {proposal.topic}
Priority: {proposal.priority}/10

**Reason:**
{proposal.reason}

**Validation:**
- Title: {validation.title or "N/A"}
- Articles: {validation.article_count}
- Sample titles: {", ".join(validation.sample_titles[:2]) or "N/A"}

Discovered via: {proposal.discovered_via}
"""

        request = ApprovalRequest(
            action="add_source",
            resource=proposal.url,
            reason=message,
            agent=self.source_name,
            context={"proposal": proposal.model_dump()},
        )

        result = await approver.request_approval(request)

        if result.status == ApprovalStatus.APPROVED:
            await self._event_bus.publish(
                event_type=EventType.NEWS_SOURCE_DISCOVERED,
                payload={
                    "name": proposal.name,
                    "url": proposal.url,
                    "category": proposal.category,
                    "topic": proposal.topic,
                    "priority": proposal.priority,
                    "approved_by": result.responder,
                },
                source=self.source_name,
            )

            record_event_published(
                event_type=EventType.NEWS_SOURCE_DISCOVERED.value,
                source=self.source_name,
            )

            logger.info(f"Source {proposal.name} approved and published")
            return True

        logger.info(f"Source {proposal.name} was not approved: {result.status}")
        return False

    def get_category_coverage(self) -> dict[str, int]:
        """Get the number of sources per category."""
        coverage: dict[str, int] = defaultdict(int)
        for feed in FEEDS:
            if feed.enabled:
                coverage[feed.category.value] += 1
        return dict(coverage)

    def find_underrepresented_categories(self, min_sources: int = 3) -> list[str]:
        """Find categories with fewer than min_sources."""
        coverage = self.get_category_coverage()
        return [cat for cat, count in coverage.items() if count < min_sources]


DISCOVERY_PROMPT = """You are an RSS feed discovery expert.

Your job is to suggest RSS feeds that would improve news coverage for specific topics.

When suggesting feeds:
1. Prefer official sources (company blogs, official news outlets)
2. Ensure the URL is a direct RSS/Atom feed link (not an HTML page)
3. Focus on reliable, frequently-updated sources
4. Avoid paywalled or login-required feeds
5. Suggest diverse perspectives on the topic

Common RSS URL patterns:
- /feed/ or /rss/ for WordPress sites
- /feed.xml or /rss.xml for static sites
- /blog/rss for company blogs
- https://rss.arxiv.org/rss/cs.XX for arXiv categories

Validate that URLs are actual RSS feeds, not HTML pages.
"""


async def run_news_explorer_cycle() -> list[SourceProposal]:
    """
    Run one news exploration cycle.

    Analyzes coverage gaps and generates source proposals.
    """
    explorer = NewsExplorerAgent()
    await explorer._ensure_initialized()

    gaps = await explorer.analyze_coverage_gaps()
    if not gaps:
        return []

    all_proposals = []
    for gap in gaps[:3]:  # Process top 3 gaps
        proposals = await explorer.discover_sources(gap)
        all_proposals.extend(proposals)

    return all_proposals
