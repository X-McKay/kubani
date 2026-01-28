"""Event Bus to Temporal Bridge.

This module provides utilities for bridging the Redis Streams-based event bus
to Temporal workflows. It enables:

1. Event-driven workflow triggers (event → start workflow)
2. Workflow result publishing (workflow complete → event)
3. Bidirectional integration for gradual migration

Architecture:
    The bridge runs as a separate process (or alongside workers) and:
    - Subscribes to event bus topics
    - Routes events to appropriate Temporal workflows
    - Publishes workflow results back to the event bus

Usage:
    from kubani.framework.temporal.bridge import (
        EventBridge,
        WorkflowTrigger,
        start_event_bridge,
    )

    # Define workflow triggers
    triggers = [
        WorkflowTrigger(
            event_type=EventType.K8S_ISSUE_DETECTED,
            workflow_type=K8sRemediationWorkflow,
            task_queue="k8s-monitor",
            input_mapper=lambda e: RemediationInput(
                event_id=e.id,
                resource_kind=e.payload.get("kind"),
                ...
            ),
        ),
    ]

    # Start the bridge
    await start_event_bridge(triggers)
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from temporalio.client import Client, WorkflowHandle

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Types
# =============================================================================


@dataclass
class WorkflowTrigger:
    """Configuration for triggering a workflow from an event.

    Attributes:
        event_type: Event type that triggers this workflow
        workflow_type: The Temporal workflow class to start
        task_queue: Task queue for the workflow
        input_mapper: Function to convert Event to workflow input
        condition: Optional function to filter events (return True to trigger)
        workflow_id_template: Template for workflow ID (uses event fields)
        execution_timeout: Overall workflow timeout
        publish_result: Whether to publish result back to event bus
        result_event_type: Event type for result (if publish_result=True)
    """

    event_type: str  # EventType value
    workflow_type: type
    task_queue: str
    input_mapper: Callable[[Any], Any]  # Event -> workflow input
    condition: Callable[[Any], bool] | None = None
    workflow_id_template: str = "{event_type}-{event_id}"
    execution_timeout: timedelta = field(default_factory=lambda: timedelta(hours=1))
    publish_result: bool = True
    result_event_type: str | None = None


@dataclass
class BridgeConfig:
    """Configuration for the event bridge.

    Attributes:
        consumer_group: Consumer group name for event bus
        consumer_name: Individual consumer name
        batch_size: Number of events to process in parallel
        poll_interval_ms: Event bus polling interval
        max_retries: Max retries for workflow start failures
        retry_delay_seconds: Delay between retries
    """

    consumer_group: str = "temporal-bridge"
    consumer_name: str = "bridge-0"
    batch_size: int = 10
    poll_interval_ms: int = 1000
    max_retries: int = 3
    retry_delay_seconds: float = 5.0


# =============================================================================
# Event Bridge
# =============================================================================


class EventBridge:
    """Bridges events from the event bus to Temporal workflows.

    The bridge subscribes to configured event types and starts
    corresponding Temporal workflows when events are received.
    """

    def __init__(
        self,
        client: Client,
        triggers: list[WorkflowTrigger],
        config: BridgeConfig | None = None,
    ):
        """Initialize the event bridge.

        Args:
            client: Temporal client
            triggers: List of workflow triggers
            config: Bridge configuration
        """
        self._client = client
        self._triggers = triggers
        self._config = config or BridgeConfig()
        self._running = False
        self._event_bus = None

        # Index triggers by event type for fast lookup
        self._trigger_map: dict[str, list[WorkflowTrigger]] = {}
        for trigger in triggers:
            if trigger.event_type not in self._trigger_map:
                self._trigger_map[trigger.event_type] = []
            self._trigger_map[trigger.event_type].append(trigger)

        logger.info(
            f"EventBridge initialized with {len(triggers)} triggers "
            f"for {len(self._trigger_map)} event types"
        )

    async def start(self) -> None:
        """Start the event bridge.

        Subscribes to all configured event types and processes events.
        """
        from kubani.framework.events import EventType, get_event_bus

        self._event_bus = await get_event_bus()
        self._running = True

        logger.info(f"Starting event bridge with config: {self._config}")

        # Subscribe to all configured event types
        event_types = [EventType(t) for t in self._trigger_map.keys()]

        tasks = []
        for event_type in event_types:
            task = asyncio.create_task(
                self._process_events(event_type),
                name=f"bridge-{event_type.value}",
            )
            tasks.append(task)

        logger.info(f"Subscribed to {len(event_types)} event types")

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Event bridge cancelled")
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the event bridge."""
        self._running = False
        logger.info("Event bridge stopped")

    async def _process_events(self, event_type: Any) -> None:
        """Process events of a specific type."""

        logger.info(f"Starting event processor for {event_type.value}")

        async for event in self._event_bus.subscribe(
            event_type,
            consumer_group=self._config.consumer_group,
            consumer_name=f"{self._config.consumer_name}-{event_type.value}",
        ):
            if not self._running:
                break

            try:
                await self._handle_event(event)
            except Exception as e:
                logger.error(f"Error handling event {event.id}: {e}")

    async def _handle_event(self, event: Any) -> None:
        """Handle a single event by starting appropriate workflows."""
        triggers = self._trigger_map.get(event.type.value, [])

        for trigger in triggers:
            # Check condition if specified
            if trigger.condition and not trigger.condition(event):
                logger.debug(f"Event {event.id} skipped by condition for {trigger.workflow_type}")
                continue

            try:
                await self._start_workflow(event, trigger)
            except Exception as e:
                logger.error(
                    f"Failed to start workflow {trigger.workflow_type.__name__} "
                    f"for event {event.id}: {e}"
                )

    async def _start_workflow(self, event: Any, trigger: WorkflowTrigger) -> WorkflowHandle:
        """Start a workflow for an event."""
        # Map event to workflow input
        workflow_input = trigger.input_mapper(event)

        # Generate workflow ID
        workflow_id = trigger.workflow_id_template.format(
            event_type=event.type.value.replace(":", "-"),
            event_id=event.id,
            timestamp=datetime.utcnow().strftime("%Y%m%d-%H%M%S"),
        )

        logger.info(
            f"Starting workflow {trigger.workflow_type.__name__} "
            f"(id={workflow_id}) for event {event.id}"
        )

        # Start the workflow with retries
        for attempt in range(self._config.max_retries):
            try:
                handle = await self._client.start_workflow(
                    trigger.workflow_type.run,
                    workflow_input,
                    id=workflow_id,
                    task_queue=trigger.task_queue,
                    execution_timeout=trigger.execution_timeout,
                )

                logger.info(f"Started workflow {workflow_id}")

                # Optionally publish result when complete
                if trigger.publish_result:
                    asyncio.create_task(
                        self._publish_result(handle, event, trigger),
                        name=f"result-{workflow_id}",
                    )

                return handle

            except Exception as e:
                if attempt < self._config.max_retries - 1:
                    logger.warning(
                        f"Retry {attempt + 1}/{self._config.max_retries} "
                        f"for workflow {workflow_id}: {e}"
                    )
                    await asyncio.sleep(self._config.retry_delay_seconds)
                else:
                    raise

    async def _publish_result(
        self,
        handle: WorkflowHandle,
        event: Any,
        trigger: WorkflowTrigger,
    ) -> None:
        """Wait for workflow completion and publish result to event bus."""
        try:
            result = await handle.result()

            # Determine result event type
            result_type = trigger.result_event_type
            if not result_type:
                # Default: append _COMPLETED to the trigger event type
                result_type = event.type.value.replace("_DETECTED", "_COMPLETED")
                result_type = result_type.replace("_REQUESTED", "_COMPLETED")

            await self._event_bus.publish(
                result_type,
                {
                    "trigger_event_id": event.id,
                    "workflow_id": handle.id,
                    "result": result,
                },
                source="temporal-bridge",
                correlation_id=event.correlation_id,
            )

            logger.info(f"Published result for workflow {handle.id}")

        except Exception as e:
            logger.error(f"Error publishing result for workflow {handle.id}: {e}")


