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

    def __init__(self, agent_dir: Path | None = None):
        super().__init__(agent_dir)
        self._mcp_client = None

    async def _load_mcp_tools(self) -> list[Any]:
        """Load Kubernetes MCP tools from the sidecar server."""
        mcp_url = os.environ.get("KUBERNETES_MCP_SERVER_URL")
        if not mcp_url:
            logger.warning("KUBERNETES_MCP_SERVER_URL not set, no K8s MCP tools")
            return []

        try:
            from mcp.client.sse import sse_client
            from strands.tools.mcp import MCPClient

            sse_url = mcp_url.rstrip("/")
            if not sse_url.endswith("/sse"):
                sse_url += "/sse"

            self._mcp_client = MCPClient(lambda u=sse_url: sse_client(u))
            tools = self._mcp_client.load_tools()
            logger.info(f"Loaded {len(tools)} K8s MCP tools from {mcp_url}")
            return tools
        except Exception as e:
            logger.warning(f"Failed to load K8s MCP tools: {e}")
            return []

    async def run(self, input_text: str) -> str:
        """Run the agent with MCP tools loaded."""
        if self._agent is None:
            mcp_tools = await self._load_mcp_tools()

            try:  # noqa: SIM105
                skill_tools = await self.get_tools()
            except Exception as e:
                logger.warning(f"Failed to load skills: {e}")
                skill_tools = []

            all_tools = skill_tools + mcp_tools
            self._agent = self._create_agent(tools=all_tools if all_tools else None)

        result = await self._agent.invoke_async(input_text)

        if hasattr(result, "message"):
            message = result.message
            if isinstance(message, dict):
                content = message.get("content", [])
                if isinstance(content, list):
                    for block in reversed(content):
                        if isinstance(block, dict) and "text" in block:
                            return block["text"]
                return str(content) if content else str(message)
            return str(message)
        return str(result)

    async def close(self) -> None:
        """Clean up MCP client connection."""
        if self._mcp_client:
            try:  # noqa: SIM105
                await self._mcp_client.stop()
            except Exception:
                pass

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record diagnostic outcomes for learning."""
        success = result.get("success", True)
        await self.record_outcome(skill_name, result, success=success)
