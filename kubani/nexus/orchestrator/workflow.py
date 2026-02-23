"""Nexus Orchestrator Temporal Workflow.

This is the core 'always-on' workflow that represents the Nexus agent's
lifecycle. It uses the 'entity workflow' pattern — a long-running workflow
that maintains state and responds to signals (user messages, proactive
missions) and queries (status checks from the UI).

Key design decisions:
- The workflow is deterministic: all non-deterministic work (LLM calls,
  database access, network I/O) happens in activities.
- State is maintained in the workflow and queryable by the UI.
- User messages arrive as Temporal signals (``user_message``).
- Proactive missions arrive as Temporal signals (``proactive_mission``),
  dispatched by NexusHeartbeatWorkflow on a cron schedule.
- The workflow uses continue-as-new to prevent unbounded history growth.

Agentic loop (Strands Agent SDK):
    Reactive (user message):
        1. Start → IDLE
        2. Receive user_message signal → PROCESSING
        3. Recall memories
        4. Run Strands agent (run_agent_turn activity)
        5. Publish response → IDLE
        6. Wait for next signal → goto 2
        7. After N iterations → continue-as-new

    Proactive (mission):
        1. Receive proactive_mission signal → MISSION_RUNNING
        2. Run Strands agent (run_mission_agent_turn activity)
           - Bounded by max_tool_calls
           - Uses policy-scoped MCP clients
        3. If agent found something noteworthy → publish notification
        4. Record run outcome → IDLE
        5. Wait for next signal → goto 2
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
    - Receives user messages via ``user_message`` signals
    - Receives proactive mission dispatches via ``proactive_mission`` signals
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
        self._pending_messages.append({
            **decision_data,
            "_type": "approval_decision",
        })

    @workflow.signal
    async def proactive_mission(self, mission_data: dict[str, Any]) -> None:
        """Signal handler for proactive mission dispatches.

        Sent by NexusHeartbeatWorkflow when a scheduled mission is due.
        The mission is queued alongside user messages and processed in the
        same main loop, ensuring serialized, non-concurrent execution.

        Missions are processed with lower priority than user messages:
        if a user message and a mission arrive simultaneously, the user
        message is always processed first.

        Args:
            mission_data: Serialized NexusMission dict from the heartbeat.
        """
        # Tag the message type so the main loop can dispatch correctly
        self._pending_messages.append({
            **mission_data,
            "_type": "proactive_mission",
        })
        workflow.logger.info(
            f"Queued proactive mission: {mission_data.get('id')} "
            f"({mission_data.get('title', 'untitled')})"
        )

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

        This loop runs indefinitely, processing user messages and proactive
        missions as they arrive via signals. It uses continue-as-new to
        prevent unbounded history.

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
            # Wait for any signal (user message or proactive mission)
            await workflow.wait_condition(lambda: len(self._pending_messages) > 0)

            # Sort pending messages: user messages first, then missions
            # This ensures user interaction is never delayed by background work
            user_msgs = [
                m for m in self._pending_messages
                if m.get("_type") not in ("proactive_mission", "approval_decision")
            ]
            mission_msgs = [
                m for m in self._pending_messages
                if m.get("_type") == "proactive_mission"
            ]
            other_msgs = [
                m for m in self._pending_messages
                if m.get("_type") == "approval_decision"
            ]
            # Rebuild queue: user messages → missions → approvals
            self._pending_messages = user_msgs + mission_msgs + other_msgs

            # Process all pending messages in priority order
            while self._pending_messages:
                message_data = self._pending_messages.pop(0)
                msg_type = message_data.get("_type")

                if msg_type == "approval_decision":
                    # Handled by waiting approval step — skip here
                    continue
                elif msg_type == "proactive_mission":
                    await self._run_mission_turn(message_data)
                else:
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
    # Reactive Message Processing — Agentic Loop (Pi-style)
    # =================================================================

    async def _process_message(self, message_data: dict[str, Any]) -> None:
        """Process a single user message.

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
                "content": (
                    f"User asked: {user_msg.text}\n"
                    f"I responded: {response_text[:200]}"
                ),
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
            memories: Relevant memories recalled for this message.

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
    # Proactive Mission Turn
    # =================================================================

    async def _run_mission_turn(self, mission_data: dict[str, Any]) -> None:
        """Execute a proactive mission turn autonomously.

        The agent works on the mission goal using a bounded tool budget and
        a policy-scoped MCP client set. It only notifies the user if it
        finds something genuinely noteworthy (as determined by the mission's
        ``notify_on`` configuration).

        This method is intentionally separate from ``_process_message`` to
        keep the two execution paths cleanly isolated.

        Args:
            mission_data: Serialized NexusMission dict from the heartbeat.
        """
        mission_id = mission_data.get("id", "unknown")
        mission_title = mission_data.get("title", "Untitled Mission")
        user_id = mission_data.get("user_id", self._state.user_id)

        workflow.logger.info(
            f"Starting mission turn: {mission_id} ({mission_title})"
        )
        self._state.status = NexusStatus.EXECUTING
        self._state.current_goal = f"[Mission] {mission_title}"

        try:
            result = await workflow.execute_activity(
                "run_mission_agent_turn",
                args=[{
                    "mission_id": mission_id,
                    "mission_title": mission_title,
                    "mission_goal": mission_data.get("goal", ""),
                    "user_id": user_id,
                    "mcp_policy": mission_data.get("mcp_policy", "nexus"),
                    "max_tool_calls": mission_data.get("max_tool_calls", 20),
                    "notify_on": mission_data.get("notify_on", ["anomaly", "error"]),
                    # Provide limited conversation context so the agent can
                    # reference recent interactions if relevant
                    "recent_history": [
                        msg.model_dump(mode="json")
                        for msg in self._state.conversation_history[-5:]
                    ],
                }],
                start_to_close_timeout=timedelta(minutes=15),
                heartbeat_timeout=timedelta(minutes=3),
                retry_policy=LLM_RETRY_POLICY,
            )

            # Only publish a notification if the agent decided it was warranted
            if result.get("should_notify") and result.get("notification_text"):
                notification_conversation_id = (
                    self._state.conversation_id
                    or f"mission-notifications-{user_id}"
                )
                await self._publish_and_persist_response(
                    conversation_id=notification_conversation_id,
                    user_id=user_id,
                    text=(
                        f"**Mission Update — {mission_title}**\n\n"
                        f"{result['notification_text']}"
                    ),
                )
                workflow.logger.info(
                    f"Mission {mission_id}: notification published"
                )
            else:
                workflow.logger.info(
                    f"Mission {mission_id}: completed silently "
                    f"(tool_calls={result.get('tool_calls_made', 0)})"
                )

        except Exception as exc:
            workflow.logger.error(
                f"Mission {mission_id} failed: {exc}"
            )
            # On error, always notify the user so they know something went wrong
            notification_conversation_id = (
                self._state.conversation_id
                or f"mission-notifications-{user_id}"
            )
            await self._publish_and_persist_response(
                conversation_id=notification_conversation_id,
                user_id=user_id,
                text=(
                    f"**Mission Error — {mission_title}**\n\n"
                    f"The mission encountered an error: {exc}\n\n"
                    f"The mission will retry on its next scheduled run."
                ),
            )
        finally:
            self._state.current_goal = None
            self._state.status = NexusStatus.IDLE

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
