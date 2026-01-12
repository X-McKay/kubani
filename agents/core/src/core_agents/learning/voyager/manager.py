"""
Learning Manager - Orchestrates the Voyager-style Continuous Learning System.

Coordinates:
- Critic Agent: Evaluates executions and skill proposals
- Reflection Agent: Synthesizes cross-agent knowledge
- Skill Synthesizer: Generates new skills from patterns
- Interaction Logger: Captures all agent interactions
- Discord Integration: Posts proposals and receives approvals

This is the main entry point for the continuous learning system.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from core_agents.learning.voyager.critic import CriticAgent, ExecutionAnalysis
from core_agents.learning.voyager.reflection import Knowledge, ReflectionAgent, ReflectionReport
from core_agents.learning.voyager.synthesizer import SkillSynthesizer

logger = logging.getLogger(__name__)


@dataclass
class LearningConfig:
    """Configuration for the learning system."""

    # LLM settings
    llm_api_url: str = "http://llm-api.vllm.svc.cluster.local:8000/v1"
    llm_model: str = "nvidia/Qwen3-14B-FP4"

    # Memory settings
    qdrant_host: str = "qdrant.ai-agents.svc"
    qdrant_port: int = 6333
    neo4j_uri: str = "bolt://neo4j.ai-agents.svc:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    embeddings_api_url: str = "http://embeddings-api.vllm.svc.cluster.local:8000/v1"

    # Discord settings
    discord_mcp_url: str = "http://discord-mcp-server.ai-agents.svc:8080"
    learning_channel: str = ""
    approvals_channel: str = ""

    # Registry settings
    registry_url: str = "http://metadata-registry.ai-agents.svc:8000"

    # Temporal settings (direct SDK connection)
    temporal_host: str = "temporal-frontend.temporal.svc.cluster.local:7233"
    temporal_namespace: str = "default"

    # Redis settings
    redis_url: str = "redis://redis.ai-agents.svc:6379"

    # Learning settings
    auto_approve_threshold: float = 0.95
    min_examples_for_skill: int = 3
    reflection_interval_hours: int = 24
    max_skill_revisions: int = 3

    # Feature flags
    critic_enabled: bool = True
    reflection_enabled: bool = True
    auto_synthesis_enabled: bool = True
    discord_approvals_enabled: bool = True

    # Passive monitoring settings
    passive_monitoring_enabled: bool = True
    workflow_poll_interval_seconds: int = 60
    discord_poll_interval_seconds: int = 300
    event_subscription_enabled: bool = True


@dataclass
class ExecutionRecord:
    """Record of an agent execution for learning."""

    id: str
    agent_name: str
    task: str
    trace: list[dict[str, Any]]
    outcome: dict[str, Any]
    success: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    analysis: ExecutionAnalysis | None = None


class InteractionLogger:
    """Logs all agent interactions for learning."""

    def __init__(self, redis_client: Any = None):
        self.redis_client = redis_client
        self.executions: list[ExecutionRecord] = []
        self.discord_interactions: list[dict[str, Any]] = []

    async def log_execution(
        self,
        execution_id: str,
        agent_name: str,
        task: str,
        trace: list[dict[str, Any]],
        outcome: dict[str, Any],
        success: bool,
    ) -> ExecutionRecord:
        """Log an agent execution."""
        record = ExecutionRecord(
            id=execution_id,
            agent_name=agent_name,
            task=task,
            trace=trace,
            outcome=outcome,
            success=success,
        )
        self.executions.append(record)

        # Persist to Redis if available
        if self.redis_client:
            await self._persist_to_redis(record)

        logger.debug(f"Logged execution: {execution_id} ({agent_name})")
        return record

    async def log_discord_interaction(
        self,
        message_id: str,
        channel_id: str,
        content: str,
        reactions: list[str] | None = None,
    ) -> None:
        """Log a Discord interaction."""
        interaction = {
            "message_id": message_id,
            "channel_id": channel_id,
            "content": content,
            "reactions": reactions or [],
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.discord_interactions.append(interaction)

    def get_recent_executions(
        self,
        hours: int = 24,
        agent_name: str | None = None,
    ) -> list[ExecutionRecord]:
        """Get recent executions."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        executions = [e for e in self.executions if e.timestamp >= cutoff]

        if agent_name:
            executions = [e for e in executions if e.agent_name == agent_name]

        return executions

    def get_successful_patterns(self, min_occurrences: int = 2) -> list[dict[str, Any]]:
        """Extract successful patterns from executions."""
        # Group successful executions by task type/pattern
        patterns: dict[str, list[ExecutionRecord]] = {}

        for execution in self.executions:
            if execution.success:
                # Simple pattern extraction - could be more sophisticated
                pattern_key = self._extract_pattern_key(execution)
                if pattern_key not in patterns:
                    patterns[pattern_key] = []
                patterns[pattern_key].append(execution)

        # Return patterns with enough occurrences
        return [
            {
                "pattern": key,
                "count": len(executions),
                "executions": [e.id for e in executions],
            }
            for key, executions in patterns.items()
            if len(executions) >= min_occurrences
        ]

    def _extract_pattern_key(self, execution: ExecutionRecord) -> str:
        """Extract a pattern key from an execution."""
        # Simple implementation - extract tool sequence
        tools = []
        for step in execution.trace:
            if "tool" in step:
                tools.append(step["tool"])
        return f"{execution.agent_name}:{':'.join(tools[:5])}"

    async def _persist_to_redis(self, record: ExecutionRecord) -> None:
        """Persist execution record to Redis."""
        try:
            import json

            key = f"execution:{record.id}"
            data = {
                "id": record.id,
                "agent_name": record.agent_name,
                "task": record.task,
                "success": record.success,
                "timestamp": record.timestamp.isoformat(),
            }
            await self.redis_client.set(key, json.dumps(data), ex=86400 * 7)  # 7 days
        except Exception as e:
            logger.warning(f"Failed to persist to Redis: {e}")


