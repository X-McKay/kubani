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

Agentic loop (Strands Agent SDK):
    1. Start → IDLE
    2. Receive user message signal → PROCESSING
    3. Recall memories
    4. Run Strands agent (single activity):
       - Agent has core tools (read_file, write_file, edit_file, bash, register_skill)
       - Agent runs think→act→observe loop internally via OpenAI tool calling
       - Loop terminates when LLM produces text without tool calls
    5. Publish response → IDLE
    6. Wait for next signal → goto 2
    7. After N iterations → continue-as-new
"""

from __future__ import annotations

import logging
import os
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
    # Message Processing — Agentic Loop (Pi-style)
    # =================================================================

    async def _process_message(self, message_data: dict[str, Any]) -> None:
        """Process a single user message.

        Delegates to the agentic loop (default) or the legacy
        plan-then-execute pipeline based on NEXUS_AGENTIC_MODE.

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

        # Persist user message
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

        # Recall memories
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

        # Run agentic loop
        response_text = await self._run_agentic_loop(user_msg, memories)

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
        self._state.tool_call_history = []
        self._state.status = NexusStatus.IDLE

    async def _run_agentic_loop(
        self, user_msg: UserMessage, memories: list[str]
    ) -> str:
        """Run the agentic loop using Strands Agent SDK.

        Delegates the entire think→act→observe loop to a single Temporal
        activity that creates a Strands Agent. The agent handles tool
        calling, result injection, and loop termination internally.

        Args:
            user_msg: The user message being processed.
            memories: Relevant memories from the memory system.

        Returns:
            The final response text.
        """
        self._state.status = NexusStatus.PROCESSING

        result = await workflow.execute_activity(
            "run_agent_turn",
            args=[{
                "user_message": user_msg.text,
                "conversation_history": [
                    msg.model_dump(mode="json")
                    for msg in self._state.conversation_history
                ],
                "memories": memories,
                "user_id": user_msg.user_id,
            }],
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=LLM_RETRY_POLICY,
        )

        return result.get("response_text", "Done.")

    # =================================================================
    # (Legacy _execute_plan removed — replaced by _run_agentic_loop)
    # =================================================================

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
        """Get the list of available skills (legacy helper).

        The agentic loop uses the list_available_tools activity instead.
        """
        return []
