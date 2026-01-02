"""
Federated agent architecture for k8s-monitor.

This module implements the Voyager-inspired multi-agent system using:
- Skills: Knowledge about when/how to use MCP tools (not code)
- Events: Redis Streams for cross-agent communication
- Agents: Sentinel (watches), Healer (remediates), Explorer (learns)

Example:
    from k8s_monitor.federated import (
        SentinelAgent,
        HealerAgent,
        K8S_SKILLS,
        bootstrap_k8s_skills,
    )

    # Bootstrap initial skills
    await bootstrap_k8s_skills()

    # Start watching cluster events
    sentinel = SentinelAgent()
    await sentinel.start()
"""

from k8s_monitor.federated.healer import HealerAgent
from k8s_monitor.federated.sentinel import SentinelAgent
from k8s_monitor.federated.skills import (
    K8S_SKILLS,
    bootstrap_k8s_skills,
    get_k8s_skill,
)

__all__ = [
    # Skills
    "K8S_SKILLS",
    "bootstrap_k8s_skills",
    "get_k8s_skill",
    # Agents
    "SentinelAgent",
    "HealerAgent",
]
