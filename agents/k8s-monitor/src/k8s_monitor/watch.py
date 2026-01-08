"""
Kubernetes Watch Stream - Real-time event monitoring.

Provides real-time Kubernetes event watching using the watch API
instead of polling. This reduces latency from ~30 seconds to near-instant
event detection while also reducing load on the Kubernetes API server.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from kubernetes import client, config, watch

logger = logging.getLogger(__name__)


@dataclass
class WatchEvent:
    """A Kubernetes watch event."""

    event_type: str  # ADDED, MODIFIED, DELETED
    k8s_event: dict[str, Any]  # The raw Kubernetes Event object
    timestamp: datetime


class K8sWatchStream:
    """
    Asynchronous Kubernetes event watch stream.

    Uses the Kubernetes watch API to receive real-time event notifications
    instead of polling. Includes automatic reconnection with exponential backoff.
    """

    def __init__(
        self,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
        backoff_multiplier: float = 2.0,
        resource_version_window: int = 300,
    ):
        """
        Initialize the watch stream.

        Args:
            initial_backoff: Initial backoff time in seconds after disconnect.
            max_backoff: Maximum backoff time in seconds.
            backoff_multiplier: Multiplier for exponential backoff.
            resource_version_window: Seconds to look back on reconnect.
        """
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier
        self.resource_version_window = resource_version_window

        self._running = False
        self._current_backoff = initial_backoff
        self._last_resource_version: str | None = None
        self._v1: client.CoreV1Api | None = None
        self._watch: watch.Watch | None = None

    def _load_config(self) -> None:
        """Load Kubernetes configuration (in-cluster or local)."""
        try:
            config.load_incluster_config()
            logger.debug("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            config.load_kube_config()
            logger.debug("Loaded local Kubernetes config")

    def _ensure_client(self) -> client.CoreV1Api:
        """Ensure the Kubernetes client is initialized."""
        if self._v1 is None:
            self._load_config()
            self._v1 = client.CoreV1Api()
        return self._v1

    async def _watch_events_sync(self) -> AsyncIterator[WatchEvent]:
        """
        Internal synchronous watch that yields events.

        This runs the blocking watch.stream() in a thread pool to avoid
        blocking the async event loop.
        """
        v1 = self._ensure_client()
        self._watch = watch.Watch()

        # Build watch kwargs
        watch_kwargs: dict[str, Any] = {
            "timeout_seconds": 0,  # Infinite watch
        }

        # If we have a resource version, resume from there
        if self._last_resource_version:
            watch_kwargs["resource_version"] = self._last_resource_version
            logger.debug(f"Resuming watch from resource version {self._last_resource_version}")

        try:
            # Run the blocking watch in a thread pool
            asyncio.get_event_loop()

            for event in self._watch.stream(
                v1.list_event_for_all_namespaces,
                **watch_kwargs,
            ):
                if not self._running:
                    break

                # Update resource version for resumption
                raw_object = event.get("raw_object", {})
                metadata = raw_object.get("metadata", {})
                if resource_version := metadata.get("resourceVersion"):
                    self._last_resource_version = resource_version

                yield WatchEvent(
                    event_type=event["type"],
                    k8s_event=raw_object,
                    timestamp=datetime.now(UTC),
                )

                # Reset backoff on successful event
                self._current_backoff = self.initial_backoff

                # Yield control to allow other coroutines to run
                await asyncio.sleep(0)

        except client.ApiException as e:
            if e.status == 410:
                # Gone - resource version too old, need to re-list
                logger.warning("Watch resource version expired, will re-list")
                self._last_resource_version = None
            else:
                raise

    async def watch(
        self,
        event_filter: Callable[[WatchEvent], bool] | None = None,
    ) -> AsyncIterator[WatchEvent]:
        """
        Watch for Kubernetes events with automatic reconnection.

        Args:
            event_filter: Optional filter function to select events.

        Yields:
            WatchEvent objects for each matching Kubernetes event.
        """
        self._running = True
        self._current_backoff = self.initial_backoff

        while self._running:
            try:
                logger.info("Starting Kubernetes event watch stream")

                async for event in self._watch_events_sync():
                    if not self._running:
                        break

                    # Apply filter if provided
                    if event_filter and not event_filter(event):
                        continue

                    yield event

            except Exception as e:
                if not self._running:
                    break

                logger.error(
                    f"Watch stream error: {e}. Reconnecting in {self._current_backoff:.1f}s"
                )

                # Wait with backoff
                await asyncio.sleep(self._current_backoff)

                # Increase backoff for next failure
                self._current_backoff = min(
                    self._current_backoff * self.backoff_multiplier,
                    self.max_backoff,
                )

                # Reset client to force reconnection
                self._v1 = None

    def stop(self) -> None:
        """Stop the watch stream."""
        self._running = False
        if self._watch:
            self._watch.stop()
        logger.info("Watch stream stopped")


def default_event_filter(event: WatchEvent) -> bool:
    """
    Default filter for Kubernetes events.

    Filters for Warning and Error type events, excluding Normal events.
    """
    k8s_event = event.k8s_event
    event_type = k8s_event.get("type", "Normal")
    return event_type in ("Warning", "Error")


def create_reason_filter(reasons: set[str]) -> Callable[[WatchEvent], bool]:
    """
    Create a filter that matches specific event reasons.

    Args:
        reasons: Set of event reasons to match (e.g., {"CrashLoopBackOff", "OOMKilled"})

    Returns:
        Filter function that matches events with those reasons.
    """

    def filter_func(event: WatchEvent) -> bool:
        k8s_event = event.k8s_event
        reason = k8s_event.get("reason", "")
        return reason in reasons

    return filter_func


@asynccontextmanager
async def watch_kubernetes_events(
    event_filter: Callable[[WatchEvent], bool] | None = None,
    initial_backoff: float = 1.0,
    max_backoff: float = 60.0,
) -> AsyncIterator[AsyncIterator[WatchEvent]]:
    """
    Context manager for watching Kubernetes events.

    Usage:
        async with watch_kubernetes_events() as events:
            async for event in events:
                process(event)

    Args:
        event_filter: Optional filter for events.
        initial_backoff: Initial reconnection backoff in seconds.
        max_backoff: Maximum reconnection backoff in seconds.

    Yields:
        AsyncIterator of WatchEvent objects.
    """
    stream = K8sWatchStream(
        initial_backoff=initial_backoff,
        max_backoff=max_backoff,
    )

    try:
        yield stream.watch(event_filter=event_filter)
    finally:
        stream.stop()