# =============================================================================
# Workflow Result Publisher
# =============================================================================


class WorkflowResultPublisher:
    """Publishes workflow results back to the event bus.

    This can be used as an activity or called from workflow completion handlers.
    """

    def __init__(self, event_bus: Any):
        """Initialize the publisher.

        Args:
            event_bus: Event bus instance
        """
        self._event_bus = event_bus

    async def publish_success(
        self,
        workflow_id: str,
        event_type: str,
        result: dict[str, Any],
        correlation_id: str | None = None,
    ) -> None:
        """Publish a successful workflow result."""
        await self._event_bus.publish(
            event_type,
            {
                "workflow_id": workflow_id,
                "success": True,
                "result": result,
            },
            source="temporal-workflow",
            correlation_id=correlation_id,
        )

    async def publish_failure(
        self,
        workflow_id: str,
        event_type: str,
        error: str,
        correlation_id: str | None = None,
    ) -> None:
        """Publish a failed workflow result."""
        await self._event_bus.publish(
            event_type,
            {
                "workflow_id": workflow_id,
                "success": False,
                "error": error,
            },
            source="temporal-workflow",
            correlation_id=correlation_id,
        )


# =============================================================================
# Convenience Functions
# =============================================================================


async def start_event_bridge(
    triggers: list[WorkflowTrigger],
    temporal_host: str | None = None,
    temporal_namespace: str | None = None,
    config: BridgeConfig | None = None,
) -> EventBridge:
    """Start an event bridge with the given triggers.

    Args:
        triggers: List of workflow triggers
        temporal_host: Temporal host (defaults to TEMPORAL_HOST env var)
        temporal_namespace: Temporal namespace (defaults to TEMPORAL_NAMESPACE env var)
        config: Bridge configuration

    Returns:
        Running EventBridge instance
    """
    import os

    host = temporal_host or os.environ.get("TEMPORAL_HOST", "localhost:7233")
    namespace = temporal_namespace or os.environ.get("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {host}")
    client = await Client.connect(host, namespace=namespace)

    bridge = EventBridge(client, triggers, config)
    await bridge.start()

    return bridge


