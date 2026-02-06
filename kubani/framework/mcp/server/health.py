"""
Health check utilities for MCP servers.

Provides standardized health checking across all MCP servers.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthResult:
    """Result of a health check."""

    name: str
    status: HealthStatus
    latency_ms: float
    error: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        result = {
            "name": self.name,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
        }
        if self.error:
            result["error"] = self.error
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class BackendHealth:
    """Health status of a backend service."""

    name: str
    status: HealthStatus
    latency_ms: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        result = {
            "name": self.name,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
        }
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class HealthCheckResponse:
    """Complete health check response from MCP server."""

    status: HealthStatus
    backends: dict[str, BackendHealth]
    uptime_seconds: float
    version: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "status": self.status.value,
            "backends": {name: backend.to_dict() for name, backend in self.backends.items()},
            "uptime_seconds": self.uptime_seconds,
            "version": self.version,
        }


class HealthCheck:
    """
    Configurable health check for a backend service.

    Usage:
        async def check_db():
            await db.ping()
            return True

        hc = HealthCheck(name="database", check_fn=check_db, timeout=5.0)
        result = await hc.run()
        print(result.status)  # HealthStatus.HEALTHY
    """

    def __init__(
        self,
        name: str,
        check_fn: Callable[[], Awaitable[bool]],
        timeout: float = 10.0,
    ):
        """
        Initialize health check.

        Args:
            name: Name of the service being checked
            check_fn: Async function that returns True if healthy, False otherwise
            timeout: Maximum time to wait for check (seconds)
        """
        self.name = name
        self.check_fn = check_fn
        self.timeout = timeout

    async def run(self) -> HealthResult:
        """
        Run the health check.

        Returns:
            HealthResult with status, latency, and any errors
        """
        start = time.monotonic()

        try:
            result = await asyncio.wait_for(
                self.check_fn(),
                timeout=self.timeout,
            )
            latency_ms = (time.monotonic() - start) * 1000

            if result:
                return HealthResult(
                    name=self.name,
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency_ms,
                )
            else:
                return HealthResult(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=latency_ms,
                    error="Check returned False",
                )

        except TimeoutError:
            latency_ms = (time.monotonic() - start) * 1000
            return HealthResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                error=f"Health check timed out after {self.timeout}s",
            )

        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning(f"Health check {self.name} failed: {e}")
            return HealthResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                error=str(e),
            )


class HealthCheckManager:
    """
    Manager for multiple backend health checks.

    Supports registering multiple backend health checks and running them
    all to produce a comprehensive health status.

    Usage:
        manager = HealthCheckManager(version="1.0.0")

        async def check_db():
            await db.ping()
            return True

        manager.register("database", check_db)
        manager.register("cache", check_redis)

        response = await manager.check_all()
        print(response.status)  # Overall health status
    """

    def __init__(self, version: str = "unknown"):
        """
        Initialize health check manager.

        Args:
            version: Version string for the server
        """
        self.version = version
        self._checks: dict[str, HealthCheck] = {}
        self._start_time = time.monotonic()

    def register(
        self,
        name: str,
        check_fn: Callable[[], Awaitable[bool]],
        timeout: float = 10.0,
    ) -> None:
        """
        Register a backend health check.

        Args:
            name: Name of the backend service
            check_fn: Async function that returns True if healthy
            timeout: Maximum time to wait for check (seconds)
        """
        self._checks[name] = HealthCheck(name=name, check_fn=check_fn, timeout=timeout)

    async def check_all(self) -> HealthCheckResponse:
        """
        Run all registered health checks.

        Returns:
            HealthCheckResponse with overall status and individual backend results
        """
        backends: dict[str, BackendHealth] = {}

        # Run all checks concurrently
        results = await asyncio.gather(
            *[check.run() for check in self._checks.values()],
            return_exceptions=True,
        )

        # Process results
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Health check raised exception: {result}")
                continue

            backends[result.name] = BackendHealth(
                name=result.name,
                status=result.status,
                latency_ms=result.latency_ms,
                error=result.error,
            )

        # Determine overall status
        if not backends:
            overall_status = HealthStatus.HEALTHY
        elif all(b.status == HealthStatus.HEALTHY for b in backends.values()):
            overall_status = HealthStatus.HEALTHY
        elif any(b.status == HealthStatus.UNHEALTHY for b in backends.values()):
            overall_status = HealthStatus.UNHEALTHY
        else:
            overall_status = HealthStatus.DEGRADED

        uptime = time.monotonic() - self._start_time

        return HealthCheckResponse(
            status=overall_status,
            backends=backends,
            uptime_seconds=uptime,
            version=self.version,
        )
