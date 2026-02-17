"""
Metrics collection utilities for MCP servers.

Provides standardized Prometheus metrics across all MCP servers.
"""

import logging
import time
from contextlib import contextmanager
from typing import Any

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Prometheus metrics collector for MCP servers.

    Provides standard metrics for all MCP servers:
    - Request counts (total, by tool, by status)
    - Request duration (by tool)
    - Active connections
    - Backend request counts and latencies

    Usage:
        metrics = MetricsCollector(server_name="discord-mcp")

        # Track a request
        with metrics.track_request("send_message"):
            await send_message()

        # Track backend call
        with metrics.track_backend("discord_api"):
            await api.call()

        # Get metrics for HTTP endpoint
        metrics_data = metrics.get_metrics()
    """

    def __init__(self, server_name: str, registry=None):
        """
        Initialize metrics collector.

        Args:
            server_name: Name of the MCP server (used as label)
            registry: Prometheus registry (defaults to default registry)
        """
        self.server_name = server_name
        self.registry = registry or CollectorRegistry()

        # Standard MCP server metrics
        self.request_total = Counter(
            "mcp_requests_total",
            "Total number of MCP requests",
            ["server", "tool", "status"],
            registry=self.registry,
        )

        self.request_duration_seconds = Histogram(
            "mcp_request_duration_seconds",
            "Duration of MCP requests in seconds",
            ["server", "tool"],
            registry=self.registry,
        )

        self.active_connections = Gauge(
            "mcp_active_connections",
            "Number of active MCP connections",
            ["server", "transport"],
            registry=self.registry,
        )

        # Backend metrics
        self.backend_requests_total = Counter(
            "mcp_backend_requests_total",
            "Total number of backend requests",
            ["server", "backend", "status"],
            registry=self.registry,
        )

        self.backend_latency_seconds = Histogram(
            "mcp_backend_latency_seconds",
            "Latency of backend requests in seconds",
            ["server", "backend"],
            registry=self.registry,
        )

    def increment_request(self, tool: str, status: str = "success") -> None:
        """
        Increment request counter.

        Args:
            tool: Name of the tool that was called
            status: Status of the request (success, error, timeout)
        """
        self.request_total.labels(
            server=self.server_name,
            tool=tool,
            status=status,
        ).inc()

    def observe_request_duration(self, tool: str, duration_seconds: float) -> None:
        """
        Record request duration.

        Args:
            tool: Name of the tool that was called
            duration_seconds: Duration in seconds
        """
        self.request_duration_seconds.labels(
            server=self.server_name,
            tool=tool,
        ).observe(duration_seconds)

    @contextmanager
    def track_request(self, tool: str):
        """
        Context manager to track a request.

        Automatically records duration and increments counters.

        Usage:
            with metrics.track_request("send_message"):
                await send_message()

        Args:
            tool: Name of the tool being called
        """
        start = time.monotonic()
        status = "success"

        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.monotonic() - start
            self.observe_request_duration(tool, duration)
            self.increment_request(tool, status)

    def set_active_connections(self, transport: str, count: int) -> None:
        """
        Set the number of active connections.

        Args:
            transport: Transport type (sse, stdio, http)
            count: Number of active connections
        """
        self.active_connections.labels(
            server=self.server_name,
            transport=transport,
        ).set(count)

    def increment_backend_request(self, backend: str, status: str = "success") -> None:
        """
        Increment backend request counter.

        Args:
            backend: Name of the backend service
            status: Status of the request (success, error, timeout)
        """
        self.backend_requests_total.labels(
            server=self.server_name,
            backend=backend,
            status=status,
        ).inc()

    def observe_backend_latency(self, backend: str, latency_seconds: float) -> None:
        """
        Record backend request latency.

        Args:
            backend: Name of the backend service
            latency_seconds: Latency in seconds
        """
        self.backend_latency_seconds.labels(
            server=self.server_name,
            backend=backend,
        ).observe(latency_seconds)

    @contextmanager
    def track_backend(self, backend: str):
        """
        Context manager to track a backend request.

        Automatically records latency and increments counters.

        Usage:
            with metrics.track_backend("discord_api"):
                await api.call()

        Args:
            backend: Name of the backend service
        """
        start = time.monotonic()
        status = "success"

        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            latency = time.monotonic() - start
            self.observe_backend_latency(backend, latency)
            self.increment_backend_request(backend, status)

    def get_metrics(self) -> bytes:
        """
        Get metrics in Prometheus format.

        Returns:
            Metrics data as bytes (suitable for HTTP response)
        """
        return generate_latest(self.registry)

    def get_metrics_handler(self):
        """
        Get a handler function for serving metrics via HTTP.

        Returns:
            Async handler function that returns metrics data
        """

        async def handler() -> dict[str, Any]:
            """Metrics endpoint handler."""
            return {
                "content_type": "text/plain; version=0.0.4",
                "body": self.get_metrics(),
            }

        return handler
