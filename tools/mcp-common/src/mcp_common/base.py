"""
Base MCP Server class providing common patterns for all Kubani MCP servers.

This module provides:
- BaseMCPServer: Abstract base class with health checks, metrics, and logging
- Common tool decorators for consistent error handling
- Standard response models

Usage:
    from mcp_common import BaseMCPServer, tool_handler

    class MyMCPServer(BaseMCPServer):
        def __init__(self):
            super().__init__(
                name="my-mcp-server",
                version="1.0.0",
                description="My custom MCP server",
            )

        def register_tools(self) -> None:
            @self.server.tool()
            @tool_handler
            async def my_tool(param: str) -> str:
                return f"Result: {param}"
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from typing import Any, Callable, TypeVar

from mcp.server import Server
from mcp.server.stdio import stdio_server

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class ServerMetrics:
    """Metrics collected by the MCP server."""

    start_time: datetime = field(default_factory=datetime.utcnow)
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0

    @property
    def uptime_seconds(self) -> float:
        """Get server uptime in seconds."""
        return (datetime.utcnow() - self.start_time).total_seconds()

    @property
    def average_latency_ms(self) -> float:
        """Get average request latency in milliseconds."""
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    @property
    def success_rate(self) -> float:
        """Get success rate as a percentage."""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "uptime_seconds": self.uptime_seconds,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "average_latency_ms": self.average_latency_ms,
            "success_rate": self.success_rate,
        }


@dataclass
class ToolResult:
    """Standard result from a tool invocation."""

    success: bool
    data: Any = None
    error: str | None = None
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for MCP response."""
        result = {"success": self.success}
        if self.data is not None:
            result["data"] = self.data
        if self.error:
            result["error"] = self.error
        return result


def tool_handler(func: F) -> F:
    """
    Decorator for MCP tool handlers providing consistent error handling and metrics.

    Usage:
        @self.server.tool()
        @tool_handler
        async def my_tool(param: str) -> dict:
            # Tool implementation
            return {"result": param}
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        start_time = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            latency_ms = (time.perf_counter() - start_time) * 1000

            # If result is already a ToolResult, convert it
            if isinstance(result, ToolResult):
                result.latency_ms = latency_ms
                return result.to_dict()

            # Otherwise wrap in success result
            return ToolResult(success=True, data=result, latency_ms=latency_ms).to_dict()

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(f"Tool {func.__name__} failed: {e}")
            return ToolResult(success=False, error=str(e), latency_ms=latency_ms).to_dict()

    return wrapper  # type: ignore


class BaseMCPServer(ABC):
    """
    Abstract base class for Kubani MCP servers.

    Provides:
    - Standard server initialization
    - Health check endpoint
    - Metrics collection
    - Consistent logging

    Subclasses must implement:
    - register_tools(): Register server-specific tools
    - Optional: initialize() for async setup
    - Optional: cleanup() for async teardown
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        description: str = "",
    ):
        """
        Initialize the MCP server.

        Args:
            name: Server name (e.g., "temporal-mcp-server")
            version: Server version
            description: Human-readable description
        """
        self.name = name
        self.version = version
        self.description = description
        self.metrics = ServerMetrics()
        self._initialized = False

        # Create MCP server instance
        self.server = Server(name)

        # Register common tools
        self._register_common_tools()

        # Register server-specific tools
        self.register_tools()

    def _register_common_tools(self) -> None:
        """Register tools common to all MCP servers."""

        @self.server.tool()
        async def health() -> dict[str, Any]:
            """Check server health and get basic metrics."""
            return {
                "status": "healthy",
                "server": self.name,
                "version": self.version,
                "initialized": self._initialized,
                "metrics": self.metrics.to_dict(),
            }

        @self.server.tool()
        async def info() -> dict[str, Any]:
            """Get server information."""
            return {
                "name": self.name,
                "version": self.version,
                "description": self.description,
            }

    @abstractmethod
    def register_tools(self) -> None:
        """
        Register server-specific tools.

        Subclasses must implement this method to register their tools.

        Example:
            def register_tools(self) -> None:
                @self.server.tool()
                @tool_handler
                async def my_tool(param: str) -> str:
                    return f"Result: {param}"
        """
        pass

    async def initialize(self) -> None:
        """
        Perform async initialization.

        Override this method to perform async setup like connecting to databases.
        Called automatically when the server starts.
        """
        pass

    async def cleanup(self) -> None:
        """
        Perform async cleanup.

        Override this method to perform async teardown like closing connections.
        Called automatically when the server stops.
        """
        pass

    def record_request(self, success: bool, latency_ms: float) -> None:
        """Record a request for metrics."""
        self.metrics.total_requests += 1
        self.metrics.total_latency_ms += latency_ms
        if success:
            self.metrics.successful_requests += 1
        else:
            self.metrics.failed_requests += 1

    @asynccontextmanager
    async def lifespan(self):
        """Context manager for server lifecycle."""
        try:
            logger.info(f"Starting {self.name} v{self.version}")
            await self.initialize()
            self._initialized = True
            logger.info(f"{self.name} initialized successfully")
            yield
        finally:
            logger.info(f"Shutting down {self.name}")
            await self.cleanup()
            self._initialized = False
            logger.info(f"{self.name} shutdown complete")

    async def run(self) -> None:
        """Run the MCP server using stdio transport."""
        async with self.lifespan():
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options(),
                )

    def run_sync(self) -> None:
        """Run the server synchronously (for CLI entry points)."""
        asyncio.run(self.run())


class HealthCheckMixin:
    """
    Mixin providing health check functionality for services.

    Can be used with non-MCP services that need health checks.
    """

    _health_checks: dict[str, Callable[[], bool]]

    def __init__(self):
        self._health_checks = {}

    def register_health_check(self, name: str, check: Callable[[], bool]) -> None:
        """Register a health check function."""
        self._health_checks[name] = check

    def check_health(self) -> dict[str, Any]:
        """Run all health checks and return results."""
        results = {}
        all_healthy = True

        for name, check in self._health_checks.items():
            try:
                healthy = check()
                results[name] = {"healthy": healthy}
                if not healthy:
                    all_healthy = False
            except Exception as e:
                results[name] = {"healthy": False, "error": str(e)}
                all_healthy = False

        return {
            "status": "healthy" if all_healthy else "unhealthy",
            "checks": results,
        }
