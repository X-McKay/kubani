"""Tests for health check utilities."""

import pytest

from kubani.framework.mcp.server.health import HealthCheck, HealthStatus


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_statuses_exist(self):
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"


class TestHealthCheck:
    """Tests for HealthCheck."""

    @pytest.mark.asyncio
    async def test_healthy_check(self):
        async def check():
            return True

        hc = HealthCheck(name="backend", check_fn=check)
        result = await hc.run()

        assert result.status == HealthStatus.HEALTHY
        assert result.name == "backend"
        assert result.latency_ms >= 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_unhealthy_check(self):
        async def check():
            raise ConnectionError("Cannot connect")

        hc = HealthCheck(name="backend", check_fn=check)
        result = await hc.run()

        assert result.status == HealthStatus.UNHEALTHY
        assert "Cannot connect" in result.error

    @pytest.mark.asyncio
    async def test_check_returning_false(self):
        async def check():
            return False

        hc = HealthCheck(name="backend", check_fn=check)
        result = await hc.run()

        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_timeout(self):
        import asyncio

        async def slow_check():
            await asyncio.sleep(10)
            return True

        hc = HealthCheck(name="slow", check_fn=slow_check, timeout=0.1)
        result = await hc.run()

        assert result.status == HealthStatus.UNHEALTHY
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_result_to_dict(self):
        async def check():
            return True

        hc = HealthCheck(name="backend", check_fn=check)
        result = await hc.run()
        d = result.to_dict()

        assert d["status"] == "healthy"
        assert d["name"] == "backend"
        assert "latency_ms" in d
