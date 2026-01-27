# Phase 1: Server Utilities Module

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create `kubani/framework/mcp/server/` module that extracts shared patterns from all MCP servers.

**Architecture:** Module within the existing `kubani-framework` package providing base classes, connection management, error handling, health checks, and transport utilities.

**Tech Stack:** Python 3.11+, FastMCP (mcp library), pydantic, anyio

---

## Task 1: Create Module Structure

**Files:**
- Create: `kubani/framework/mcp/server/__init__.py`
- Modify: `kubani/framework/mcp/__init__.py`

**Step 1: Create directory structure**

```bash
mkdir -p kubani/framework/mcp/server
mkdir -p kubani/framework/mcp/server/testing
```

**Step 2: Create server/__init__.py**

```python
"""
Kubani MCP Server Utilities - Shared base code for MCP servers.

Provides:
- MCPServerBase: Base class for all MCP servers
- Connection management utilities
- Standardized error handling
- Health check utilities
- Transport mode handling
"""

from kubani.framework.mcp.server.base import MCPServerBase
from kubani.framework.mcp.server.connection import ConnectionManager, ConnectionState
from kubani.framework.mcp.server.errors import (
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
    MCPValidationError,
)
from kubani.framework.mcp.server.health import HealthCheck, HealthStatus
from kubani.framework.mcp.server.transport import TransportConfig, run_server

__all__ = [
    # Base
    "MCPServerBase",
    # Connection
    "ConnectionManager",
    "ConnectionState",
    # Errors
    "MCPError",
    "MCPConnectionError",
    "MCPTimeoutError",
    "MCPValidationError",
    # Health
    "HealthCheck",
    "HealthStatus",
    # Transport
    "TransportConfig",
    "run_server",
]
```

**Step 3: Update kubani/framework/mcp/__init__.py**

Add exports for the new server module:

```python
# Add to existing __init__.py
from kubani.framework.mcp.server import (
    MCPServerBase,
    ConnectionManager,
    ConnectionState,
    MCPError,
    MCPConnectionError,
    MCPTimeoutError,
    MCPValidationError,
    HealthCheck,
    HealthStatus,
    TransportConfig,
    run_server,
)
```

**Step 4: Commit**

```bash
git add kubani/framework/mcp/
git commit -m "feat(mcp): scaffold server utilities module

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Implement Error Module

**Files:**
- Create: `kubani/framework/mcp/server/errors.py`
- Create: `kubani/framework/mcp/server/tests/test_errors.py`

**Step 1: Write the failing test**

```python
# kubani/framework/mcp/server/tests/test_errors.py
"""Tests for MCP error classes."""

import pytest

from kubani.framework.mcp.server.errors import (
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
    MCPValidationError,
)


class TestMCPError:
    """Tests for base MCPError."""

    def test_basic_error(self):
        error = MCPError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.code == "MCP_ERROR"

    def test_error_with_details(self):
        error = MCPError("Failed", details={"key": "value"})
        assert error.details == {"key": "value"}

    def test_error_to_dict(self):
        error = MCPError("Failed", code="CUSTOM_CODE", details={"x": 1})
        d = error.to_dict()
        assert d["message"] == "Failed"
        assert d["code"] == "CUSTOM_CODE"
        assert d["details"] == {"x": 1}


class TestMCPConnectionError:
    """Tests for MCPConnectionError."""

    def test_connection_error(self):
        error = MCPConnectionError("Cannot connect to backend", server="qdrant")
        assert "Cannot connect to backend" in str(error)
        assert error.server == "qdrant"
        assert error.code == "MCP_CONNECTION_ERROR"

    def test_connection_error_to_dict(self):
        error = MCPConnectionError("Failed", server="temporal")
        d = error.to_dict()
        assert d["server"] == "temporal"


class TestMCPTimeoutError:
    """Tests for MCPTimeoutError."""

    def test_timeout_error(self):
        error = MCPTimeoutError("Operation timed out", timeout=30.0)
        assert error.timeout == 30.0
        assert error.code == "MCP_TIMEOUT"

    def test_timeout_error_to_dict(self):
        error = MCPTimeoutError("Slow", timeout=60.0)
        d = error.to_dict()
        assert d["timeout"] == 60.0


