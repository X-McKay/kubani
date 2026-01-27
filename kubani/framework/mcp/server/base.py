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
from kubani.framework.mcp.server.health import HealthCheck, HealthResult

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
            allowed_hosts.extend(h.strip() for h in allowed_hosts_env.split(",") if h.strip())

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