def create_k8s_triggers() -> list[WorkflowTrigger]:
    """Create standard triggers for K8s monitoring workflows.

    Returns triggers for:
    - K8S_ISSUE_DETECTED → K8sRemediationWorkflow or K8sInvestigationSwarm
    - K8S_INVESTIGATION_REQUESTED → K8sInvestigationSwarm
    """
    from kubani.framework.events import EventType

    triggers = []

    # Lazy import to avoid circular imports
    def _get_k8s_workflows():
        from kubani.syndicates.k8s_monitor.workflows import (
            K8sInvestigationSwarm,
            K8sRemediationWorkflow,
        )

        return K8sRemediationWorkflow, K8sInvestigationSwarm

    # Helper to determine complexity
    def _is_simple_issue(event: Any) -> bool:
        payload = event.payload.get("event", {})
        reason = payload.get("reason", "")
        severity = payload.get("severity", "warning")

        # Simple issues
        simple_reasons = [
            "CrashLoopBackOff",
            "OOMKilled",
            "ImagePullBackOff",
            "FailedScheduling",
            "Unhealthy",
        ]

        return reason in simple_reasons and severity != "critical"

    def _is_complex_issue(event: Any) -> bool:
        return not _is_simple_issue(event)

    # Simple issues → Remediation workflow
    triggers.append(
        WorkflowTrigger(
            event_type=EventType.K8S_ISSUE_DETECTED.value,
            workflow_type=_get_k8s_workflows()[0],  # K8sRemediationWorkflow
            task_queue="k8s-monitor",
            input_mapper=lambda e: {
                "event_id": e.id,
                "resource_kind": e.payload.get("event", {}).get("kind", "Pod"),
                "resource_name": e.payload.get("event", {}).get("name", "unknown"),
                "namespace": e.payload.get("event", {}).get("namespace", "default"),
                "reason": e.payload.get("event", {}).get("reason", "Unknown"),
                "message": e.payload.get("event", {}).get("message", ""),
                "severity": e.payload.get("event", {}).get("severity", "warning"),
                "correlation_id": e.correlation_id,
            },
            condition=_is_simple_issue,
            workflow_id_template="remediation-{event_id}",
            result_event_type=EventType.K8S_REMEDIATION_COMPLETED.value,
        )
    )

    # Complex issues → Investigation swarm
    triggers.append(
        WorkflowTrigger(
            event_type=EventType.K8S_ISSUE_DETECTED.value,
            workflow_type=_get_k8s_workflows()[1],  # K8sInvestigationSwarm
            task_queue="k8s-monitor",
            input_mapper=lambda e: {
                "trigger_event_id": e.id,
                "resource_kind": e.payload.get("event", {}).get("kind", "Pod"),
                "resource_name": e.payload.get("event", {}).get("name", "unknown"),
                "namespace": e.payload.get("event", {}).get("namespace", "default"),
                "symptoms": [e.payload.get("event", {}).get("reason", "Unknown")],
                "priority": 2 if e.payload.get("event", {}).get("severity") == "critical" else 3,
                "correlation_id": e.correlation_id,
            },
            condition=_is_complex_issue,
            workflow_id_template="investigation-{event_id}",
        )
    )

    # Explicit investigation requests
    triggers.append(
        WorkflowTrigger(
            event_type=EventType.K8S_INVESTIGATION_REQUESTED.value,
            workflow_type=_get_k8s_workflows()[1],  # K8sInvestigationSwarm
            task_queue="k8s-monitor",
            input_mapper=lambda e: {
                "trigger_event_id": e.id,
                "resource_kind": e.payload.get("resource_kind", "Pod"),
                "resource_name": e.payload.get("resource_name", "unknown"),
                "namespace": e.payload.get("namespace", "default"),
                "symptoms": e.payload.get("symptoms", []),
                "priority": e.payload.get("priority", 3),
                "correlation_id": e.correlation_id,
            },
            workflow_id_template="investigation-{event_id}",
        )
    )

    return triggers


def create_news_triggers() -> list[WorkflowTrigger]:
    """Create standard triggers for news digest workflows.

    Returns triggers for:
    - NEWS_COLLECTION_REQUESTED → NewsCollectionWorkflow
    """
    from kubani.framework.events import EventType

    triggers = []

    # Lazy import
    def _get_news_workflows():
        from kubani.syndicates.news_digest.workflows import (
            NewsCollectionWorkflow,
            NewsDigestWorkflow,
        )

        return NewsCollectionWorkflow, NewsDigestWorkflow

    # Manual collection trigger
    triggers.append(
        WorkflowTrigger(
            event_type=EventType.NEWS_COLLECTION_REQUESTED.value,
            workflow_type=_get_news_workflows()[0],  # NewsCollectionWorkflow
            task_queue="news-digest",
            input_mapper=lambda e: {
                "sources": e.payload.get("sources", ["rss", "arxiv", "github"]),
                "max_articles_per_source": e.payload.get("max_articles", 20),
                "notify_breaking": e.payload.get("notify_breaking", True),
                "correlation_id": e.correlation_id,
            },
            workflow_id_template="collection-{timestamp}",
        )
    )

    return triggers
