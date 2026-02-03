"""
Trend Analyst Agent - Skills-centric trend analysis.

Thin orchestrator that delegates to diagnostic skills:
- analyze-trends-historical: Compare current vs historical data

Usage:
    from kubani.agents.trend_analyst import TrendAnalystAgent

    agent = TrendAnalystAgent()
    analysis = await agent.analyze_trends(current_entities, historical_data)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kubani.agents._base import SkillsOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class EntityTrend:
    """Trend data for a single entity."""

    entity: str
    current_mentions: int = 0
    historical_mentions: int = 0
    velocity_class: str = "stable"
    velocity_percent: float = 0.0
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "entity": self.entity,
            "current_mentions": self.current_mentions,
            "historical_mentions": self.historical_mentions,
            "velocity_class": self.velocity_class,
            "velocity_percent": round(self.velocity_percent, 1),
            "sources": self.sources,
        }


@dataclass
class TrendAnalysis:
    """Complete trend analysis result."""

    trends: list[EntityTrend] = field(default_factory=list)
    emerging_topics: list[str] = field(default_factory=list)
    declining_topics: list[str] = field(default_factory=list)
    summary: str = ""
    lookback_days: int = 14

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "trends": [t.to_dict() for t in self.trends],
            "emerging_topics": self.emerging_topics,
            "declining_topics": self.declining_topics,
            "summary": self.summary,
            "lookback_days": self.lookback_days,
        }


class TrendAnalystAgent(SkillsOrchestrator):
    """
    Skills-centric trend analyst.

    Discovers and delegates to news/diagnostic skills:
    - analyze-trends-historical
    """

    AGENT_DIR = Path(__file__).parent
    SKILLS_DOMAIN = "news"
    SKILLS_CATEGORY = "diagnostic"

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Trend Analyst agent."""
        super().__init__(agent_dir)

        analyst_config = self.config.get("analyst", {})
        self.lookback_days = analyst_config.get("default_lookback_days", 14)

    async def analyze_trends(
        self,
        current_entities: dict[str, int],
        historical_data: dict[str, int],
        lookback_days: int | None = None,
    ) -> TrendAnalysis:
        """
        Analyze trends by comparing current vs historical entity counts.

        Args:
            current_entities: Entity name -> mention count for current period
            historical_data: Entity name -> mention count for historical period
            lookback_days: Days of historical data (for context)

        Returns:
            TrendAnalysis with velocity classifications and insights
        """
        lookback = lookback_days or self.lookback_days

        task_prompt = f"""Analyze trend velocity for these entities.

Use the analyze-trends-historical skill to:
1. Calculate velocity for each entity (current vs historical mentions)
2. Classify as: surging (>100%), rising (25-100%), stable (-25% to +25%), declining (-25% to -75%), fading (<-75%), or new (no historical)
3. Identify emerging topics (new this period)
4. Identify declining topics
5. Generate a summary

Current period entity mentions:
```json
{json.dumps(current_entities, indent=2)}
```

Historical period entity mentions ({lookback} days):
```json
{json.dumps(historical_data, indent=2)}
```

Return JSON with fields: trends (array), emerging_topics, declining_topics, summary"""

        response = await self.run(task_prompt)
        analysis = self._parse_trend_analysis(response)
        analysis.lookback_days = lookback

        await self.on_skill_complete(
            "analyze-trends-historical",
            {"trends": len(analysis.trends), "emerging": len(analysis.emerging_topics)},
        )

        return analysis

    def _parse_trend_analysis(self, response: str) -> TrendAnalysis:
        """Parse LLM response into TrendAnalysis."""
        try:
            data = self._extract_json(response)
            trends_data = data.get("trends", []) if isinstance(data, dict) else []

            trends = [
                EntityTrend(
                    entity=t.get("entity", ""),
                    current_mentions=t.get("current_mentions", 0),
                    historical_mentions=t.get("historical_mentions", 0),
                    velocity_class=t.get("velocity_class", "stable"),
                    velocity_percent=t.get("velocity_percent", 0.0),
                    sources=t.get("sources", []),
                )
                for t in trends_data
            ]

            return TrendAnalysis(
                trends=trends,
                emerging_topics=data.get("emerging_topics", []) if isinstance(data, dict) else [],
                declining_topics=data.get("declining_topics", []) if isinstance(data, dict) else [],
                summary=data.get("summary", "") if isinstance(data, dict) else "",
            )
        except Exception as e:
            logger.warning(f"Failed to parse trend analysis: {e}")
            return TrendAnalysis()

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        trends = result.get("trends", 0)
        # Handle both count (int) and list of trends
        success = len(trends) > 0 if isinstance(trends, list) else trends > 0
        await self.record_outcome(skill_name, result, success=success)