class TestMCPValidationError:
    """Tests for MCPValidationError."""

    def test_validation_error(self):
        error = MCPValidationError("Invalid input", field="name", value="")
        assert error.field == "name"
        assert error.value == ""
        assert error.code == "MCP_VALIDATION_ERROR"

    def test_validation_error_to_dict(self):
        error = MCPValidationError("Bad", field="age", value=-1)
        d = error.to_dict()
        assert d["field"] == "age"
        assert d["value"] == -1
```

**Step 2: Run test to verify it fails**

```bash
cd kubani/framework && uv run pytest mcp/server/tests/test_errors.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'kubani.framework.mcp.server.errors'`

**Step 3: Write minimal implementation**

```python
# kubani/framework/mcp/server/errors.py
"""
Standardized error classes for MCP servers.

All MCP servers should use these error classes for consistent
error handling and reporting.
"""

from typing import Any


class MCPError(Exception):
    """Base exception for all MCP errors."""

    code: str = "MCP_ERROR"

    def __init__(
        self,
        message: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for MCP response."""
        return {
            "message": self.message,
            "code": self.code,
            "details": self.details,
        }


class MCPConnectionError(MCPError):
    """Error connecting to a backend service."""

    code: str = "MCP_CONNECTION_ERROR"

    def __init__(
        self,
        message: str,
        server: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details=details)
        self.server = server

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        if self.server:
            d["server"] = self.server
        return d


class MCPTimeoutError(MCPError):
    """Operation timed out."""

    code: str = "MCP_TIMEOUT"

    def __init__(
        self,
        message: str,
        timeout: float | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details=details)
        self.timeout = timeout

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        if self.timeout is not None:
            d["timeout"] = self.timeout
        return d


class MCPValidationError(MCPError):
    """Validation error for tool inputs."""

    code: str = "MCP_VALIDATION_ERROR"

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details=details)
        self.field = field
        self.value = value

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        if self.field:
            d["field"] = self.field
        if self.value is not None:
            d["value"] = self.value
        return d
```

**Step 4: Run test to verify it passes**

```bash
cd kubani/framework && uv run pytest mcp/server/tests/test_errors.py -v
```
Expected: PASS (all 8 tests)

**Step 5: Commit**

```bash
git add kubani/framework/mcp/server/errors.py kubani/framework/mcp/server/tests/test_errors.py
git commit -m "feat(mcp): add standardized error classes

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Implement Connection Manager

**Files:**
- Create: `kubani/framework/mcp/server/connection.py`
- Create: `kubani/framework/mcp/server/tests/test_connection.py`

**Step 1: Write the failing test**

```python
# kubani/framework/mcp/server/tests/test_connection.py
"""Tests for connection management utilities."""

import pytest

from kubani.framework.mcp.server.connection import ConnectionManager, ConnectionState


class TestConnectionState:
    """Tests for ConnectionState enum."""

    def test_states_exist(self):
        assert ConnectionState.DISCONNECTED.value == "disconnected"
        assert ConnectionState.CONNECTING.value == "connecting"
        assert ConnectionState.CONNECTED.value == "connected"
        assert ConnectionState.FAILED.value == "failed"


class TestConnectionManager:
    """Tests for ConnectionManager."""

    @pytest.mark.asyncio
    async def test_initial_state(self):
        manager = ConnectionManager(name="test")
        assert manager.state == ConnectionState.DISCONNECTED
        assert manager.name == "test"

    @pytest.mark.asyncio
    async def test_connect_success(self):
        manager = ConnectionManager(name="test")

        async def connect_fn():
            return {"client": "connected"}

        result = await manager.connect(connect_fn)
        assert result == {"client": "connected"}
        assert manager.state == ConnectionState.CONNECTED

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        manager = ConnectionManager(name="test")

        async def failing_connect():
            raise ValueError("Connection refused")

        with pytest.raises(ValueError, match="Connection refused"):
            await manager.connect(failing_connect)

        assert manager.state == ConnectionState.FAILED

    @pytest.mark.asyncio
    async def test_disconnect(self):
        manager = ConnectionManager(name="test")

        async def connect_fn():
            return "client"

        async def disconnect_fn():
            pass

        await manager.connect(connect_fn)
        assert manager.state == ConnectionState.CONNECTED

        await manager.disconnect(disconnect_fn)
        assert manager.state == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_is_connected(self):
        manager = ConnectionManager(name="test")
        assert not manager.is_connected

        async def connect_fn():
            return "client"

        await manager.connect(connect_fn)
        assert manager.is_connected

    @pytest.mark.asyncio
    async def test_ensure_connected_raises(self):
        from kubani.framework.mcp.server.errors import MCPConnectionError

        manager = ConnectionManager(name="test-server")

        with pytest.raises(MCPConnectionError) as exc_info:
            manager.ensure_connected()

        assert exc_info.value.server == "test-server"

    @pytest.mark.asyncio
    async def test_ensure_connected_passes(self):
        manager = ConnectionManager(name="test")

        async def connect_fn():
            return "client"

        await manager.connect(connect_fn)
        # Should not raise
        manager.ensure_connected()
```

**Step 2: Run test to verify it fails**

```bash
cd kubani/framework && uv run pytest mcp/server/tests/test_connection.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# kubani/framework/mcp/server/connection.py
"""
Connection management utilities for MCP servers.

Provides consistent connection lifecycle management across all servers.
"""

import logging
from enum import Enum
from typing import Any, Awaitable, Callable, TypeVar

from kubani.framework.mcp.server.errors import MCPConnectionError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ConnectionState(Enum):
    """Connection states for a backend service."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


class ConnectionManager:
    """
    Manages connection lifecycle for a backend service.

    Usage:
        manager = ConnectionManager(name="qdrant")

        async def connect():
            return await QdrantClient.connect()

        client = await manager.connect(connect)
        manager.ensure_connected()  # Raises if not connected

        await manager.disconnect(client.close)
    """

    def __init__(self, name: str):
        """
        Initialize connection manager.

        Args:
            name: Name of the service (for error messages)
        """
        self.name = name
        self._state = ConnectionState.DISCONNECTED
        self._error: Exception | None = None

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._state == ConnectionState.CONNECTED

    @property
    def last_error(self) -> Exception | None:
        """Last connection error, if any."""
        return self._error

    async def connect(
        self,
        connect_fn: Callable[[], Awaitable[T]],
    ) -> T:
        """
        Connect to the backend service.

        Args:
            connect_fn: Async function that establishes connection and returns client

        Returns:
            The client/connection object returned by connect_fn

        Raises:
            Exception from connect_fn if connection fails
        """
        self._state = ConnectionState.CONNECTING
        self._error = None

        try:
            logger.info(f"Connecting to {self.name}...")
            result = await connect_fn()
            self._state = ConnectionState.CONNECTED
            logger.info(f"Connected to {self.name}")
            return result
        except Exception as e:
            self._state = ConnectionState.FAILED
            self._error = e
            logger.error(f"Failed to connect to {self.name}: {e}")
            raise

    async def disconnect(
        self,
        disconnect_fn: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """
        Disconnect from the backend service.

        Args:
            disconnect_fn: Optional async function to clean up the connection
        """
        if disconnect_fn:
            try:
                logger.info(f"Disconnecting from {self.name}...")
                await disconnect_fn()
            except Exception as e:
                logger.warning(f"Error disconnecting from {self.name}: {e}")

        self._state = ConnectionState.DISCONNECTED
        logger.info(f"Disconnected from {self.name}")

    def ensure_connected(self) -> None:
        """
        Ensure the service is connected, raise if not.

        Raises:
            MCPConnectionError: If not in CONNECTED state
        """
        if self._state != ConnectionState.CONNECTED:
            raise MCPConnectionError(
                f"{self.name} is not connected. "
                f"Current state: {self._state.value}. "
                "Ensure connect() was called at server startup.",
                server=self.name,
            )
```

**Step 4: Run test to verify it passes**

```bash
cd kubani/framework && uv run pytest mcp/server/tests/test_connection.py -v
```
Expected: PASS (all 7 tests)

**Step 5: Commit**

```bash
git add kubani/framework/mcp/server/connection.py kubani/framework/mcp/server/tests/test_connection.py
git commit -m "feat(mcp): add connection management utilities

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Implement Health Check Utilities

**Files:**
- Create: `kubani/framework/mcp/server/health.py`
- Create: `kubani/framework/mcp/server/tests/test_health.py`

**Step 1: Write the failing test**

```python
# kubani/framework/mcp/server/tests/test_health.py
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
```

**Step 2: Run test to verify it fails**

```bash
cd kubani/framework && uv run pytest mcp/server/tests/test_health.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# kubani/framework/mcp/server/health.py
"""
Health check utilities for MCP servers.

Provides standardized health checking across all MCP servers.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable

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

        except asyncio.TimeoutError:
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
```

**Step 4: Run test to verify it passes**

```bash
cd kubani/framework && uv run pytest mcp/server/tests/test_health.py -v
```
Expected: PASS (all 5 tests)

**Step 5: Commit**

```bash
git add kubani/framework/mcp/server/health.py kubani/framework/mcp/server/tests/test_health.py
git commit -m "feat(mcp): add health check utilities

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Implement Transport Utilities

**Files:**
- Create: `kubani/framework/mcp/server/transport.py`
- Create: `kubani/framework/mcp/server/tests/test_transport.py`

**Step 1: Write the failing test**

```python
# kubani/framework/mcp/server/tests/test_transport.py
"""Tests for transport mode utilities."""

import os

import pytest

from kubani.framework.mcp.server.transport import TransportConfig, TransportMode


class TestTransportMode:
    """Tests for TransportMode enum."""

    def test_modes_exist(self):
        assert TransportMode.STDIO.value == "stdio"
        assert TransportMode.SSE.value == "sse"
        assert TransportMode.HTTP.value == "http"


class TestTransportConfig:
    """Tests for TransportConfig."""

    def test_default_config(self):
        config = TransportConfig()
        assert config.mode == TransportMode.STDIO
        assert config.host == "0.0.0.0"
        assert config.port == 8080

    def test_from_args_stdio(self):
        config = TransportConfig.from_args(["--mode", "stdio"])
        assert config.mode == TransportMode.STDIO

    def test_from_args_sse(self):
        config = TransportConfig.from_args(["--mode", "sse", "--port", "9000"])
        assert config.mode == TransportMode.SSE
        assert config.port == 9000

    def test_from_args_http(self):
        config = TransportConfig.from_args([
            "--mode", "http",
            "--host", "127.0.0.1",
            "--port", "8888"
        ])
        assert config.mode == TransportMode.HTTP
        assert config.host == "127.0.0.1"
        assert config.port == 8888

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("MCP_TRANSPORT", "sse")
        monkeypatch.setenv("MCP_HOST", "localhost")
        monkeypatch.setenv("MCP_PORT", "7777")

        config = TransportConfig.from_env()
        assert config.mode == TransportMode.SSE
        assert config.host == "localhost"
        assert config.port == 7777

    def test_from_env_defaults(self, monkeypatch):
        # Clear any existing env vars
        monkeypatch.delenv("MCP_TRANSPORT", raising=False)
        monkeypatch.delenv("MCP_HOST", raising=False)
        monkeypatch.delenv("MCP_PORT", raising=False)

        config = TransportConfig.from_env()
        assert config.mode == TransportMode.STDIO
        assert config.host == "0.0.0.0"
        assert config.port == 8080

    def test_from_args_with_allowed_hosts(self):
        config = TransportConfig.from_args([
            "--mode", "sse",
            "--allowed-hosts", "example.com:*,api.example.com:443"
        ])
        assert "example.com:*" in config.allowed_hosts
        assert "api.example.com:443" in config.allowed_hosts
        # Should also have localhost defaults
        assert "localhost:*" in config.allowed_hosts
```

**Step 2: Run test to verify it fails**

```bash
cd kubani/framework && uv run pytest mcp/server/tests/test_transport.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# kubani/framework/mcp/server/transport.py
"""
Transport mode utilities for MCP servers.

Provides consistent argument parsing and transport configuration
across all MCP servers.
"""

import argparse
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import anyio
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)


class TransportMode(Enum):
    """Supported MCP transport modes."""

    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


@dataclass
class TransportConfig:
    """Configuration for MCP transport."""

    mode: TransportMode = TransportMode.STDIO
    host: str = "0.0.0.0"
    port: int = 8080
    allowed_hosts: list[str] = field(
        default_factory=lambda: ["localhost:*", "127.0.0.1:*"]
    )

    @classmethod
    def from_args(cls, args: list[str] | None = None) -> "TransportConfig":
        """
        Parse transport config from command line arguments.

        Args:
            args: Command line arguments (defaults to sys.argv[1:])

        Returns:
            TransportConfig instance
        """
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument(
            "--mode",
            choices=["stdio", "sse", "http"],
            default="stdio",
            help="Transport mode",
        )
        parser.add_argument(
            "--host",
            default="0.0.0.0",
            help="Host to bind to",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8080,
            help="Port to bind to",
        )
        parser.add_argument(
            "--allowed-hosts",
            default="",
            help="Comma-separated list of allowed hosts",
        )

        parsed, _ = parser.parse_known_args(args)

        allowed_hosts = ["localhost:*", "127.0.0.1:*"]
        if parsed.allowed_hosts:
            allowed_hosts.extend(
                h.strip() for h in parsed.allowed_hosts.split(",") if h.strip()
            )

        return cls(
            mode=TransportMode(parsed.mode),
            host=parsed.host,
            port=parsed.port,
            allowed_hosts=allowed_hosts,
        )

    @classmethod
    def from_env(cls) -> "TransportConfig":
        """
        Load transport config from environment variables.

        Environment variables:
            MCP_TRANSPORT: Transport mode (stdio, sse, http)
            MCP_HOST: Host to bind to
            MCP_PORT: Port to bind to
            MCP_ALLOWED_HOSTS: Comma-separated allowed hosts

        Returns:
            TransportConfig instance
        """
        mode_str = os.environ.get("MCP_TRANSPORT", "stdio")
        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8080"))

        allowed_hosts = ["localhost:*", "127.0.0.1:*"]
        allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
        if allowed_hosts_env:
            allowed_hosts.extend(
                h.strip() for h in allowed_hosts_env.split(",") if h.strip()
            )

        return cls(
            mode=TransportMode(mode_str),
            host=host,
            port=port,
            allowed_hosts=allowed_hosts,
        )


async def run_server_async(
    mcp: FastMCP,
    config: TransportConfig,
    startup_hook: Callable[[], None] | None = None,
    shutdown_hook: Callable[[], None] | None = None,
) -> None:
    """
    Run the MCP server with the specified transport configuration.

    Args:
        mcp: The FastMCP server instance
        config: Transport configuration
        startup_hook: Optional async function to call before serving
        shutdown_hook: Optional async function to call on shutdown
    """
    try:
        if startup_hook:
            await startup_hook()

        if config.mode == TransportMode.STDIO:
            await mcp.run_stdio_async()
        elif config.mode == TransportMode.SSE:
            logger.info(f"Starting SSE server on {config.host}:{config.port}")
            mcp.settings.host = config.host
            mcp.settings.port = config.port
            await mcp.run_sse_async()
        elif config.mode == TransportMode.HTTP:
            logger.info(f"Starting HTTP server on {config.host}:{config.port}")
            mcp.settings.host = config.host
            mcp.settings.port = config.port
            await mcp.run_streamable_http_async()
    finally:
        if shutdown_hook:
            await shutdown_hook()


def run_server(
    mcp: FastMCP,
    config: TransportConfig,
    startup_hook: Callable[[], None] | None = None,
    shutdown_hook: Callable[[], None] | None = None,
) -> None:
    """
    Run the MCP server synchronously.

    This is a convenience wrapper around run_server_async.

    Args:
        mcp: The FastMCP server instance
        config: Transport configuration
        startup_hook: Optional async function to call before serving
        shutdown_hook: Optional async function to call on shutdown
    """
    anyio.run(
        run_server_async,
        mcp,
        config,
        startup_hook,
        shutdown_hook,
    )
```

**Step 4: Run test to verify it passes**

```bash
cd kubani/framework && uv run pytest mcp/server/tests/test_transport.py -v
```
Expected: PASS (all 7 tests)

**Step 5: Commit**

```bash
git add kubani/framework/mcp/server/transport.py kubani/framework/mcp/server/tests/test_transport.py
git commit -m "feat(mcp): add transport mode utilities

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Implement Base Server Class

**Files:**
- Create: `kubani/framework/mcp/server/base.py`
- Create: `kubani/framework/mcp/server/tests/test_base.py`

**Step 1: Write the failing test**

```python
# kubani/framework/mcp/server/tests/test_base.py
"""Tests for MCPServerBase class."""

import pytest

from kubani.framework.mcp.server.base import MCPServerBase
from kubani.framework.mcp.server.health import HealthStatus


class MockBackendServer(MCPServerBase):
    """Mock server for testing."""

    name = "mock-server"
    description = "A mock MCP server for testing"

    def __init__(self):
        super().__init__()
        self.connected = False
        self.tools_registered = False

    async def connect_backend(self) -> None:
        self.connected = True

    async def disconnect_backend(self) -> None:
        self.connected = False

    def register_tools(self, mcp) -> None:
        self.tools_registered = True

        @mcp.tool()
        async def echo(message: str) -> dict:
            """Echo back the message."""
            return {"echo": message}


class FailingServer(MCPServerBase):
    """Server that fails to connect."""

    name = "failing-server"
    description = "Always fails to connect"

    async def connect_backend(self) -> None:
        raise ConnectionError("Backend unavailable")

    async def disconnect_backend(self) -> None:
        pass

    def register_tools(self, mcp) -> None:
        pass


class TestMCPServerBase:
    """Tests for MCPServerBase."""

    def test_create_server(self):
        server = MockBackendServer()
        mcp = server.create_server()

        assert mcp.name == "mock-server"
        assert server.tools_registered

    @pytest.mark.asyncio
    async def test_startup_shutdown(self):
        server = MockBackendServer()
        mcp = server.create_server()

        # Simulate lifespan startup
        await server.startup()
        assert server.connected
        assert server.connection.is_connected

        # Simulate lifespan shutdown
        await server.shutdown()
        assert not server.connected

    @pytest.mark.asyncio
    async def test_health_check(self):
        server = MockBackendServer()
        await server.startup()

        result = await server.health_check()
        assert result.status == HealthStatus.HEALTHY
        assert result.name == "mock-server"

        await server.shutdown()

    @pytest.mark.asyncio
    async def test_health_check_not_connected(self):
        server = MockBackendServer()
        # Don't call startup

        result = await server.health_check()
        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_connection_failure(self):
        server = FailingServer()

        with pytest.raises(ConnectionError, match="Backend unavailable"):
            await server.startup()

    def test_get_client_before_connect(self):
        from kubani.framework.mcp.server.errors import MCPConnectionError

        server = MockBackendServer()

        with pytest.raises(MCPConnectionError):
            server.ensure_connected()

    @pytest.mark.asyncio
    async def test_ensure_connected_after_connect(self):
        server = MockBackendServer()
        await server.startup()

        # Should not raise
        server.ensure_connected()

        await server.shutdown()
```

**Step 2: Run test to verify it fails**

```bash
cd kubani/framework && uv run pytest mcp/server/tests/test_base.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# kubani/framework/mcp/server/base.py
"""
Base class for MCP servers.

Provides a consistent foundation for all Kubani MCP servers with:
- Connection lifecycle management
- Health checks
- Transport configuration
- Error handling
"""

import logging
import os
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from kubani.framework.mcp.server.connection import ConnectionManager
from kubani.framework.mcp.server.health import HealthCheck, HealthResult, HealthStatus

logger = logging.getLogger(__name__)


class MCPServerBase(ABC):
    """
    Base class for all Kubani MCP servers.

    Subclasses must implement:
        - name: Server name
        - description: Server description
        - connect_backend(): Connect to backend service
        - disconnect_backend(): Disconnect from backend service
        - register_tools(mcp): Register MCP tools

    Usage:
        class MyServer(MCPServerBase):
            name = "my-server"
            description = "Does useful things"

            async def connect_backend(self):
                self._client = await SomeClient.connect()

            async def disconnect_backend(self):
                await self._client.close()

            def register_tools(self, mcp):
                @mcp.tool()
                async def my_tool() -> dict:
                    return {"result": "ok"}

        if __name__ == "__main__":
            server = MyServer()
            server.run()
    """

    # Subclasses must set these
    name: str
    description: str

    def __init__(self):
        """Initialize the server."""
        self.connection = ConnectionManager(name=self.name)
        self._mcp: FastMCP | None = None

    def create_server(self) -> FastMCP:
        """
        Create and configure the FastMCP server.

        Returns:
            Configured FastMCP instance with tools registered
        """
        # Get allowed hosts from environment or use defaults
        allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
        allowed_hosts = ["localhost:*", "127.0.0.1:*"]
        if allowed_hosts_env:
            allowed_hosts.extend(
                h.strip() for h in allowed_hosts_env.split(",") if h.strip()
            )

        mcp = FastMCP(
            name=self.name,
            instructions=self.description,
            lifespan=self._lifespan,
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=allowed_hosts,
            ),
        )

        # Register tools from subclass
        self.register_tools(mcp)

        # Register built-in health tool
        self._register_health_tool(mcp)

        self._mcp = mcp
        return mcp

    def _register_health_tool(self, mcp: FastMCP) -> None:
        """Register the health check tool."""

        @mcp.tool()
        async def health() -> dict[str, Any]:
            """
            Check the health of the MCP server.

            Returns:
                Health status including backend connectivity
            """
            result = await self.health_check()
            return result.to_dict()

    @asynccontextmanager
    async def _lifespan(self, server: FastMCP):
        """
        MCP server lifespan context manager.

        Handles startup (backend connection) and shutdown (cleanup).
        """
        await self.startup()
        try:
            yield
        finally:
            await self.shutdown()

    async def startup(self) -> None:
        """
        Start the server - connect to backend.

        Called automatically during server lifespan.
        """
        await self.connection.connect(self.connect_backend)

    async def shutdown(self) -> None:
        """
        Shut down the server - disconnect from backend.

        Called automatically during server lifespan.
        """
        await self.connection.disconnect(self.disconnect_backend)

    def ensure_connected(self) -> None:
        """
        Ensure the backend is connected.

        Raises:
            MCPConnectionError: If not connected
        """
        self.connection.ensure_connected()

    async def health_check(self) -> HealthResult:
        """
        Run a health check on the server.

        Returns:
            HealthResult with status and latency
        """

        async def check() -> bool:
            return self.connection.is_connected

        hc = HealthCheck(name=self.name, check_fn=check)
        return await hc.run()

    @abstractmethod
    async def connect_backend(self) -> None:
        """
        Connect to the backend service.

        Subclasses implement this to establish connections to
        their specific backend (e.g., Qdrant, Temporal, etc.)
        """
        ...

    @abstractmethod
    async def disconnect_backend(self) -> None:
        """
        Disconnect from the backend service.

        Subclasses implement this to clean up connections.
        """
        ...

    @abstractmethod
    def register_tools(self, mcp: FastMCP) -> None:
        """
        Register MCP tools on the server.

        Subclasses implement this to add their specific tools:

            def register_tools(self, mcp):
                @mcp.tool()
                async def my_tool(param: str) -> dict:
                    return {"result": param}

        Args:
            mcp: The FastMCP instance to register tools on
        """
        ...
```

**Step 4: Run test to verify it passes**

```bash
cd kubani/framework && uv run pytest mcp/server/tests/test_base.py -v
```
Expected: PASS (all 7 tests)

**Step 5: Commit**

```bash
git add kubani/framework/mcp/server/base.py kubani/framework/mcp/server/tests/test_base.py
git commit -m "feat(mcp): add MCPServerBase class

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Run All Tests & Finalize Phase 1

**Step 1: Ensure __init__.py is complete**

Verify `kubani/framework/mcp/server/__init__.py` exports all modules correctly (should already be done in Task 1).

**Step 2: Create conftest.py for common test fixtures**

```python
# kubani/framework/mcp/server/tests/conftest.py
"""Common test fixtures for MCP server utilities."""

import pytest


@pytest.fixture
def mock_env(monkeypatch):
    """Fixture to set MCP environment variables."""
    def _set(**kwargs):
        for key, value in kwargs.items():
            monkeypatch.setenv(key, str(value))
    return _set
```

**Step 3: Create tests/__init__.py**

```python
# kubani/framework/mcp/server/tests/__init__.py
"""Tests for kubani.framework.mcp.server module."""
```

**Step 4: Run all tests**

```bash
cd kubani/framework && uv run pytest mcp/server/tests/ -v --tb=short
```
Expected: All tests pass (27+ tests)

**Step 5: Final commit**

```bash
git add kubani/framework/mcp/server/
git commit -m "feat(mcp): complete server utilities module

Shared base code for all MCP servers including:
- MCPServerBase: Base class with lifecycle management
- ConnectionManager: Backend connection utilities
- Health checks: Standardized health monitoring
- Transport utilities: Consistent arg parsing
- Error classes: Standardized MCP errors

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

Phase 1 creates the `kubani/framework/mcp/server/` module with:

| Module | Purpose |
|--------|---------|
| `errors.py` | Standardized MCP error classes |
| `connection.py` | Connection lifecycle management |
| `health.py` | Health check utilities |
| `transport.py` | Transport mode handling |
| `base.py` | MCPServerBase abstract base class |

All servers in Phase 2 will be updated to inherit from `MCPServerBase` and use these utilities.

**Proceed to:** `2026-01-27-mcp-phase2-server-fixes.md`
