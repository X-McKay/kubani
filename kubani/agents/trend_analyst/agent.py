"""
Trend Analyst Agent - Analyzes trends over historical data.

Implements the analyze-trends-historical skill that compares current
entity mentions against historical data to identify velocity and
emerging/declining topics.

Usage:
    from kubani.agents.trend_analyst import TrendAnalystAgent

    agent = TrendAnalystAgent()
    analysis = await agent.analyze_trends(current_articles, lookback_days=14)
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from kubani.agents._base import KubaniAgent

logger = logging.getLogger(__name__)


# ============================================================================
# Models
# ============================================================================


class VelocityClass:
    """Velocity classifications for trends."""

    SURGING = "surging"  # >100% increase
    RISING = "rising"  # 25-100% increase
    STABLE = "stable"  # -25% to +25%
    DECLINING = "declining"  # 25-75% decrease
    FADING = "fading"  # >75% decrease
    NEW = "new"  # New topic (no historical data)


@dataclass
class EntityTrend:
    """Trend data for a single entity."""

    entity: str
    current_mentions: int = 0
    historical_mentions: int = 0
    velocity_class: str = VelocityClass.STABLE
    velocity_percent: float = 0.0
    first_seen: datetime | None = None
    peak_mentions: int = 0
    sources: list[str] = field(default_factory=list)
    related_articles: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "entity": self.entity,
            "current_mentions": self.current_mentions,
            "historical_mentions": self.historical_mentions,
            "velocity_class": self.velocity_class,
            "velocity_percent": round(self.velocity_percent, 1),
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "peak_mentions": self.peak_mentions,
            "sources": self.sources,
            "related_articles": self.related_articles[:5],  # Limit for output
        }


@dataclass
class TrendAnalysis:
    """Complete trend analysis result."""

    trends: list[EntityTrend] = field(default_factory=list)
    emerging_topics: list[str] = field(default_factory=list)
    declining_topics: list[str] = field(default_factory=list)
    stable_leaders: list[str] = field(default_factory=list)
    summary: str = ""
    period_start: datetime | None = None
    period_end: datetime | None = None
    lookback_days: int = 14
    total_articles_current: int = 0
    total_articles_historical: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "trends": [t.to_dict() for t in self.trends],
            "emerging_topics": self.emerging_topics,
            "declining_topics": self.declining_topics,
            "stable_leaders": self.stable_leaders,
            "summary": self.summary,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "lookback_days": self.lookback_days,
            "total_articles_current": self.total_articles_current,
            "total_articles_historical": self.total_articles_historical,
        }


@dataclass
class HistoricalSnapshot:
    """Historical data snapshot for comparison."""

    entity_counts: dict[str, int] = field(default_factory=dict)
    total_articles: int = 0
    snapshot_date: datetime = field(default_factory=lambda: datetime.now(UTC))


# ============================================================================
# Agent Implementation
# ============================================================================


class TrendAnalystAgent(KubaniAgent):
    """
    Analyzes trends by comparing current vs historical data.

    Implements the analyze-trends-historical skill.
    """

    AGENT_DIR = Path(__file__).parent

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Trend Analyst agent."""
        super().__init__(agent_dir)

        # Analyst-specific configuration
        analyst_config = self.config.get("analyst", {})
        self.min_mentions = analyst_config.get("min_mentions", 2)
        self.default_lookback_days = analyst_config.get("default_lookback_days", 14)

        # Velocity thresholds
        self.surging_threshold = analyst_config.get("surging_threshold", 100)  # >100%
        self.rising_threshold = analyst_config.get("rising_threshold", 25)  # >25%
        self.declining_threshold = analyst_config.get("declining_threshold", -25)
        self.fading_threshold = analyst_config.get("fading_threshold", -75)

        # Memory client - lazy initialization
        self._memory_client = None

    def _get_memory_client(self):
        """Get or create memory MCP client."""
        if self._memory_client is None:
            try:
                from kubani.framework.mcp import get_mcp_client

                self._memory_client = get_mcp_client()
            except Exception as e:
                logger.warning(f"Memory MCP not available: {e}")
                return None
        return self._memory_client

    # ========================================================================
    # Entity extraction
    # ========================================================================

    def _extract_entities(self, articles: list[dict[str, Any]]) -> dict[str, list[str]]:
        """
        Extract entities from articles with their source URLs.

        Returns dict mapping entity -> list of article URLs.
        """
        entity_articles: dict[str, list[str]] = {}

        for article in articles:
            url = article.get("url", "")
            entities = article.get("entities", [])

            # Also check topics field (alias)
            if not entities:
                entities = article.get("topics", [])

            for entity in entities:
                # Normalize entity name
                entity_clean = entity.strip().lower()
                if len(entity_clean) < 2:
                    continue

                if entity_clean not in entity_articles:
                    entity_articles[entity_clean] = []
                if url and url not in entity_articles[entity_clean]:
                    entity_articles[entity_clean].append(url)

        return entity_articles

    def _count_entities(self, articles: list[dict[str, Any]]) -> Counter:
        """Count entity mentions across articles."""
        entity_counts: Counter = Counter()

        for article in articles:
            entities = article.get("entities", []) or article.get("topics", [])
            for entity in entities:
                entity_clean = entity.strip().lower()
                if len(entity_clean) >= 2:
                    entity_counts[entity_clean] += 1

        return entity_counts

    # ========================================================================
    # Velocity calculation
    # ========================================================================

    def _calculate_velocity(
        self,
        current: int,
        historical: int,
    ) -> tuple[str, float]:
        """
        Calculate velocity class and percentage.

        Returns tuple of (velocity_class, velocity_percent).
        """
        if historical == 0:
            if current > 0:
                return VelocityClass.NEW, 100.0
            return VelocityClass.STABLE, 0.0

        # Calculate percentage change
        velocity_percent = ((current - historical) / historical) * 100

        # Classify
        if velocity_percent > self.surging_threshold:
            return VelocityClass.SURGING, velocity_percent
        elif velocity_percent > self.rising_threshold:
            return VelocityClass.RISING, velocity_percent
        elif velocity_percent < self.fading_threshold:
            return VelocityClass.FADING, velocity_percent
        elif velocity_percent < self.declining_threshold:
            return VelocityClass.DECLINING, velocity_percent
        else:
            return VelocityClass.STABLE, velocity_percent

    # ========================================================================
    # Historical data access
    # ========================================================================

    async def _get_historical_snapshot(
        self,
        lookback_days: int,
    ) -> HistoricalSnapshot:
        """
        Get historical entity counts from memory.

        Falls back to empty snapshot if memory unavailable.
        """
        memory = self._get_memory_client()

        if memory is None:
            logger.warning("Memory client unavailable, using empty historical data")
            return HistoricalSnapshot()

        try:
            # Query memory for historical articles
            cutoff_date = datetime.now(UTC) - timedelta(days=lookback_days)
            end_date = datetime.now(UTC) - timedelta(days=1)  # Exclude today

            # Use memory MCP to query stored articles
            historical_articles = await memory.memory.query_articles(
                start_date=cutoff_date.isoformat(),
                end_date=end_date.isoformat(),
            )

            # Count entities from historical articles
            entity_counts = self._count_entities(historical_articles)

            return HistoricalSnapshot(
                entity_counts=dict(entity_counts),
                total_articles=len(historical_articles),
                snapshot_date=datetime.now(UTC),
            )

        except Exception as e:
            logger.error(f"Failed to get historical data: {e}")
            return HistoricalSnapshot()

    async def _store_trend_snapshot(
        self,
        analysis: TrendAnalysis,
    ) -> None:
        """Store current trend snapshot for future comparisons."""
        memory = self._get_memory_client()

        if memory is None:
            return

        try:
            # Store the trend snapshot
            await memory.memory.store_trend_snapshot(
                snapshot_date=datetime.now(UTC).isoformat(),
                trends=[t.to_dict() for t in analysis.trends[:20]],
                emerging_topics=analysis.emerging_topics,
                declining_topics=analysis.declining_topics,
                total_articles=analysis.total_articles_current,
            )
            logger.info("Stored trend snapshot to memory")

        except Exception as e:
            logger.warning(f"Failed to store trend snapshot: {e}")

    # ========================================================================
    # Summary generation
    # ========================================================================

    def _generate_summary(self, analysis: TrendAnalysis) -> str:
        """Generate human-readable trend summary."""
        parts = []

        # Surging topics
        surging = [t for t in analysis.trends if t.velocity_class == VelocityClass.SURGING]
        if surging:
            topics = ", ".join(t.entity.title() for t in surging[:3])
            parts.append(f"**Surging:** {topics} (significant increase in coverage)")

        # Rising topics
        rising = [t for t in analysis.trends if t.velocity_class == VelocityClass.RISING]
        if rising:
            topics = ", ".join(t.entity.title() for t in rising[:3])
            parts.append(f"**Rising:** {topics} (growing attention)")

        # Emerging topics
        if analysis.emerging_topics:
            topics = ", ".join(t.title() for t in analysis.emerging_topics[:3])
            parts.append(f"**Emerging:** {topics} (new this period)")

        # Declining topics
        if analysis.declining_topics:
            topics = ", ".join(t.title() for t in analysis.declining_topics[:3])
            parts.append(f"**Declining:** {topics} (reduced coverage)")

        # Stable leaders
        if analysis.stable_leaders:
            topics = ", ".join(t.title() for t in analysis.stable_leaders[:3])
            parts.append(f"**Consistent Coverage:** {topics}")

        if not parts:
            return "No significant trend changes detected this period."

        return "\n".join(parts)

    # ========================================================================
    # Main analysis method
    # ========================================================================

    async def analyze_trends(
        self,
        current_articles: list[dict[str, Any]],
        lookback_days: int | None = None,
        min_mentions: int | None = None,
    ) -> TrendAnalysis:
        """
        Analyze trends by comparing current vs historical data.

        Implements the analyze-trends-historical skill.

        Args:
            current_articles: Articles from current period (with entities)
            lookback_days: Days of historical data to compare (default: 14)
            min_mentions: Minimum mentions to include entity (default: 2)

        Returns:
            TrendAnalysis with velocity classifications and insights
        """
        lookback_days = lookback_days or self.default_lookback_days
        min_mentions = min_mentions or self.min_mentions

        now = datetime.now(UTC)
        analysis = TrendAnalysis(
            period_start=now - timedelta(days=1),
            period_end=now,
            lookback_days=lookback_days,
            total_articles_current=len(current_articles),
        )

        logger.info(
            f"Analyzing trends: {len(current_articles)} current articles, "
            f"{lookback_days} day lookback"
        )

        # Step 1: Extract current entity mentions
        current_entity_articles = self._extract_entities(current_articles)
        current_counts = self._count_entities(current_articles)

        # Step 2: Get historical data
        historical = await self._get_historical_snapshot(lookback_days)
        analysis.total_articles_historical = historical.total_articles

        # Normalize historical counts to per-day average for fair comparison
        historical_daily = {}
        if lookback_days > 0:
            for entity, count in historical.entity_counts.items():
                historical_daily[entity] = count / lookback_days

        # Step 3: Calculate trends for each entity
        all_entities = set(current_counts.keys()) | set(historical.entity_counts.keys())

        for entity in all_entities:
            current_count = current_counts.get(entity, 0)
            historical_count = historical.entity_counts.get(entity, 0)
            historical_avg = historical_daily.get(entity, 0)

            # Skip entities below threshold in both periods
            if current_count < min_mentions and historical_avg < min_mentions:
                continue

            # Calculate velocity (comparing to daily average)
            velocity_class, velocity_percent = self._calculate_velocity(
                current_count,
                int(historical_avg * 1),  # Compare to 1-day equivalent
            )

            # Get sources for current period
            sources = list(
                {
                    a.get("source", "Unknown")
                    for a in current_articles
                    if entity in [e.lower() for e in (a.get("entities", []) or a.get("topics", []))]
                }
            )

            trend = EntityTrend(
                entity=entity,
                current_mentions=current_count,
                historical_mentions=historical_count,
                velocity_class=velocity_class,
                velocity_percent=velocity_percent,
                sources=sources[:5],
                related_articles=current_entity_articles.get(entity, [])[:5],
            )

            analysis.trends.append(trend)

        # Step 4: Sort by velocity and current mentions
        analysis.trends.sort(
            key=lambda t: (
                # Priority order: surging > rising > new > stable > declining > fading
                {
                    VelocityClass.SURGING: 0,
                    VelocityClass.RISING: 1,
                    VelocityClass.NEW: 2,
                    VelocityClass.STABLE: 3,
                    VelocityClass.DECLINING: 4,
                    VelocityClass.FADING: 5,
                }.get(t.velocity_class, 6),
                -t.current_mentions,  # Then by current mentions desc
            )
        )

        # Step 5: Categorize topics
        analysis.emerging_topics = [
            t.entity
            for t in analysis.trends
            if t.velocity_class == VelocityClass.NEW and t.current_mentions >= min_mentions
        ][:5]

        analysis.declining_topics = [
            t.entity
            for t in analysis.trends
            if t.velocity_class in (VelocityClass.DECLINING, VelocityClass.FADING)
        ][:5]

        analysis.stable_leaders = [
            t.entity
            for t in analysis.trends
            if t.velocity_class == VelocityClass.STABLE and t.current_mentions >= min_mentions * 2
        ][:5]

        # Step 6: Generate summary
        analysis.summary = self._generate_summary(analysis)

        # Step 7: Store snapshot for future comparisons
        await self._store_trend_snapshot(analysis)

        logger.info(
            f"Trend analysis complete: {len(analysis.trends)} entities tracked, "
            f"{len(analysis.emerging_topics)} emerging, {len(analysis.declining_topics)} declining"
        )

        return analysis

    async def analyze_trends_as_dict(
        self,
        current_articles: list[dict[str, Any]],
        lookback_days: int | None = None,
        min_mentions: int | None = None,
    ) -> dict[str, Any]:
        """Convenience method returning dict for Temporal activities."""
        result = await self.analyze_trends(current_articles, lookback_days, min_mentions)
        return result.to_dict()

    # ========================================================================
    # Learning integration
    # ========================================================================

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = len(result.get("trends", [])) > 0
        await self.record_outcome(skill_name, result, success=success)
