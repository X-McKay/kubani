"""Tests for health check utilities."""

import pytest

from kubani.framework.mcp.server.health import (
    HealthCheck,
    HealthCheckManager,
    HealthStatus,
)


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


class TestHealthCheckManager:
    """Tests for HealthCheckManager."""

    @pytest.mark.asyncio
    async def test_no_backends_is_healthy(self):
        manager = HealthCheckManager(version="1.0.0")
        response = await manager.check_all()

        assert response.status == HealthStatus.HEALTHY
        assert response.version == "1.0.0"
        assert len(response.backends) == 0

    @pytest.mark.asyncio
    async def test_all_healthy_backends(self):
        manager = HealthCheckManager(version="1.0.0")

        async def check_db():
            return True

        async def check_cache():
            return True

        manager.register("database", check_db)
        manager.register("cache", check_cache)

        response = await manager.check_all()

        assert response.status == HealthStatus.HEALTHY
        assert len(response.backends) == 2
        assert response.backends["database"].status == HealthStatus.HEALTHY
        assert response.backends["cache"].status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_one_unhealthy_backend(self):
        manager = HealthCheckManager(version="1.0.0")

        async def check_db():
            return True

        async def check_cache():
            raise ConnectionError("Cache down")

        manager.register("database", check_db)
        manager.register("cache", check_cache)

        response = await manager.check_all()

        assert response.status == HealthStatus.UNHEALTHY
        assert response.backends["database"].status == HealthStatus.HEALTHY
        assert response.backends["cache"].status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_response_to_dict(self):
        manager = HealthCheckManager(version="1.0.0")

        async def check_db():
            return True

        manager.register("database", check_db)

        response = await manager.check_all()
        d = response.to_dict()

        assert d["status"] == "healthy"
        assert d["version"] == "1.0.0"
        assert "backends" in d
        assert "database" in d["backends"]
        assert "uptime_seconds" in d

