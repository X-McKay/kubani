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
from pathlib import Path
from typing import Any

from kubani.agents._base import KubaniAgent

logger = logging.getLogger(__name__)


class K8sDiagnosticsAgent(KubaniAgent):
    """Investigates K8s issues and reports root cause analysis."""

    AGENT_DIR = Path(__file__).parent

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record diagnostic outcomes for learning."""
        success = result.get("success", True)
        await self.record_outcome(skill_name, result, success=success)
