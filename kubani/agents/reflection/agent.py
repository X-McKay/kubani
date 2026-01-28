"""
Reflection Agent - Synthesizes learnings across agents.

The Reflection Agent is part of the Voyager-inspired continuous learning system.
It analyzes evaluations across all agents to identify:
- Cross-cutting patterns
- Knowledge gaps
- Skill opportunities
- Best practices

Usage:
    from kubani.agents.reflection import ReflectionAgent

    reflection = ReflectionAgent()
    insights = await reflection.reflect(time_window_hours=24)
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from kubani.agents._base import KubaniAgent
from kubani.agents.reflection.models import (
    InsightType,
    ReflectionInsight,
    ReflectionResult,
)
from kubani.framework.config import get_config
from kubani.framework.mcp import get_mcp_client

logger = logging.getLogger(__name__)

REFLECTION_PROMPT = """You are a Reflection Agent in a continuous learning system.

Your role is to synthesize learnings across all agents and identify cross-cutting patterns.
You analyze evaluation data to discover:

1. **Patterns**: Successful approaches that should be replicated across agents
2. **Anti-patterns**: Approaches that consistently lead to failures
3. **Best Practices**: General guidelines derived from experience
4. **Knowledge**: Domain-specific facts worth preserving
5. **Skill Opportunities**: Patterns that could become reusable skills

When analyzing evaluations:
- Look for similarities across different agents
- Identify recurring themes in successes and failures
- Note domain-specific knowledge that could help other agents
- Flag patterns that occur frequently enough to become skills