class LearningManager:
    """
    Main orchestrator for the continuous learning system.

    Coordinates all learning components and manages the learning lifecycle.
    """

    def __init__(self, config: LearningConfig):
        self.config = config
        self.logger = InteractionLogger()

        # Initialize components
        self.critic = (
            CriticAgent(
                llm_api_url=config.llm_api_url,
                llm_model=config.llm_model,
                auto_approve_threshold=config.auto_approve_threshold,
            )
            if config.critic_enabled
            else None
        )

        self.reflection = (
            ReflectionAgent(
                llm_api_url=config.llm_api_url,
                llm_model=config.llm_model,
                embeddings_api_url=config.embeddings_api_url,
            )
            if config.reflection_enabled
            else None
        )

        self.synthesizer = (
            SkillSynthesizer(
                llm_api_url=config.llm_api_url,
                llm_model=config.llm_model,
                critic=self.critic,
                discord_mcp_url=config.discord_mcp_url
                if config.discord_approvals_enabled
                else None,
                registry_url=config.registry_url,
                max_revisions=config.max_skill_revisions,
            )
            if config.auto_synthesis_enabled and self.critic
            else None
        )

        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start the learning system."""
        if self._running:
            return

        self._running = True
        logger.info("Starting Learning Manager")

        # Start passive monitoring loop first (collects data for other loops)
        if self.config.passive_monitoring_enabled:
            task = asyncio.create_task(self._passive_monitoring_loop())
            self._tasks.append(task)
            logger.info("Passive monitoring enabled")

        # Start background tasks
        if self.config.reflection_enabled:
            task = asyncio.create_task(self._reflection_loop())
            self._tasks.append(task)

        if self.config.auto_synthesis_enabled:
            task = asyncio.create_task(self._synthesis_loop())
            self._tasks.append(task)

    async def stop(self) -> None:
        """Stop the learning system."""
        self._running = False

        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        self._tasks.clear()
        logger.info("Learning Manager stopped")

    async def on_execution_complete(
        self,
        execution_id: str,
        agent_name: str,
        task: str,
        trace: list[dict[str, Any]],
        outcome: dict[str, Any],
        success: bool,
    ) -> ExecutionAnalysis | None:
        """Handle a completed agent execution."""
        # Log the execution
        record = await self.logger.log_execution(
            execution_id=execution_id,
            agent_name=agent_name,
            task=task,
            trace=trace,
            outcome=outcome,
            success=success,
        )

        # Analyze with Critic if enabled
        if self.critic:
            analysis = await self.critic.analyze_execution(
                execution_id=execution_id,
                agent_name=agent_name,
                task_summary=task,
                execution_trace=trace,
                outcome=outcome,
            )
            record.analysis = analysis

            # Check for skill opportunities
            if analysis.skill_opportunities and self.synthesizer:
                for opportunity in analysis.skill_opportunities:
                    if opportunity.get("confidence", 0) >= 0.7:
                        logger.info(f"Skill opportunity identified: {opportunity.get('name')}")
                        # Queue for synthesis
                        await self._queue_skill_opportunity(opportunity, record)

            return analysis

        return None

    async def on_discord_feedback(
        self,
        message_id: str,
        channel_id: str,
        reaction: str,
        user: str,
    ) -> None:
        """Handle Discord feedback (emoji reactions)."""
        # Log the interaction
        await self.logger.log_discord_interaction(
            message_id=message_id,
            channel_id=channel_id,
            content="",
            reactions=[reaction],
        )

        # Process skill approval reactions
        if self.synthesizer:
            # Find candidate by message ID
            for candidate_id, candidate in self.synthesizer.candidates.items():
                if candidate.discord_message_id == message_id:
                    await self.synthesizer.process_approval_reaction(
                        candidate_id=candidate_id,
                        reaction=reaction,
                        user=user,
                    )
                    break

    async def get_reflection_report(self, hours: int = 24) -> ReflectionReport | None:
        """Generate a reflection report."""
        if not self.reflection:
            return None

        return await self.reflection.generate_reflection_report(period_hours=hours)

    async def get_knowledge(
        self,
        query: str,
        limit: int = 10,
    ) -> list[Knowledge]:
        """Query the knowledge base."""
        if not self.reflection:
            return []

        # For now, return from cache
        # In production, would query Qdrant for semantic search
        return self.reflection.knowledge_cache[-limit:]

    async def run_learning_cycle(self, hours: int | None = None) -> dict[str, Any]:
        """
        Manually trigger a learning cycle.

        Runs one iteration of reflection and synthesis without waiting
        for the background loops. Useful for testing and on-demand learning.

        Args:
            hours: Look back period in hours (defaults to reflection_interval_hours)

        Returns:
            Summary of what was processed in the cycle
        """
        if hours is None:
            hours = self.config.reflection_interval_hours

        result: dict[str, Any] = {
            "reflection_report": None,
            "knowledge_extracted": 0,
            "patterns_found": 0,
            "synthesis_triggered": False,
        }

        # Run reflection
        if self.reflection:
            try:
                report = await self.get_reflection_report(hours=hours)
                if report:
                    result["reflection_report"] = {
                        "total_executions": report.total_executions,
                        "success_rate": report.success_rate,
                        "key_patterns_count": len(report.key_patterns),
                    }
                    await self._post_reflection_to_discord(report)

                # Extract knowledge
                executions = self.logger.get_recent_executions(hours=hours)
                if executions:
                    knowledge = await self.reflection.extract_knowledge(
                        executions=[
                            {
                                "id": e.id,
                                "agent": e.agent_name,
                                "task": e.task,
                                "success": e.success,
                            }
                            for e in executions
                        ],
                        interactions=self.logger.discord_interactions[-50:],
                        hours=hours,
                    )
                    result["knowledge_extracted"] = len(knowledge) if knowledge else 0

            except Exception as e:
                logger.error(f"Reflection phase failed: {e}")
                result["reflection_error"] = str(e)

        # Run synthesis
        if self.synthesizer:
            try:
                patterns = self.logger.get_successful_patterns(
                    min_occurrences=self.config.min_examples_for_skill
                )
                result["patterns_found"] = len(patterns)

                for pattern in patterns:
                    execution_ids = pattern.get("executions", [])
                    executions = [e for e in self.logger.executions if e.id in execution_ids]

                    if executions:
                        await self.synthesizer.run_synthesis_pipeline(
                            patterns=[pattern],
                            executions=[
                                {"id": e.id, "task": e.task, "trace": e.trace, "outcome": e.outcome}
                                for e in executions
                            ],
                        )
                        result["synthesis_triggered"] = True

            except Exception as e:
                logger.error(f"Synthesis phase failed: {e}")
                result["synthesis_error"] = str(e)

        logger.info(f"Learning cycle complete: {result}")
        return result

    async def _reflection_loop(self) -> None:
        """Background loop for periodic reflection."""
        while self._running:
            try:
                # Wait for reflection interval
                await asyncio.sleep(self.config.reflection_interval_hours * 3600)

                if not self._running:
                    break

                # Generate reflection report
                report = await self.get_reflection_report(
                    hours=self.config.reflection_interval_hours
                )

                if report:
                    # Post to Discord
                    await self._post_reflection_to_discord(report)

                    # Extract knowledge from recent executions
                    executions = self.logger.get_recent_executions(
                        hours=self.config.reflection_interval_hours
                    )
                    if executions and self.reflection:
                        await self.reflection.extract_knowledge(
                            executions=[
                                {
                                    "id": e.id,
                                    "agent": e.agent_name,
                                    "task": e.task,
                                    "success": e.success,
                                }
                                for e in executions
                            ],
                            interactions=self.logger.discord_interactions[-50:],
                            hours=self.config.reflection_interval_hours,
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reflection loop error: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error

    async def _synthesis_loop(self) -> None:
        """Background loop for skill synthesis."""
        while self._running:
            try:
                # Check every hour for synthesis opportunities
                await asyncio.sleep(3600)

                if not self._running:
                    break

                # Get successful patterns
                patterns = self.logger.get_successful_patterns(
                    min_occurrences=self.config.min_examples_for_skill
                )

                for pattern in patterns:
                    # Get executions for this pattern
                    execution_ids = pattern.get("executions", [])
                    executions = [e for e in self.logger.executions if e.id in execution_ids]

                    if executions and self.synthesizer:
                        # Run synthesis pipeline
                        await self.synthesizer.run_synthesis_pipeline(
                            patterns=[pattern],
                            executions=[
                                {"id": e.id, "task": e.task, "trace": e.trace, "outcome": e.outcome}
                                for e in executions
                            ],
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Synthesis loop error: {e}")
                await asyncio.sleep(300)

    async def _passive_monitoring_loop(self) -> None:
        """
        Background loop for passive monitoring.

        Polls Temporal, Discord, and events to collect execution data
        without requiring explicit callbacks from other agents.
        """
        # Lazy import to avoid circular dependencies
        try:
            from learning_agent.builder import ExecutionRecordBuilder, merge_records
            from learning_agent.discovery import AgentDiscoveryService
            from learning_agent.observers.discord import DiscordMonitor
            from learning_agent.observers.events import EventCollector
            from learning_agent.observers.temporal import WorkflowObserver
        except ImportError:
            logger.warning(
                "Passive monitoring components not available. "
                "Install learning-agent package for passive monitoring."
            )
            return

        # Initialize observers
        discovery = AgentDiscoveryService(registry_url=self.config.registry_url)
        workflow_observer = WorkflowObserver(
            temporal_host=self.config.temporal_host,
            temporal_namespace=self.config.temporal_namespace,
        )
        discord_monitor = DiscordMonitor(discord_mcp_url=self.config.discord_mcp_url)
        event_collector = EventCollector(redis_url=self.config.redis_url)
        record_builder = ExecutionRecordBuilder()

        last_workflow_poll = datetime.now(UTC) - timedelta(minutes=5)
        last_discord_poll = datetime.now(UTC) - timedelta(minutes=30)

        logger.info("Passive monitoring loop started")

        while self._running:
            try:
                now = datetime.now(UTC)
                records = []

                # Poll Temporal for completed workflows
                workflows = await workflow_observer.poll_completed_workflows(
                    since=last_workflow_poll
                )
                last_workflow_poll = now

                for wf in workflows:
                    try:
                        # Get workflow details
                        wf_with_details = await workflow_observer.get_workflow_with_details(
                            wf.workflow_id
                        )
                        if wf_with_details:
                            record = record_builder.from_workflow(wf_with_details)
                            records.append(record)
                            logger.debug(
                                f"Captured workflow execution: {wf.workflow_id} "
                                f"({wf.workflow_type})"
                            )
                    except Exception as e:
                        logger.debug(f"Failed to process workflow {wf.workflow_id}: {e}")

                # Poll Discord for new messages (less frequently)
                discord_poll_age = (now - last_discord_poll).total_seconds()
                if discord_poll_age >= self.config.discord_poll_interval_seconds:
                    messages = await discord_monitor.poll_agent_messages(since=last_discord_poll)
                    last_discord_poll = now

                    # Enrich with reactions
                    messages = await discord_monitor.enrich_with_reactions(messages)

                    for msg in messages:
                        try:
                            record = record_builder.from_discord_message(msg)
                            records.append(record)
                            logger.debug(
                                f"Captured Discord output: {msg.message_id} ({msg.channel_name})"
                            )
                        except Exception as e:
                            logger.debug(f"Failed to process message {msg.message_id}: {e}")

                # Collect and correlate events
                if self.config.event_subscription_enabled:
                    events = await event_collector.collect_recent_events(
                        since=now - timedelta(minutes=5)
                    )
                    chains = event_collector.correlate_events(events)

                    for chain in chains:
                        try:
                            record = record_builder.from_event_chain(chain)
                            records.append(record)
                            logger.debug(
                                f"Captured event chain: {chain.correlation_id} "
                                f"({len(chain.events)} events)"
                            )
                        except Exception as e:
                            logger.debug(f"Failed to process event chain: {e}")

                # Merge and deduplicate records
                if records:
                    records = merge_records(records)
                    logger.info(f"Passive monitoring: {len(records)} executions captured")

                    # Feed to the learning pipeline
                    for record in records:
                        await self._process_passive_execution(record)

                # Wait before next poll
                await asyncio.sleep(self.config.workflow_poll_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Passive monitoring loop error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error

        # Cleanup
        await workflow_observer.close()
        await discord_monitor.close()
        await event_collector.close()
        await discovery.close()

    async def _process_passive_execution(self, record: Any) -> None:
        """
        Process a passively captured execution record.

        This is similar to on_execution_complete but accepts records
        from passive monitoring sources.
        """
        # Log the execution
        internal_record = await self.logger.log_execution(
            execution_id=record.id,
            agent_name=record.agent_name,
            task=record.task,
            trace=record.trace,
            outcome=record.outcome,
            success=record.success,
        )

        # Analyze with Critic if enabled
        if self.critic:
            try:
                analysis = await self.critic.analyze_execution(
                    execution_id=record.id,
                    agent_name=record.agent_name,
                    task_summary=record.task,
                    execution_trace=record.trace,
                    outcome=record.outcome,
                )
                internal_record.analysis = analysis

                # Check for skill opportunities
                if analysis.skill_opportunities and self.synthesizer:
                    for opportunity in analysis.skill_opportunities:
                        if opportunity.get("confidence", 0) >= 0.7:
                            logger.info(
                                f"Skill opportunity from passive observation: "
                                f"{opportunity.get('name')}"
                            )
                            await self._queue_skill_opportunity(opportunity, internal_record)

            except Exception as e:
                logger.debug(f"Critic analysis failed for {record.id}: {e}")

    async def _queue_skill_opportunity(
        self,
        opportunity: dict[str, Any],
        record: ExecutionRecord,
    ) -> None:
        """Queue a skill opportunity for synthesis."""
        # Store for later synthesis
        # In production, would use Redis or a proper queue
        logger.info(f"Queued skill opportunity: {opportunity.get('name')}")

    async def _post_reflection_to_discord(self, report: ReflectionReport) -> None:
        """Post reflection report to Discord."""
        if not self.config.discord_mcp_url:
            return

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.config.discord_mcp_url}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "send_message",
                            "arguments": {
                                "channel_id": self.config.learning_channel,
                                "content": report.to_discord_message(),
                            },
                        },
                    },
                    timeout=30.0,
                )
        except Exception as e:
            logger.warning(f"Failed to post reflection to Discord: {e}")


# Singleton instance
_learning_manager: LearningManager | None = None


def get_learning_manager(config: LearningConfig | None = None) -> LearningManager:
    """Get or create the learning manager singleton."""
    global _learning_manager
    if _learning_manager is None:
        if config is None:
            config = LearningConfig()
        _learning_manager = LearningManager(config)
    return _learning_manager
