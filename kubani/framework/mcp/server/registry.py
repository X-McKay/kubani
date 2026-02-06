"""
Registry integration for MCP servers.

Provides automatic registration and heartbeat functionality for MCP servers
to integrate with the Kubani Registry.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)


@dataclass
class MCPServerRegistration:
    """MCP server registration data."""

    id: str
    name: str
    description: str
    transport: Literal["sse", "stdio", "http"]
    connection_config: dict[str, str]
    capabilities: list[str]
    health_endpoint: str = "/health"
    metrics_endpoint: str = "/metrics"


class RegistryClient:
    """
    Client for MCP server self-registration with the Kubani Registry.

    Handles:
    - Initial registration on startup
    - Periodic heartbeats to maintain status
    - Graceful handling of registration failures

    Usage:
        client = RegistryClient(
            registry_url="http://registry.ai-agents.svc:8000",
            server_id="discord-mcp",
        )

        # Register on startup
        await client.register(
            name="Discord MCP Server",
            description="Bidirectional Discord integration",
            transport="sse",
            connection_config={
                "url": "https://discord-mcp.almckay.io/sse",
                "internal_url": "http://discord-mcp-server.ai-agents.svc:8080/sse"
            },
            capabilities=["messages.send", "messages.read"],
        )

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(client.start_heartbeat())

        # On shutdown
        heartbeat_task.cancel()
    """

    def __init__(
        self,
        registry_url: str,
        server_id: str,
        timeout: float = 10.0,
    ):
        """
        Initialize registry client.

        Args:
            registry_url: Base URL of the registry API
            server_id: Unique identifier for this MCP server
            timeout: Request timeout in seconds
        """
        self.registry_url = registry_url.rstrip("/")
        self.server_id = server_id
        self.timeout = timeout
        self._registered = False
        self._heartbeat_task: asyncio.Task | None = None

    async def register(
        self,
        name: str,
        description: str,
        transport: Literal["sse", "stdio", "http"],
        connection_config: dict[str, str],
        capabilities: list[str],
        health_endpoint: str = "/health",
        metrics_endpoint: str = "/metrics",
    ) -> bool:
        """
        Register this MCP server with the registry.

        Args:
            name: Human-readable server name
            description: Server description
            transport: Transport type (sse, stdio, http)
            connection_config: Connection configuration (URLs, etc.)
            capabilities: List of tool names/capabilities
            health_endpoint: Path to health endpoint
            metrics_endpoint: Path to metrics endpoint

        Returns:
            True if registration succeeded, False otherwise
        """
        registration = MCPServerRegistration(
            id=self.server_id,
            name=name,
            description=description,
            transport=transport,
            connection_config=connection_config,
            capabilities=capabilities,
            health_endpoint=health_endpoint,
            metrics_endpoint=metrics_endpoint,
        )

        url = f"{self.registry_url}/api/v1/mcp/servers"
        payload = {
            "id": registration.id,
            "name": registration.name,
            "description": registration.description,
            "transport": registration.transport,
            "connection_config": registration.connection_config,
            "capabilities": registration.capabilities,
            "status": "healthy",
            "health_endpoint": registration.health_endpoint,
            "metrics_endpoint": registration.metrics_endpoint,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

            logger.info(f"Successfully registered MCP server {self.server_id} with registry")
            self._registered = True
            return True

        except httpx.HTTPError as e:
            logger.warning(f"Failed to register with registry: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during registration: {e}")
            return False

    async def heartbeat(
        self,
        backend_status: dict[str, str] | None = None,
    ) -> bool:
        """
        Send a heartbeat to the registry.

        Args:
            backend_status: Optional dict of backend name -> status

        Returns:
            True if heartbeat succeeded, False otherwise
        """
        if not self._registered:
            logger.debug("Skipping heartbeat - not registered")
            return False

        url = f"{self.registry_url}/api/v1/mcp/servers/{self.server_id}/heartbeat"
        payload: dict[str, Any] = {
            "status": "healthy",
        }

        if backend_status:
            payload["backend_status"] = backend_status

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.put(url, json=payload)
                response.raise_for_status()

            logger.debug(f"Heartbeat sent for {self.server_id}")
            return True

        except httpx.HTTPError as e:
            logger.warning(f"Failed to send heartbeat: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during heartbeat: {e}")
            return False

    async def start_heartbeat(
        self,
        interval: int = 30,
        get_backend_status: Callable[[], Awaitable[dict[str, str]]] | None = None,
    ) -> None:
        """
        Start periodic heartbeat task.

        This is a long-running task that should be run in the background.

        Args:
            interval: Heartbeat interval in seconds
            get_backend_status: Optional async function that returns backend status dict

        Usage:
            task = asyncio.create_task(client.start_heartbeat())
            # ... later ...
            task.cancel()
        """
        logger.info(f"Starting heartbeat task with {interval}s interval")

        while True:
            try:
                backend_status = None
                if get_backend_status:
                    try:
                        backend_status = await get_backend_status()
                    except Exception as e:
                        logger.warning(f"Failed to get backend status: {e}")

                await self.heartbeat(backend_status=backend_status)
                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                logger.info("Heartbeat task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in heartbeat task: {e}")
                await asyncio.sleep(interval)

    async def unregister(self) -> bool:
        """
        Unregister this MCP server from the registry.

        Returns:
            True if unregistration succeeded, False otherwise
        """
        if not self._registered:
            return True

        url = f"{self.registry_url}/api/v1/mcp/servers/{self.server_id}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.delete(url)
                response.raise_for_status()

            logger.info(f"Successfully unregistered MCP server {self.server_id}")
            self._registered = False
            return True

        except httpx.HTTPError as e:
            logger.warning(f"Failed to unregister from registry: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during unregistration: {e}")
            return False
