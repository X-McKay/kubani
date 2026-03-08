"""
K8s Coordinator Agent.

Orchestrates cluster health monitoring by collecting cluster state,
identifying issues, and dispatching to specialist agents for investigation
and remediation.

Usage:
    from kubani.agents.k8s_coordinator import K8sCoordinatorAgent

    agent = K8sCoordinatorAgent()
    result = await agent.run("Run cluster health check. Trigger: scheduled.")
"""

import logging
import os
from pathlib import Path
from typing import Any

from kubani.agents._base import KubaniAgent

logger = logging.getLogger(__name__)


class K8sCoordinatorAgent(KubaniAgent):
    """Coordinates K8s cluster monitoring and dispatches to specialists."""

    AGENT_DIR = Path(__file__).parent

    def get_additional_tools(self) -> list[Any]:
        """Provide dispatch/publish tools and K8s MCP client."""
        from kubani.agents.k8s_coordinator.tools import (
            dispatch_diagnostics,
            dispatch_remediation,
            publish_results,
        )

        tools: list[Any] = [dispatch_diagnostics, dispatch_remediation, publish_results]

        # Add K8s MCP server as a ToolProvider — Strands handles connection lifecycle
        mcp_url = os.environ.get("KUBERNETES_MCP_SERVER_URL")
        if mcp_url:
            try:
                from mcp.client.sse import sse_client
                from strands.tools.mcp import MCPClient

                sse_url = mcp_url.rstrip("/")
                if not sse_url.endswith("/sse"):
                    sse_url += "/sse"

                tools.append(MCPClient(lambda u=sse_url: sse_client(u)))
                logger.info(f"K8s MCP client configured: {mcp_url}")
            except Exception as e:
                logger.error(f"Failed to create K8s MCP client: {e}")
                raise

        return tools

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("success", True)
        await self.record_outcome(skill_name, result, success=success)