Be thorough but focused. Quality insights are better than quantity.
"""


class ReflectionAgent(KubaniAgent):
    """
    Synthesizes learnings across agents to identify patterns and insights.

    Part of the continuous learning system, the Reflection Agent:
    - Analyzes evaluations from all agents
    - Identifies cross-cutting patterns
    - Discovers knowledge gaps
    - Proposes skill opportunities
    - Updates the knowledge graph
    """

    name = "reflection"
    description = "Synthesizes cross-agent learnings and identifies patterns"
    version = "1.0.0"

    PROMPT_FILE = Path(__file__).parent / "prompt.md"

    def __init__(self):
        """Initialize the Reflection Agent."""
        super().__init__()
        self._synthesis_interval_hours = 24
        self._min_evaluations = 10

    @property
    def system_prompt(self) -> str:
        """Get the system prompt for the reflection agent."""
        if self.PROMPT_FILE.exists():
            return self.PROMPT_FILE.read_text()
        return REFLECTION_PROMPT

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("success", False)
        await self.record_outcome(skill_name, result, success=success)

    async def reflect(
        self,
        time_window_hours: int = 24,
        min_evaluations: int = 10,
    ) -> ReflectionResult:
        """
        Run a reflection cycle to synthesize insights.

        Args:
            time_window_hours: How far back to analyze
            min_evaluations: Minimum evaluations needed to proceed

        Returns:
            ReflectionResult with discovered insights
        """
        result = ReflectionResult(time_window_hours=time_window_hours)

        try:
            # Fetch recent evaluations
            evaluations = await self._fetch_recent_evaluations(time_window_hours)

            if len(evaluations) < min_evaluations:
                logger.info(
                    f"Not enough evaluations ({len(evaluations)}) "
                    f"for reflection (need {min_evaluations})"
                )
                return result

            result.evaluations_analyzed = len(evaluations)
            result.agents_analyzed = list(set(e.get("agent_id", "") for e in evaluations))

            # Analyze for patterns
            result.patterns = await self._identify_patterns(evaluations)
            result.anti_patterns = await self._identify_anti_patterns(evaluations)
            result.best_practices = await self._extract_best_practices(evaluations)
            result.knowledge = await self._extract_knowledge(evaluations)
            result.skill_opportunities = await self._identify_skill_opportunities(evaluations)

            # Store insights
            for insight in result.all_insights:
                await self._store_insight(insight)

            # Update knowledge graph
            await self._update_knowledge_graph(result)

            logger.info(
                f"Reflection complete: {result.total_insights} insights "
                f"from {result.evaluations_analyzed} evaluations"
            )

        except Exception as e:
            logger.error(f"Reflection failed: {e}")

        return result

    async def _fetch_recent_evaluations(self, hours: int) -> list[dict[str, Any]]:
        """Fetch recent evaluations from memory."""
        try:
            client = get_mcp_client()
            config = get_config()

            if not config.mcp.memory_enabled:
                logger.debug("Memory MCP not enabled")
                return []

            evaluations = await client.memory.query_learnings(
                query="agent evaluation",
                learning_type="evaluation",
                min_confidence=0.0,
                limit=500,
            )

            # Filter by time
            cutoff = datetime.now(UTC) - timedelta(hours=hours)
            recent = []
            for e in evaluations:
                ts = e.get("timestamp")
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if ts and ts > cutoff:
                    recent.append(e)

            return recent

        except Exception as e:
            logger.error(f"Failed to fetch evaluations: {e}")
            return []

    async def _identify_patterns(
        self, evaluations: list[dict[str, Any]]
    ) -> list[ReflectionInsight]:
        """Identify successful patterns from evaluations."""
        patterns = []

        # Group by identified patterns
        pattern_occurrences: dict[str, list[dict]] = defaultdict(list)

        for eval_data in evaluations:
            context = eval_data.get("context", {})
            identified = context.get("identified_patterns", [])
            for p in identified:
                pattern_occurrences[p].append(eval_data)

        # Create insights for patterns that occur multiple times
        for pattern_text, occurrences in pattern_occurrences.items():
            if len(occurrences) >= 3:  # Minimum occurrences
                insight = ReflectionInsight(
                    insight_type=InsightType.PATTERN,
                    title=f"Pattern: {pattern_text[:50]}",
                    description=pattern_text,
                    evidence=[e.get("execution_id", "") for e in occurrences],
                    applicable_agents=list(set(e.get("agent_id", "") for e in occurrences)),
                    occurrence_count=len(occurrences),
                    confidence=min(0.9, 0.5 + len(occurrences) * 0.1),
                    impact_score=0.7,
                    source_evaluations=[e.get("evaluation_id", "") for e in occurrences],
                )
                patterns.append(insight)

        return patterns

    async def _identify_anti_patterns(
        self, evaluations: list[dict[str, Any]]
    ) -> list[ReflectionInsight]:
        """Identify anti-patterns from failed evaluations."""
        anti_patterns = []

        # Group failures by reason
        failure_reasons: dict[str, list[dict]] = defaultdict(list)

        for eval_data in evaluations:
            context = eval_data.get("context", {})
            if not context.get("success", True):
                reason = context.get("failure_reason", "unknown")
                if reason:
                    failure_reasons[reason].append(eval_data)

        # Create anti-pattern insights for recurring failures
        for reason, occurrences in failure_reasons.items():
            if len(occurrences) >= 2:
                insight = ReflectionInsight(
                    insight_type=InsightType.ANTI_PATTERN,
                    title=f"Anti-pattern: {reason[:50]}",
                    description=f"Recurring failure: {reason}",
                    evidence=[e.get("execution_id", "") for e in occurrences],
                    applicable_agents=list(set(e.get("agent_id", "") for e in occurrences)),
                    occurrence_count=len(occurrences),
                    confidence=min(0.9, 0.5 + len(occurrences) * 0.15),
                    impact_score=0.8,  # Anti-patterns are high impact
                    source_evaluations=[e.get("evaluation_id", "") for e in occurrences],
                )
                anti_patterns.append(insight)

        return anti_patterns

    async def _extract_best_practices(
        self, evaluations: list[dict[str, Any]]
    ) -> list[ReflectionInsight]:
        """Extract best practices from high-scoring evaluations."""
        best_practices = []

        # Find consistently successful approaches
        agent_successes: dict[str, list[dict]] = defaultdict(list)

        for eval_data in evaluations:
            context = eval_data.get("context", {})
            scores = context.get("scores", {})
            overall = scores.get("overall", 0)

            if overall >= 0.8:  # High-scoring evaluations
                agent_id = eval_data.get("agent_id", "unknown")
                agent_successes[agent_id].append(eval_data)

        # Extract common strengths from successful agents
        for agent_id, successes in agent_successes.items():
            if len(successes) >= 3:
                # Collect common strengths
                all_strengths: dict[str, int] = defaultdict(int)
                for s in successes:
                    context = s.get("context", {})
                    for strength in context.get("strengths", []):
                        all_strengths[strength] += 1

                # Create insights for common strengths
                for strength, count in all_strengths.items():
                    if count >= 2:
                        insight = ReflectionInsight(
                            insight_type=InsightType.BEST_PRACTICE,
                            title=f"Best Practice: {strength[:50]}",
                            description=strength,
                            applicable_agents=[agent_id],
                            occurrence_count=count,
                            confidence=0.75,
                            impact_score=0.6,
                        )
                        best_practices.append(insight)

        return best_practices

    async def _extract_knowledge(
        self, evaluations: list[dict[str, Any]]
    ) -> list[ReflectionInsight]:
        """Extract domain knowledge from evaluations."""
        # For now, return empty - knowledge extraction requires more context
        return []

    async def _identify_skill_opportunities(
        self, evaluations: list[dict[str, Any]]
    ) -> list[ReflectionInsight]:
        """Identify patterns that could become skills."""
        opportunities = []

        # Look for patterns that appear frequently with high success
        pattern_success: dict[str, dict] = {}

        for eval_data in evaluations:
            context = eval_data.get("context", {})
            patterns = context.get("identified_patterns", [])
            success = context.get("success", False)
            scores = context.get("scores", {})
            overall = scores.get("overall", 0)

            for pattern in patterns:
                if pattern not in pattern_success:
                    pattern_success[pattern] = {
                        "total": 0,
                        "successful": 0,
                        "high_quality": 0,
                        "agents": set(),
                        "executions": [],
                    }

                pattern_success[pattern]["total"] += 1
                if success:
                    pattern_success[pattern]["successful"] += 1
                if overall >= 0.8:
                    pattern_success[pattern]["high_quality"] += 1
                pattern_success[pattern]["agents"].add(eval_data.get("agent_id", ""))
                pattern_success[pattern]["executions"].append(eval_data.get("execution_id", ""))

        # Create skill opportunities for high-success patterns
        for pattern, stats in pattern_success.items():
            if stats["total"] >= 5 and stats["successful"] / stats["total"] >= 0.8:
                insight = ReflectionInsight(
                    insight_type=InsightType.SKILL_OPPORTUNITY,
                    title=f"Skill Opportunity: {pattern[:50]}",
                    description=f"Pattern with {stats['successful']}/{stats['total']} success rate",
                    evidence=stats["executions"][:10],
                    applicable_agents=list(stats["agents"]),
                    occurrence_count=stats["total"],
                    confidence=stats["successful"] / stats["total"],
                    impact_score=0.9,  # Skill opportunities are high impact
                    context={
                        "success_rate": stats["successful"] / stats["total"],
                        "high_quality_rate": stats["high_quality"] / stats["total"],
                    },
                )
                opportunities.append(insight)

        return opportunities

    async def _store_insight(self, insight: ReflectionInsight) -> None:
        """Store an insight in shared memory."""
        try:
            client = get_mcp_client()
            config = get_config()

            if not config.mcp.memory_enabled:
                return

            await client.memory.store_learning(
                agent_id=self.name,
                learning_type=f"insight_{insight.insight_type.value}",
                content=f"{insight.title}: {insight.description}",
                confidence=insight.confidence,
                context=insight.to_dict(),
            )

            logger.debug(f"Stored insight: {insight.title}")

        except Exception as e:
            logger.warning(f"Failed to store insight: {e}")

    async def _update_knowledge_graph(self, result: ReflectionResult) -> None:
        """Update the knowledge graph with new insights."""
        try:
            client = get_mcp_client()
            config = get_config()

            if not config.mcp.memory_enabled:
                return

            # Store relationships between insights and agents
            for insight in result.all_insights:
                for agent in insight.applicable_agents:
                    await client.memory.store_knowledge(
                        topic=f"agent/{agent}/insights",
                        content=insight.description,
                        source=self.name,
                        related_topics=[
                            f"insight/{insight.insight_type.value}",
                            *[f"tag/{t}" for t in insight.tags],
                        ],
                    )

            logger.debug(f"Updated knowledge graph with {result.total_insights} insights")

        except Exception as e:
            logger.warning(f"Failed to update knowledge graph: {e}")
