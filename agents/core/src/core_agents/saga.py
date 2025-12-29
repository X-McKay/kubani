"""
Temporal Saga Patterns for cross-agent workflows.

Provides patterns for building distributed workflows that can coordinate
across multiple agents with proper compensation (rollback) handling.

Key concepts:
- Saga: A sequence of steps that can be rolled back if any step fails
- Signal Channels: Named channels for cross-workflow communication
- Compensation: Undo actions for each forward step

Usage:
    from core_agents.saga import Saga, SagaStep, SignalChannel

    # Define a saga with compensation steps
    saga = Saga(name="deploy-and-notify")
    saga.add_step(
        SagaStep(
            name="scale-deployment",
            forward=scale_up_activity,
            compensate=scale_down_activity,
        )
    )
    saga.add_step(
        SagaStep(
            name="notify-users",
            forward=send_notification_activity,
            compensate=send_rollback_notification_activity,
        )
    )

    # Execute the saga (auto-compensates on failure)
    result = await saga.execute()

    # Signal channels for cross-workflow coordination
    channel = SignalChannel("remediation-complete")
    await channel.send({"issue_id": "123", "status": "fixed"})

    # In another workflow
    message = await channel.receive(timeout_seconds=300)
"""

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SagaStatus(Enum):
    """Status of a saga execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"


@dataclass
class SagaStep:
    """
    A single step in a saga with forward and compensating actions.

    Attributes:
        name: Human-readable step name
        forward: The action to execute (activity function)
        compensate: The action to run if rollback is needed (optional)
        forward_args: Arguments for the forward action
        compensate_args: Arguments for the compensate action (if different)
        timeout: Timeout for this step
        retry_attempts: Number of retries for forward action
    """

    name: str
    forward: Callable[..., Coroutine[Any, Any, Any]]
    compensate: Callable[..., Coroutine[Any, Any, Any]] | None = None
    forward_args: tuple[Any, ...] = ()
    forward_kwargs: dict[str, Any] = field(default_factory=dict)
    compensate_args: tuple[Any, ...] | None = None
    compensate_kwargs: dict[str, Any] | None = None
    timeout: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    retry_attempts: int = 3


@dataclass
class StepResult:
    """Result of executing a saga step."""

    step_name: str
    success: bool
    result: Any = None
    error: str | None = None
    compensated: bool = False


@dataclass
class SagaResult:
    """Result of executing a complete saga."""

    saga_name: str
    status: SagaStatus
    steps: list[StepResult] = field(default_factory=list)
    final_result: Any = None
    error: str | None = None


class Saga:
    """
    Saga pattern implementation for distributed transactions.

    A saga is a sequence of steps where each step can have a compensation
    (rollback) action. If any step fails, previously completed steps are
    compensated in reverse order.

    Example:
        saga = Saga("order-fulfillment")
        saga.add_step(SagaStep(
            name="reserve-inventory",
            forward=reserve_items,
            compensate=release_reservation,
        ))
        saga.add_step(SagaStep(
            name="charge-payment",
            forward=process_payment,
            compensate=refund_payment,
        ))
        saga.add_step(SagaStep(
            name="ship-order",
            forward=create_shipment,
            compensate=cancel_shipment,
        ))

        result = await saga.execute()
        if result.status == SagaStatus.COMPLETED:
            print("Order fulfilled successfully")
        elif result.status == SagaStatus.COMPENSATED:
            print(f"Order failed, rolled back: {result.error}")
    """

    def __init__(self, name: str):
        self.name = name
        self.steps: list[SagaStep] = []
        self._completed_steps: list[tuple[SagaStep, Any]] = []

    def add_step(self, step: SagaStep) -> "Saga":
        """Add a step to the saga. Returns self for chaining."""
        self.steps.append(step)
        return self

    async def execute(self) -> SagaResult:
        """
        Execute the saga, compensating on failure.

        Returns:
            SagaResult with status and step results
        """
        result = SagaResult(saga_name=self.name, status=SagaStatus.RUNNING)
        self._completed_steps = []

        logger.info(f"Starting saga: {self.name} with {len(self.steps)} steps")

        for step in self.steps:
            step_result = await self._execute_step(step)
            result.steps.append(step_result)

            if step_result.success:
                self._completed_steps.append((step, step_result.result))
                logger.debug(f"Saga step completed: {step.name}")
            else:
                logger.error(f"Saga step failed: {step.name} - {step_result.error}")
                result.error = f"Step '{step.name}' failed: {step_result.error}"
                result.status = SagaStatus.COMPENSATING

                # Compensate completed steps in reverse order
                await self._compensate(result)
                return result

        result.status = SagaStatus.COMPLETED
        result.final_result = result.steps[-1].result if result.steps else None
        logger.info(f"Saga completed successfully: {self.name}")
        return result

    async def _execute_step(self, step: SagaStep) -> StepResult:
        """Execute a single saga step."""
        try:
            # In a real Temporal workflow, this would use workflow.execute_activity
            # Here we call the function directly for the pattern definition
            result = await step.forward(*step.forward_args, **step.forward_kwargs)
            return StepResult(step_name=step.name, success=True, result=result)
        except Exception as e:
            logger.error(f"Step {step.name} failed: {e}")
            return StepResult(step_name=step.name, success=False, error=str(e))

    async def _compensate(self, result: SagaResult) -> None:
        """Run compensation for completed steps in reverse order."""
        logger.info(f"Compensating {len(self._completed_steps)} completed steps")

        for step, forward_result in reversed(self._completed_steps):
            if step.compensate is None:
                logger.warning(f"No compensate action for step: {step.name}")
                continue

            try:
                # Use compensate args if provided, otherwise use forward result
                comp_args = step.compensate_args or (forward_result,)
                comp_kwargs = step.compensate_kwargs or {}

                await step.compensate(*comp_args, **comp_kwargs)

                # Mark step as compensated in results
                for step_result in result.steps:
                    if step_result.step_name == step.name:
                        step_result.compensated = True
                        break

                logger.debug(f"Compensated step: {step.name}")

            except Exception as e:
                logger.error(f"Compensation failed for {step.name}: {e}")
                # Continue compensating other steps even if one fails
                result.status = SagaStatus.FAILED
                result.error = f"Compensation failed: {e}"
                return

        result.status = SagaStatus.COMPENSATED
        logger.info(f"Saga compensation complete: {self.name}")


# Signal channel types for cross-workflow communication
@dataclass
class SignalMessage:
    """A message sent through a signal channel."""

    channel: str
    payload: dict[str, Any]
    sender_workflow_id: str | None = None
    timestamp: str | None = None


class SignalChannelRegistry:
    """
    Registry for signal channels used in cross-workflow communication.

    In Temporal, signals are used to send data to running workflows.
    This registry provides a standardized way to define and document
    the signal channels used across agents.

    Usage:
        # Define channels
        registry = SignalChannelRegistry()
        registry.register("remediation-complete", {
            "description": "Sent when a remediation workflow completes",
            "payload_schema": {
                "issue_id": "string",
                "status": "string",
                "fix_applied": "string",
            }
        })

        # Get channel info
        channel = registry.get("remediation-complete")
    """

    # Well-known signal channels for kubani agents
    CHANNELS = {
        # K8s-monitor signals
        "issue-detected": {
            "description": "New issue detected in cluster",
            "payload": {"issue_id": "str", "severity": "str", "resource": "str"},
        },
        "remediation-started": {
            "description": "Remediation workflow has started",
            "payload": {"issue_id": "str", "workflow_id": "str"},
        },
        "remediation-complete": {
            "description": "Remediation workflow completed (success or failure)",
            "payload": {"issue_id": "str", "status": "str", "details": "dict"},
        },
        "escalation-required": {
            "description": "Issue requires human intervention",
            "payload": {"issue_id": "str", "reason": "str", "attempts": "int"},
        },
        # Cross-agent coordination
        "agent-handoff": {
            "description": "Request another agent to handle a task",
            "payload": {"from_agent": "str", "to_agent": "str", "task": "dict"},
        },
        "agent-response": {
            "description": "Response from an agent after handling a task",
            "payload": {"from_agent": "str", "task_id": "str", "result": "dict"},
        },
        # Memory updates
        "memory-update": {
            "description": "Notify agents of a memory update",
            "payload": {"memory_type": "str", "key": "str", "action": "str"},
        },
    }

    def __init__(self) -> None:
        self._channels: dict[str, dict[str, Any]] = dict(self.CHANNELS)

    def register(self, name: str, schema: dict[str, Any]) -> None:
        """Register a new signal channel."""
        self._channels[name] = schema
        logger.debug(f"Registered signal channel: {name}")

    def get(self, name: str) -> dict[str, Any] | None:
        """Get channel schema by name."""
        return self._channels.get(name)

    def list_channels(self) -> list[str]:
        """List all registered channel names."""
        return list(self._channels.keys())

    def validate_payload(self, channel: str, payload: dict[str, Any]) -> bool:
        """
        Validate a payload against the channel schema.

        This is a simple existence check - for full validation,
        use Pydantic models.
        """
        schema = self._channels.get(channel)
        if not schema:
            return False

        expected_keys = set(schema.get("payload", {}).keys())
        actual_keys = set(payload.keys())

        return expected_keys.issubset(actual_keys)


# Singleton registry instance
_signal_registry: SignalChannelRegistry | None = None


def get_signal_registry() -> SignalChannelRegistry:
    """Get the global signal channel registry."""
    global _signal_registry
    if _signal_registry is None:
        _signal_registry = SignalChannelRegistry()
    return _signal_registry


# Workflow coordination helpers for Temporal
def create_saga_workflow_id(saga_name: str, context_id: str) -> str:
    """
    Create a deterministic workflow ID for a saga.

    Args:
        saga_name: Name of the saga
        context_id: Unique context (e.g., issue ID, request ID)

    Returns:
        Workflow ID string
    """
    return f"saga-{saga_name}-{context_id}"


def create_signal_workflow_id(channel: str, target_id: str) -> str:
    """
    Create a workflow ID for signal routing.

    Args:
        channel: Signal channel name
        target_id: Target workflow or agent ID

    Returns:
        Workflow ID for the signal handler
    """
    return f"signal-handler-{channel}-{target_id}"
