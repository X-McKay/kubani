"""
Connection management utilities for MCP servers.

Provides consistent connection lifecycle management across all servers.
"""

import logging
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar

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
