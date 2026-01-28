"""
Learning System Syndicate - Continuous improvement through learning.

Orchestrates the Voyager-inspired continuous learning system:
- CriticAgent: Evaluates agent executions
- ReflectionAgent: Synthesizes cross-agent insights
- SkillSynthesizerAgent: Proposes new skills from patterns

Usage:
    from kubani.syndicates.learning_system import LearningSystemSyndicate

    syndicate = LearningSystemSyndicate()
    await syndicate.start()
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from kubani.agents.critic import CriticAgent
from kubani.agents.reflection import ReflectionAgent
from kubani.agents.skill_synthesizer import SkillSynthesizerAgent
from kubani.framework.config import get_config
from kubani.framework.events import EventType, get_event_bus
from kubani.syndicates._base import Syndicate

logger = logging.getLogger(__name__)


class LearningSystemSyndicate(Syndicate):
    """
    Continuous learning system syndicate.

    Orchestrates three learning agents:
    - CriticAgent: Evaluates execution quality
    - ReflectionAgent: Synthesizes insights across agents
    - SkillSynthesizerAgent: Proposes new skills

    The syndicate runs on a schedule:
    - Critic runs hourly to evaluate recent executions
    - Reflection runs daily to synthesize insights
    - Skill synthesis runs weekly to propose new skills
    """

    SYNDICATE_DIR = Path(__file__).parent

    agents = [
        CriticAgent,
        ReflectionAgent,
        SkillSynthesizerAgent,
    ]

    def __init__(self, syndicate_dir: Path | None = None):
        """Initialize the Learning System syndicate."""
        super().__init__(syndicate_dir)
        self._event_bus = None

    async def run(self) -> None:
        """
        Main orchestration loop.

        Runs three concurrent tasks on different schedules:
        1. Critic evaluation (hourly)
        2. Reflection synthesis (daily)
        3. Skill synthesis (weekly)
        """
        self._event_bus = await get_event_bus()
        config = get_config()

        # Get agent instances
        critic = self.get_agent(CriticAgent)
        reflection = self.get_agent(ReflectionAgent)
        synthesizer = self.get_agent(SkillSynthesizerAgent)

        logger.info(f"Starting {self.name} with agents: {[a.__name__ for a in self.agents]}")

        # Check if learning is enabled
        if not config.learning.enabled:
            logger.warning("Learning is disabled in configuration")
            return

        # Run all tasks concurrently
        await asyncio.gather(
            self._run_critic_loop(critic),
            self._run_reflection_loop(reflection),
            self._run_synthesis_loop(synthesizer),
            self._listen_for_events(),
        )

    async def _run_critic_loop(self, critic: CriticAgent) -> None:
        """Run the critic evaluation loop."""
        config = get_config()

        if not config.learning.critic_enabled:
            logger.info("Critic agent disabled")
            return

        interval_minutes = config.learning.critic_interval_minutes
        logger.info(f"Starting critic loop (every {interval_minutes} minutes)")

        while self._running:
            try:
                # Evaluate recent executions
                evaluations = await critic.evaluate_recent_executions(hours=1)

                if evaluations:
                    logger.info(f"Critic evaluated {len(evaluations)} executions")

                    # Publish evaluation event (using local event type)
                    from kubani.syndicates.learning_system.events import EVALUATION_COMPLETE

                    await self._event_bus.publish(
                        EVALUATION_COMPLETE,
                        {
                            "syndicate": self.name,
                            "evaluations": len(evaluations),
                            "avg_score": sum(e.overall_score for e in evaluations)
                            / len(evaluations),
                        },
                        source=self.name,
                    )

            except Exception as e:
                logger.error(f"Critic loop error: {e}")

            # Wait for next interval
            await asyncio.sleep(interval_minutes * 60)

    async def _run_reflection_loop(self, reflection: ReflectionAgent) -> None:
        """Run the reflection synthesis loop."""
        config = get_config()

        if not config.learning.reflection_enabled:
            logger.info("Reflection agent disabled")
            return

        interval_hours = config.learning.reflection_interval_hours
        logger.info(f"Starting reflection loop (every {interval_hours} hours)")

        while self._running:
            try:
                # Run reflection
                result = await reflection.reflect(
                    time_window_hours=interval_hours * 7,  # Look back 1 week
                    min_evaluations=10,
                )

                if result.total_insights > 0:
                    logger.info(
                        f"Reflection generated {result.total_insights} insights "
                        f"from {result.evaluations_analyzed} evaluations"
                    )

                    # Publish reflection event (using local event type)
                    from kubani.syndicates.learning_system.events import REFLECTION_COMPLETE

                    await self._event_bus.publish(
                        REFLECTION_COMPLETE,
                        {
                            "syndicate": self.name,
                            "insights": result.total_insights,
                            "patterns": len(result.patterns),
                            "skill_opportunities": len(result.skill_opportunities),
                        },
                        source=self.name,
                    )

            except Exception as e:
                logger.error(f"Reflection loop error: {e}")

            # Wait for next interval
            await asyncio.sleep(interval_hours * 3600)

    async def _run_synthesis_loop(self, synthesizer: SkillSynthesizerAgent) -> None:
        """Run the skill synthesis loop."""
        config = get_config()

        if not config.learning.synthesizer_enabled:
            logger.info("Skill synthesizer disabled")
            return

        # Default to weekly (168 hours) if not in config
        interval_hours = getattr(config.learning, "synthesis_interval_hours", 168)
        logger.info(f"Starting synthesis loop (every {interval_hours} hours)")

        while self._running:
            try:
                # Run synthesis
                result = await synthesizer.synthesize_skills()

                if result.proposals_created > 0:
                    logger.info(
                        f"Synthesized {result.proposals_created} skill proposals, "
                        f"{result.proposals_posted} posted for approval"
                    )

                    # Publish synthesis event (using local event type)
                    from kubani.syndicates.learning_system.events import SKILL_PROPOSED

                    await self._event_bus.publish(
                        SKILL_PROPOSED,
                        {
                            "syndicate": self.name,
                            "proposals_created": result.proposals_created,
                            "proposals_posted": result.proposals_posted,
                        },
                        source=self.name,
                    )

            except Exception as e:
                logger.error(f"Synthesis loop error: {e}")

            # Wait for next interval
            await asyncio.sleep(interval_hours * 3600)

    async def _listen_for_events(self) -> None:
        """Listen for learning-related events."""
        logger.info("Starting event listener")

        async for event in self._event_bus.subscribe(
            EventType.AGENT_EXECUTION_COMPLETE,
            consumer_group=self.name,
            consumer_name=f"{self.name}-listener",
        ):
            if not self._running:
                break

            try:
                # Log execution for later evaluation
                await self._log_execution(event)

            except Exception as e:
                logger.error(f"Event handling error: {e}")

    async def _log_execution(self, event: dict[str, Any]) -> None:
        """Log an agent execution for later evaluation."""
        from kubani.framework.mcp import get_mcp_client

        try:
            client = get_mcp_client()
            config = get_config()

            if not config.mcp.memory_enabled:
                return

            await client.memory.store_learning(
                agent_id=event.get("agent_id", "unknown"),
                learning_type="execution",
                content=f"Execution of {event.get('task', 'unknown task')}",
                confidence=0.9,
                context={
                    "execution_id": event.get("execution_id"),
                    "agent_id": event.get("agent_id"),
                    "task_description": event.get("task"),
                    "success": event.get("success", True),
                    "result_summary": event.get("result_summary", ""),
                    "duration_ms": event.get("duration_ms", 0),
                },
            )

        except Exception as e:
            logger.warning(f"Failed to log execution: {e}")

    async def trigger_evaluation(self, agent_id: str | None = None) -> dict[str, Any]:
        """
        Manually trigger a critic evaluation.

        Args:
            agent_id: Optional filter for specific agent

        Returns:
            Evaluation summary
        """
        critic = self.get_agent(CriticAgent)
        evaluations = await critic.evaluate_recent_executions(hours=24, agent_id=agent_id)

        return {
            "evaluations": len(evaluations),
            "avg_score": sum(e.overall_score for e in evaluations) / len(evaluations)
            if evaluations
            else 0,
            "successes": sum(1 for e in evaluations if e.success),
            "failures": sum(1 for e in evaluations if not e.success),
        }

    async def trigger_reflection(self) -> dict[str, Any]:
        """
        Manually trigger a reflection cycle.

        Returns:
            Reflection summary
        """
        reflection = self.get_agent(ReflectionAgent)
        result = await reflection.reflect()

        return {
            "insights": result.total_insights,
            "patterns": len(result.patterns),
            "anti_patterns": len(result.anti_patterns),
            "best_practices": len(result.best_practices),
            "skill_opportunities": len(result.skill_opportunities),
        }

    async def trigger_synthesis(self) -> dict[str, Any]:
        """
        Manually trigger a skill synthesis cycle.

        Returns:
            Synthesis summary
        """
        synthesizer = self.get_agent(SkillSynthesizerAgent)
        result = await synthesizer.synthesize_skills()

        return {
            "proposals_created": result.proposals_created,
            "proposals_posted": result.proposals_posted,
            "proposals": [p.to_dict() for p in result.proposals],
        }
