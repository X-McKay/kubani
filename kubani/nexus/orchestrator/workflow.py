"""Nexus Orchestrator Temporal Workflow.

This is the core 'always-on' workflow that represents the Nexus agent's
lifecycle. It uses the 'entity workflow' pattern — a long-running workflow
that maintains state and responds to signals (user messages) and queries
(status checks from the UI).

Key design decisions:
- The workflow is deterministic: all non-deterministic work (LLM calls,
  database access, network I/O) happens in activities.
- State is maintained in the workflow and queryable by the UI.
- User messages arrive as Temporal signals.
- The workflow uses continue-as-new to prevent unbounded history growth.

Workflow lifecycle:
    1. Start → IDLE
    2. Receive user message signal → PROCESSING
    3. Recall memories → PLANNING
    4. Plan response (LLM) → EXECUTING (if plan needed)
    5. Execute plan steps → EXECUTING
    6. Generate response (LLM) → PROCESSING
    7. Publish response → IDLE
    8. Wait for next signal → goto 2
    9. After N iterations → continue-as-new
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

# Use workflow-safe imports (no non-deterministic modules at top level)
with workflow.unsafe.imports_passed_through():
    from kubani.nexus.models.messages import (
        AgentMessage,
        ConversationMessage,
        MessageRole,
        MessageSource,
        UserMessage,
    )
    from kubani.nexus.models.state import (
        ExecutionPlan,
        NexusStatus,
        NexusWorkflowState,
        PlanStep,
    )

logger = logging.getLogger(__name__)

# Retry policy for LLM-based activities (may be slow)
LLM_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
    non_retryable_error_types=["ValidationError"],
)

# Retry policy for infrastructure activities (fast, reliable)
INFRA_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
)

# Continue-as-new after this many message cycles to prevent history bloat
MAX_ITERATIONS_BEFORE_CONTINUE = 100


@workflow.defn
class NexusOrchestratorWorkflow:
    """The core Nexus agent workflow.

    This is a long-running 'entity workflow' that:
    - Maintains conversational state
    - Receives user messages via signals
    - Plans and executes multi-step tasks
    - Publishes responses via activities
    - Supports queries for real-time UI updates
    """

    def __init__(self) -> None:
        self._state = NexusWorkflowState(user_id="default")
        self._pending_messages: list[dict[str, Any]] = []
        self._iteration_count = 0
        self._should_continue_as_new = False

    # =================================================================
    # Signals (inbound events)
    # =================================================================

    @workflow.signal
    async def user_message(self, message_data: dict[str, Any]) -> None:
        """Signal handler for incoming user messages.

        The Gateway sends this signal when a user message arrives.
        The message is queued and processed in the main workflow loop.

        Args:
            message_data: Serialized UserMessage dict.
        """
        self._pending_messages.append(message_data)

    @workflow.signal
    async def approval_decision(self, decision_data: dict[str, Any]) -> None:
        """Signal handler for HITL approval decisions.

        Args:
            decision_data: Dict with approval_id, approved (bool), reason.
        """
        # Store the decision for the waiting approval step
        self._pending_messages.append({
            **decision_data,
            "_type": "approval_decision",
        })

    # =================================================================
    # Queries (state inspection)
    # =================================================================

    @workflow.query
    def get_state(self) -> dict[str, Any]:
        """Query handler for the current workflow state.

        The UI backend calls this to get real-time status updates.

        Returns:
            Serialized NexusWorkflowState dict.
        """
        return self._state.to_dict()

    @workflow.query
    def get_status(self) -> str:
        """Query handler for just the status string.

        Returns:
            Current NexusStatus value.
        """
        return self._state.status.value

    @workflow.query
    def get_current_plan(self) -> dict[str, Any] | None:
        """Query handler for the current execution plan.

        Returns:
            Serialized ExecutionPlan dict, or None.
        """
        if self._state.current_plan:
            return self._state.current_plan.model_dump(mode="json")
        return None

    # =================================================================
    # Main Workflow Loop
    # =================================================================

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Main workflow execution loop.

        This loop runs indefinitely, processing user messages as they arrive
        via signals. It uses continue-as-new to prevent unbounded history.

        Args:
            input_data: Dict containing:
                - user_id: str - The primary user.
                - conversation_id: str - Initial conversation ID.
                - restored_history: list[dict] - Messages from previous
                  continue-as-new (if any).

        Returns:
            Dict with final state (only on graceful shutdown).
        """
        self._state.user_id = input_data.get("user_id", "default")
        self._state.conversation_id = input_data.get("conversation_id", "")

        # Restore history from previous continue-as-new
        restored = input_data.get("restored_history", [])
        for msg_data in restored:
            self._state.add_message(ConversationMessage.model_validate(msg_data))

        workflow.logger.info(
            f"Nexus workflow started for user {self._state.user_id}"
        )

        while not self._should_continue_as_new:
            # Wait for a message signal
            await workflow.wait_condition(lambda: len(self._pending_messages) > 0)

            # Process all pending messages
            while self._pending_messages:
                message_data = self._pending_messages.pop(0)

                # Skip approval decisions (handled separately)
                if message_data.get("_type") == "approval_decision":
                    continue

                await self._process_message(message_data)

                self._iteration_count += 1
                if self._iteration_count >= MAX_ITERATIONS_BEFORE_CONTINUE:
                    self._should_continue_as_new = True
                    break

        # Continue-as-new to prevent history bloat
        workflow.logger.info("Continuing as new to reset history")
        workflow.continue_as_new(
            {
                "user_id": self._state.user_id,
                "conversation_id": self._state.conversation_id,
                "restored_history": [
                    msg.model_dump(mode="json")
                    for msg in self._state.conversation_history[-20:]
                ],
            }
        )

    # =================================================================
    # Message Processing Pipeline
    # =================================================================

    async def _process_message(self, message_data: dict[str, Any]) -> None:
        """Process a single user message through the full pipeline.

        Pipeline:
            1. Parse and persist the user message
            2. Recall relevant memories
            3. Plan the response (LLM)
            4. Execute plan steps (if needed)
            5. Generate and publish the response

        Args:
            message_data: Serialized UserMessage dict.
        """
        try:
            user_msg = UserMessage.from_dict(message_data)
        except Exception:
            workflow.logger.error(f"Invalid message data: {message_data}")
            return

        self._state.status = NexusStatus.PROCESSING
        self._state.conversation_id = user_msg.conversation_id

        # Add user message to state
        self._state.add_message(ConversationMessage(
            role=MessageRole.USER,
            content=user_msg.text,
            source=user_msg.source,
        ))

        # Step 1: Persist user message
        await workflow.execute_activity(
            "persist_message",
            args=[{
                "conversation_id": user_msg.conversation_id,
                "user_id": user_msg.user_id,
                "role": "user",
                "content": user_msg.text,
                "source": user_msg.source.value,
            }],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=INFRA_RETRY_POLICY,
        )

        # Step 2: Recall memories
        self._state.status = NexusStatus.PROCESSING
        memories_result = await workflow.execute_activity(
            "recall_memories_activity",
            args=[{
                "query": user_msg.text,
                "user_id": user_msg.user_id,
                "limit": 5,
            }],
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=INFRA_RETRY_POLICY,
        )
        memories = memories_result.get("memories", [])

        # Step 3: Plan the response
        self._state.status = NexusStatus.PLANNING
        plan_result = await workflow.execute_activity(
            "plan_response",
            args=[{
                "user_message": user_msg.text,
                "conversation_history": [
                    msg.model_dump(mode="json")
                    for msg in self._state.conversation_history
                ],
                "available_skills": await self._get_available_skills(),
                "memories": memories,
            }],
            start_to_close_timeout=timedelta(minutes=2),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=LLM_RETRY_POLICY,
        )

        if not plan_result.get("needs_plan", False):
            # Direct response — no plan needed
            response_text = plan_result.get("direct_response", "")
            await self._publish_and_persist_response(
                user_msg.conversation_id, user_msg.user_id, response_text
            )
            self._state.status = NexusStatus.IDLE
            return

        # Step 4: Execute the plan
        self._state.status = NexusStatus.EXECUTING
        plan = ExecutionPlan(
            goal=plan_result.get("goal", ""),
            steps=[
                PlanStep(
                    id=step.get("id", i + 1),
                    description=step.get("description", ""),
                    skill_name=step.get("skill_name"),
                )
                for i, step in enumerate(plan_result.get("steps", []))
            ],
        )
        self._state.current_plan = plan
        self._state.current_goal = plan.goal

        step_results = await self._execute_plan(plan, user_msg)

        # Step 5: Generate final response
        self._state.status = NexusStatus.PROCESSING
        response_result = await workflow.execute_activity(
            "generate_response",
            args=[{
                "user_message": user_msg.text,
                "goal": plan.goal,
                "step_results": step_results,
                "conversation_history": [
                    msg.model_dump(mode="json")
                    for msg in self._state.conversation_history
                ],
            }],
            start_to_close_timeout=timedelta(minutes=2),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=LLM_RETRY_POLICY,
        )

        response_text = response_result.get("response_text", "I completed the task.")

        # Publish and persist the response
        await self._publish_and_persist_response(
            user_msg.conversation_id, user_msg.user_id, response_text
        )

        # Store memory of this interaction
        await workflow.execute_activity(
            "store_memory_activity",
            args=[{
                "content": f"User asked: {user_msg.text}\nI responded: {response_text[:200]}",
                "user_id": user_msg.user_id,
                "metadata": {"conversation_id": user_msg.conversation_id},
            }],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=INFRA_RETRY_POLICY,
        )

        self._state.current_plan = None
        self._state.current_goal = None
        self._state.status = NexusStatus.IDLE

    # =================================================================
    # Plan Execution
    # =================================================================

    async def _execute_plan(
        self, plan: ExecutionPlan, user_msg: UserMessage
    ) -> list[dict[str, Any]]:
        """Execute all steps in a plan sequentially.

        Args:
            plan: The execution plan to run.
            user_msg: The original user message (for context).

        Returns:
            List of result dicts from each step.
        """
        step_results = []

        for step in plan.steps:
            step.status = "running"
            self._state.actions_count += 1

            from datetime import datetime, timezone

            step.started_at = datetime.now(timezone.utc).isoformat()

            # Log action start
            action_result = await workflow.execute_activity(
                "log_action_activity",
                args=[{
                    "conversation_id": user_msg.conversation_id,
                    "action_type": "skill_execution" if step.skill_name else "reasoning",
                    "description": step.description,
                    "input_summary": step.skill_name or "LLM reasoning",
                }],
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=INFRA_RETRY_POLICY,
            )
            action_id = action_result.get("action_id")

            if step.skill_name:
                # Execute a skill
                result = await workflow.execute_activity(
                    "execute_skill_activity",
                    args=[{
                        "skill_name": step.skill_name,
                        "inputs": {"task": step.description, "context": user_msg.text},
                        "timeout_seconds": 60,
                        "conversation_id": user_msg.conversation_id,
                    }],
                    start_to_close_timeout=timedelta(minutes=5),
                    heartbeat_timeout=timedelta(minutes=1),
                    retry_policy=LLM_RETRY_POLICY,
                )
            else:
                # Use LLM for reasoning steps
                result = await workflow.execute_activity(
                    "generate_response",
                    args=[{
                        "user_message": step.description,
                        "goal": plan.goal,
                        "step_results": step_results,
                        "conversation_history": [],
                    }],
                    start_to_close_timeout=timedelta(minutes=2),
                    heartbeat_timeout=timedelta(seconds=30),
                    retry_policy=LLM_RETRY_POLICY,
                )
                result = {
                    "success": True,
                    "output": result.get("response_text", ""),
                    "error": None,
                    "duration_ms": 0,
                }

            step.completed_at = datetime.now(timezone.utc).isoformat()

            if result.get("success"):
                step.status = "completed"
                step.result_summary = str(result.get("output", ""))[:200]
            else:
                step.status = "failed"
                step.error = result.get("error", "Unknown error")

            # Log action completion
            if action_id:
                await workflow.execute_activity(
                    "log_action_activity",
                    args=[{
                        "action_id": action_id,
                        "conversation_id": user_msg.conversation_id,
                        "action_type": "skill_execution",
                        "description": step.description,
                        "output_summary": step.result_summary or "",
                        "error_message": step.error,
                        "duration_ms": result.get("duration_ms", 0),
                    }],
                    start_to_close_timeout=timedelta(seconds=10),
                    retry_policy=INFRA_RETRY_POLICY,
                )

            step_results.append(result)

        return step_results

    # =================================================================
    # Helpers
    # =================================================================

    async def _publish_and_persist_response(
        self, conversation_id: str, user_id: str, text: str
    ) -> None:
        """Publish a response via pub/sub and persist it to the database.

        Args:
            conversation_id: The conversation to publish to.
            user_id: The user who will receive the response.
            text: The response text.
        """
        # Add to workflow state
        self._state.add_message(ConversationMessage(
            role=MessageRole.ASSISTANT,
            content=text,
            source=MessageSource.SYSTEM,
        ))

        # Persist to database
        await workflow.execute_activity(
            "persist_message",
            args=[{
                "conversation_id": conversation_id,
                "user_id": user_id,
                "role": "assistant",
                "content": text,
                "source": "system",
            }],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=INFRA_RETRY_POLICY,
        )

        # Publish via Redis pub/sub
        await workflow.execute_activity(
            "publish_response_activity",
            args=[{
                "conversation_id": conversation_id,
                "text": text,
            }],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=INFRA_RETRY_POLICY,
        )

    async def _get_available_skills(self) -> list[str]:
        """Get the list of available (approved) skills.

        Returns a static list for now; in production this would query
        the Skill Registry.
        """
        # TODO: Query the skill registry via an activity
        return [
            "web/fetch-url",
            "web/search",
            "text/summarize",
            "k8s/get-pods",
            "k8s/get-events",
            "news/fetch-headlines",
        ]
