"""
Orchestrator Agent - Manages investigation lifecycle and coordinates workers.

The Orchestrator subscribes to INVESTIGATION_REQUESTED events, creates
a state machine for each investigation, delegates tasks to specialized
workers, and ensures a coherent narrative is maintained throughout.
"""

import asyncio
import hashlib
import logging
import os
import uuid
from typing import Any

import redis.asyncio as aioredis
from strands import Agent

from cluster_monitor.models import (
    CorrelatedIssue,
    InvestigationStage,
    InvestigationState,
    WorkerResult,
    WorkerTask,
)
from core_agents.events import Event, EventBus, EventType, get_event_bus
from core_agents.factory import AgentConfig, AgentFactory

logger = logging.getLogger(__name__)


class InvestigationOrchestrator:
    """
    Orchestrates the investigation lifecycle.

    Responsibilities:
    - Create investigation state and Discord thread
    - Follow investigation workflow through defined stages
    - Delegate tasks to worker agents
    - Synthesize worker results and decide next steps
    - Ensure consistent narrative via Narrator worker
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        redis_client: aioredis.Redis | None = None,
        factory: AgentFactory | None = None,
    ):
        self.event_bus = event_bus or get_event_bus()
        self._redis = redis_client
        self.factory = factory or AgentFactory()
        self._active_investigations: dict[str, InvestigationState] = {}

    async def _ensure_redis(self) -> aioredis.Redis:
        """Lazy initialization of Redis client."""
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD") or None,
                decode_responses=True,
            )
        return self._redis

    async def _save_state(self, state: InvestigationState) -> None:
        """Save investigation state to Redis."""
        redis = await self._ensure_redis()
        key = f"investigation:{state.investigation_id}"
        await redis.setex(
            key,
            3600 * 24,  # 24 hour TTL
            state.model_dump_json(),
        )

    async def _load_state(self, investigation_id: str) -> InvestigationState | None:
        """Load investigation state from Redis."""
        redis = await self._ensure_redis()
        key = f"investigation:{investigation_id}"
        data = await redis.get(key)
        if data:
            return InvestigationState.model_validate_json(data)
        return None

    async def _delegate_to_worker(
        self, task_type: str, context: dict[str, Any]
    ) -> WorkerResult:
        """
        Delegate a task to a worker agent.

        For now, this is a placeholder that returns mock results.
        In a full implementation, this would invoke actual worker agents.
        """
        task_id = str(uuid.uuid4())[:8]
        logger.info(f"Delegating task {task_id} ({task_type}) to worker")

        # TODO: Implement actual worker invocation
        # For now, return mock success
        return WorkerResult(
            task_id=task_id,
            success=True,
            data={"message": f"Mock result for {task_type}"},
        )

    async def _stage_analyze(self, state: InvestigationState) -> None:
        """
        Stage 1: Analyze the correlated issue.

        - Post initial message to Discord
        - Identify affected resources and pattern
        """
        logger.info(f"[{state.investigation_id}] Stage: ANALYZING")
        state.update_stage(InvestigationStage.ANALYZING)

        # Prepare context for narrator
        event_count = len(state.events)
        pattern = state.findings.get("pattern_type", "unknown")
        namespaces = list({e.namespace for e in state.events})
        resources = [f"{e.resource_kind}/{e.resource_name}" for e in state.events]

        narrator_context = {
            "stage": "initial_analysis",
            "event_count": event_count,
            "pattern": pattern,
            "namespaces": namespaces,
            "resources": resources[:5],  # Limit to first 5
            "message": (
                f"I've detected {event_count} related issue(s) across "
                f"{len(namespaces)} namespace(s). "
                f"The pattern suggests a {pattern} issue affecting: "
                + ", ".join(resources[:3])
                + ("..." if len(resources) > 3 else "")
                + ". Let me investigate further."
            ),
        }

        # Delegate to narrator to post initial message
        result = await self._delegate_to_worker("narrate", narrator_context)
        if result.success:
            state.discord_thread_id = result.data.get("thread_id")
            state.findings["initial_message_posted"] = True

        await self._save_state(state)

    async def _stage_query_memory(self, state: InvestigationState) -> None:
        """
        Stage 2: Query memory for similar past incidents.
        """
        logger.info(f"[{state.investigation_id}] Stage: QUERYING_MEMORY")
        state.update_stage(InvestigationStage.QUERYING_MEMORY)

        # Prepare context for memory worker
        pattern = state.findings.get("pattern_type", "unknown")
        memory_context = {
            "query": f"{pattern} issue in Kubernetes",
            "min_confidence": 0.7,
            "limit": 5,
        }

        # Delegate to memory worker
        result = await self._delegate_to_worker("query_memory", memory_context)
        if result.success:
            past_incidents = result.data.get("learnings", [])
            state.findings["past_incidents"] = past_incidents

            # Narrate findings
            if past_incidents:
                narrator_context = {
                    "stage": "memory_findings",
                    "past_incidents": past_incidents,
                    "message": (
                        f"I found {len(past_incidents)} similar incident(s) in our history. "
                        f"Let me check what we learned from those cases."
                    ),
                }
                await self._delegate_to_worker("narrate", narrator_context)

        await self._save_state(state)

    async def _stage_investigate(self, state: InvestigationState) -> None:
        """
        Stage 3: Perform detailed investigation using diagnostic skills.
        """
        logger.info(f"[{state.investigation_id}] Stage: INVESTIGATING")
        state.update_stage(InvestigationStage.INVESTIGATING)

        # Prepare context for investigator worker
        investigator_context = {
            "events": [e.model_dump() for e in state.events],
            "pattern": state.findings.get("pattern_type", "unknown"),
        }

        # Delegate to investigator worker
        result = await self._delegate_to_worker("investigate", investigator_context)
        if result.success:
            state.findings["diagnostic_results"] = result.data

            # Narrate findings
            narrator_context = {
                "stage": "investigation_findings",
                "findings": result.data,
                "message": (
                    "I've completed the diagnostic investigation. "
                    "Here's what I found..."
                ),
            }
            await self._delegate_to_worker("narrate", narrator_context)

        await self._save_state(state)

    async def _stage_plan_remediation(self, state: InvestigationState) -> None:
        """
        Stage 4: Plan remediation based on findings and memory.
        """
        logger.info(f"[{state.investigation_id}] Stage: PLANNING_REMEDIATION")
        state.update_stage(InvestigationStage.PLANNING_REMEDIATION)

        # Check if we have a known remediation from memory
        past_incidents = state.findings.get("past_incidents", [])
        known_remediation = None
        if past_incidents:
            # Look for successful remediations in past incidents
            for incident in past_incidents:
                if incident.get("resolution_success"):
                    known_remediation = incident.get("resolution_action")
                    break

        remediation_context = {
            "findings": state.findings.get("diagnostic_results", {}),
            "known_remediation": known_remediation,
            "pattern": state.findings.get("pattern_type", "unknown"),
        }

        # Delegate to remediator worker for planning
        result = await self._delegate_to_worker("plan_remediation", remediation_context)
        if result.success:
            state.findings["remediation_plan"] = result.data

            # Narrate the plan
            narrator_context = {
                "stage": "remediation_plan",
                "plan": result.data,
                "message": (
                    "Based on my investigation, here's what I recommend we do..."
                ),
            }
            await self._delegate_to_worker("narrate", narrator_context)

        await self._save_state(state)

    async def _stage_execute_action(self, state: InvestigationState) -> None:
        """
        Stage 5: Execute the remediation action.
        """
        logger.info(f"[{state.investigation_id}] Stage: EXECUTING_ACTION")
        state.update_stage(InvestigationStage.EXECUTING_ACTION)

        remediation_plan = state.findings.get("remediation_plan", {})
        if not remediation_plan:
            logger.warning("No remediation plan available, skipping execution")
            return

        # Delegate to remediator worker for execution
        result = await self._delegate_to_worker("execute_remediation", remediation_plan)
        state.actions_taken.append(
            {
                "action": remediation_plan.get("action"),
                "result": result.model_dump(),
            }
        )

        # Narrate the result
        success_msg = "successfully" if result.success else "encountered an issue while"
        narrator_context = {
            "stage": "action_result",
            "result": result.data,
            "message": f"I {success_msg} executed the remediation action.",
        }
        await self._delegate_to_worker("narrate", narrator_context)

        await self._save_state(state)

    async def _stage_verify(self, state: InvestigationState) -> None:
        """
        Stage 6: Verify that the issue is resolved.
        """
        logger.info(f"[{state.investigation_id}] Stage: VERIFYING")
        state.update_stage(InvestigationStage.VERIFYING)

        # Delegate to investigator worker to check if issue persists
        verification_context = {
            "events": [e.model_dump() for e in state.events],
            "action": "verify_resolution",
        }

        result = await self._delegate_to_worker("verify", verification_context)
        state.findings["verification_result"] = result.data

        # Narrate the verification
        resolved = result.data.get("resolved", False)
        narrator_context = {
            "stage": "verification",
            "resolved": resolved,
            "message": (
                "Great! The issue appears to be resolved."
                if resolved
                else "The issue is still present. Further investigation may be needed."
            ),
        }
        await self._delegate_to_worker("narrate", narrator_context)

        await self._save_state(state)

    async def _stage_summarize(self, state: InvestigationState) -> None:
        """
        Stage 7: Summarize the investigation and store learnings.
        """
        logger.info(f"[{state.investigation_id}] Stage: SUMMARIZING")
        state.update_stage(InvestigationStage.SUMMARIZING)

        # Prepare summary context
        summary_context = {
            "investigation_id": state.investigation_id,
            "events": [e.model_dump() for e in state.events],
            "findings": state.findings,
            "actions_taken": state.actions_taken,
        }

        # Delegate to narrator for final summary
        narrator_context = {
            "stage": "final_summary",
            "summary": summary_context,
            "message": "Here's a complete summary of the investigation...",
        }
        await self._delegate_to_worker("narrate", narrator_context)

        # Store learning in memory
        learning_context = {
            "investigation": summary_context,
            "pattern": state.findings.get("pattern_type", "unknown"),
            "resolution_success": state.findings.get("verification_result", {}).get(
                "resolved", False
            ),
        }
        await self._delegate_to_worker("store_learning", learning_context)

        state.update_stage(InvestigationStage.COMPLETED)
        await self._save_state(state)

    async def conduct_investigation(self, correlated_issue: CorrelatedIssue) -> None:
        """
        Conduct a full investigation following the workflow stages.
        """
        investigation_id = str(uuid.uuid4())[:12]
        logger.info(
            f"Starting investigation {investigation_id} for "
            f"correlation {correlated_issue.correlation_id}"
        )

        # Create investigation state
        state = InvestigationState(
            investigation_id=investigation_id,
            correlation_id=correlated_issue.correlation_id,
            stage=InvestigationStage.ANALYZING,
            events=correlated_issue.events,
        )
        state.findings["pattern_type"] = correlated_issue.pattern_type
        state.findings["severity"] = correlated_issue.severity.value

        self._active_investigations[investigation_id] = state

        try:
            # Follow the investigation workflow
            await self._stage_analyze(state)
            await self._stage_query_memory(state)
            await self._stage_investigate(state)
            await self._stage_plan_remediation(state)
            await self._stage_execute_action(state)
            await self._stage_verify(state)
            await self._stage_summarize(state)

            logger.info(f"Investigation {investigation_id} completed successfully")

        except Exception as e:
            logger.error(f"Investigation {investigation_id} failed: {e}", exc_info=True)
            state.update_stage(InvestigationStage.FAILED)
            state.findings["error"] = str(e)
            await self._save_state(state)

        finally:
            # Clean up active investigation
            self._active_investigations.pop(investigation_id, None)

    async def process_investigation_request(self, event: Event) -> None:
        """Process an INVESTIGATION_REQUESTED event."""
        try:
            correlated_issue = CorrelatedIssue(**event.payload)
            await self.conduct_investigation(correlated_issue)
        except Exception as e:
            logger.error(f"Failed to process investigation request: {e}", exc_info=True)

    async def run(self) -> None:
        """
        Run the orchestrator service.

        Subscribes to INVESTIGATION_REQUESTED events and conducts investigations.
        """
        logger.info("Starting Orchestrator service")

        async for event in self.event_bus.subscribe(
            EventType.INVESTIGATION_REQUESTED,
            consumer_group="orchestrator",
            consumer_name="orchestrator-1",
        ):
            try:
                # Process each investigation in a separate task to allow parallelism
                asyncio.create_task(self.process_investigation_request(event))
            except Exception as e:
                logger.error(f"Error processing investigation request: {e}", exc_info=True)


async def main():
    """Main entry point for the orchestrator service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    orchestrator = InvestigationOrchestrator()
    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())
