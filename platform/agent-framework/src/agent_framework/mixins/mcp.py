"""MCP Client Mixin - Connect to MCP servers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_framework.base import AgentBase

logger = logging.getLogger(__name__)


class MCPClientMixin:
    """
    Mixin for MCP server connectivity.

    Provides access to MCP servers (Temporal, Qdrant, Memory, Discord).
    Auto-discovers endpoints based on run mode (local vs cluster).

    Usage:
        class MyAgent(AgentBase, MCPClientMixin):
            async def initialize(self) -> None:
                await super().initialize()
                await self.init_mcp()

            async def run(self) -> None:
                workflows = await self.mcp.temporal.list_workflows()
    """

    async def init_mcp(self: AgentBase) -> None:
        """Initialize MCP client connections."""
        from core_agents.mcp import get_mcp_client

        self._mcp_client = get_mcp_client()
        logger.info(f"MCP client initialized for {self.name}")

    @property
    def mcp(self: AgentBase) -> Any:
        """Get the MCP client."""
        if self._mcp_client is None:
            raise RuntimeError(
                "MCP client not initialized. Call await self.init_mcp() in initialize()."
            )
        return self._mcp_client

    async def call_mcp_tool(
        self: AgentBase,
        server: str,
        tool: str,
        **kwargs: Any,
    ) -> Any:
        """
        Call an MCP tool directly.

        Args:
            server: MCP server name (temporal, qdrant, memory, discord)
            tool: Tool name
            **kwargs: Tool arguments

        Returns:
            Tool result
        """
        server_client = getattr(self.mcp, server, None)
        if server_client is None:
            raise ValueError(f"Unknown MCP server: {server}")

        return await server_client.call_tool(tool, **kwargs)
