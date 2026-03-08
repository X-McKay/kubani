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
from pathlib import Path
from typing import Any

from kubani.agents._base import KubaniAgent

logger = logging.getLogger(__name__)


class K8sCoordinatorAgent(KubaniAgent):
    """Coordinates K8s cluster monitoring and dispatches to specialists."""

    AGENT_DIR = Path(__file__).parent

    def get_additional_tools(self) -> list[Any]:
        """Provide dispatch and publish tools."""
        from kubani.agents.k8s_coordinator.tools import (
            dispatch_diagnostics,
            dispatch_remediation,
            publish_results,
        )

        return [dispatch_diagnostics, dispatch_remediation, publish_results]

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("success", True)
        await self.record_outcome(skill_name, result, success=success)
