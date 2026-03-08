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

    def __init__(self, agent_dir: Path | None = None):
        super().__init__(agent_dir)
        self._mcp_client = None
        self._mcp_tools: list[Any] = []

    def get_additional_tools(self) -> list[Any]:
        """Provide dispatch and publish tools."""
        from kubani.agents.k8s_coordinator.tools import (
            dispatch_diagnostics,
            dispatch_remediation,
            publish_results,
        )

        return [dispatch_diagnostics, dispatch_remediation, publish_results]

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
            self._mcp_tools = tools
            return tools
        except Exception as e:
            logger.warning(f"Failed to load K8s MCP tools: {e}")
            return []

    async def run(self, input_text: str) -> str:
        """Run the agent with MCP tools loaded."""
        if self._agent is None:
            # Load MCP tools first
            mcp_tools = await self._load_mcp_tools()

            # Load skills (best-effort)
            try:
                skill_tools = await self.get_tools()
            except Exception as e:
                logger.warning(f"Failed to load skills: {e}")
                skill_tools = []

            # Combine: skills + MCP tools + custom tools
            all_tools = skill_tools + mcp_tools
            # get_additional_tools already called by get_tools via base class,
            # but if skills failed, add them explicitly
            if not skill_tools:
                all_tools.extend(self.get_additional_tools())

            self._agent = self._create_agent(tools=all_tools if all_tools else None)

        result = await self._agent.invoke_async(input_text)

        # Extract text content from AgentResult
        if hasattr(result, "message"):
            message = result.message
            if isinstance(message, dict):
                content = message.get("content", [])
                if isinstance(content, list):
                    # Find the last text block (skip toolUse blocks)
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
        """Record skill outcomes for learning."""
        success = result.get("success", True)
        await self.record_outcome(skill_name, result, success=success)
