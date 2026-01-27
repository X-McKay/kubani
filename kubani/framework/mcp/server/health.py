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
