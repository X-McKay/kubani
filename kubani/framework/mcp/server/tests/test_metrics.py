"""Tests for metrics collection utilities."""

import pytest
from prometheus_client import CollectorRegistry

from kubani.framework.mcp.server.metrics import MetricsCollector


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def test_initialization(self):
        """Test metrics collector initialization."""
        registry = CollectorRegistry()
        metrics = MetricsCollector(server_name="test-server", registry=registry)

        assert metrics.server_name == "test-server"
        assert metrics.registry == registry

    def test_increment_request(self):
        """Test incrementing request counter."""
        registry = CollectorRegistry()
        metrics = MetricsCollector(server_name="test-server", registry=registry)

        metrics.increment_request("test_tool", "success")
        metrics.increment_request("test_tool", "success")
        metrics.increment_request("test_tool", "error")

        # Verify metrics were recorded by getting the metrics output
        metrics_data = metrics.get_metrics()
        assert b"mcp_requests_total" in metrics_data
        assert b'tool="test_tool"' in metrics_data
        assert b'status="success"' in metrics_data
        assert b'status="error"' in metrics_data

    def test_observe_request_duration(self):
        """Test observing request duration."""
        registry = CollectorRegistry()
        metrics = MetricsCollector(server_name="test-server", registry=registry)

        metrics.observe_request_duration("test_tool", 0.5)
        metrics.observe_request_duration("test_tool", 1.0)

        # Verify metrics were recorded
        metric_families = list(registry.collect())
        duration_metric = next(
            m for m in metric_families if m.name == "mcp_request_duration_seconds"
        )

        # Check that observations were recorded
        count_sample = next(
            s
            for s in duration_metric.samples
            if s.name == "mcp_request_duration_seconds_count"
            and s.labels["tool"] == "test_tool"
        )
        assert count_sample.value == 2

    @pytest.mark.asyncio
    async def test_track_request_context_manager(self):
        """Test track_request context manager."""
        registry = CollectorRegistry()
        metrics = MetricsCollector(server_name="test-server", registry=registry)

        with metrics.track_request("test_tool"):
            pass  # Simulate work

        # Verify metrics were recorded
        metrics_data = metrics.get_metrics()
        assert b"mcp_requests_total" in metrics_data
        assert b'tool="test_tool"' in metrics_data
        assert b'status="success"' in metrics_data

    @pytest.mark.asyncio
    async def test_track_request_with_error(self):
        """Test track_request context manager with error."""
        registry = CollectorRegistry()
        metrics = MetricsCollector(server_name="test-server", registry=registry)

        with pytest.raises(ValueError):
            with metrics.track_request("test_tool"):
                raise ValueError("Test error")

        # Verify error was recorded
        metrics_data = metrics.get_metrics()
        assert b"mcp_requests_total" in metrics_data
        assert b'tool="test_tool"' in metrics_data
        assert b'status="error"' in metrics_data

    def test_set_active_connections(self):
        """Test setting active connections."""
        registry = CollectorRegistry()
        metrics = MetricsCollector(server_name="test-server", registry=registry)

        metrics.set_active_connections("sse", 5)

        # Verify metric was set
        metric_families = list(registry.collect())
        connections_metric = next(
            m for m in metric_families if m.name == "mcp_active_connections"
        )

        sample = next(
            s
            for s in connections_metric.samples
            if s.labels["transport"] == "sse"
        )
        assert sample.value == 5

    def test_increment_backend_request(self):
        """Test incrementing backend request counter."""
        registry = CollectorRegistry()
        metrics = MetricsCollector(server_name="test-server", registry=registry)

        metrics.increment_backend_request("discord_api", "success")
        metrics.increment_backend_request("discord_api", "success")

        # Verify metrics were recorded
        metrics_data = metrics.get_metrics()
        assert b"mcp_backend_requests_total" in metrics_data
        assert b'backend="discord_api"' in metrics_data
        assert b'status="success"' in metrics_data

    def test_observe_backend_latency(self):
        """Test observing backend latency."""
        registry = CollectorRegistry()
        metrics = MetricsCollector(server_name="test-server", registry=registry)

        metrics.observe_backend_latency("discord_api", 0.1)

        # Verify metrics were recorded
        metric_families = list(registry.collect())
        latency_metric = next(
            m for m in metric_families if m.name == "mcp_backend_latency_seconds"
        )

        count_sample = next(
            s
            for s in latency_metric.samples
            if s.name == "mcp_backend_latency_seconds_count"
            and s.labels["backend"] == "discord_api"
        )
        assert count_sample.value == 1

    @pytest.mark.asyncio
    async def test_track_backend_context_manager(self):
        """Test track_backend context manager."""
        registry = CollectorRegistry()
        metrics = MetricsCollector(server_name="test-server", registry=registry)

        with metrics.track_backend("discord_api"):
            pass  # Simulate backend call

        # Verify metrics were recorded
        metrics_data = metrics.get_metrics()
        assert b"mcp_backend_requests_total" in metrics_data
        assert b'backend="discord_api"' in metrics_data
        assert b'status="success"' in metrics_data

    def test_get_metrics(self):
        """Test getting metrics in Prometheus format."""
        registry = CollectorRegistry()
        metrics = MetricsCollector(server_name="test-server", registry=registry)

        metrics.increment_request("test_tool", "success")

        metrics_data = metrics.get_metrics()

        assert isinstance(metrics_data, bytes)
        assert b"mcp_requests_total" in metrics_data
