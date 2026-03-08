"""
K8s Diagnostics Agent.

Investigates Kubernetes issues by gathering logs, events, and resource
status. Reports findings with root cause analysis. Never remediates.

Usage:
    from kubani.agents.k8s_diagnostics import K8sDiagnosticsAgent

    agent = K8sDiagnosticsAgent()
    findings = await agent.run("OOMKilled on Pod/vllm-abc in namespace vllm")
"""

import logging
import os
from pathlib import Path
from typing import Any

from kubani.agents._base import KubaniAgent

logger = logging.getLogger(__name__)


class K8sDiagnosticsAgent(KubaniAgent):
    """Investigates K8s issues and reports root cause analysis."""

    AGENT_DIR = Path(__file__).parent

    def get_additional_tools(self) -> list[Any]:
        """Provide K8s MCP client as a ToolProvider."""
        tools: list[Any] = []

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
        """Record diagnostic outcomes for learning."""
        success = result.get("success", True)
        await self.record_outcome(skill_name, result, success=success)
