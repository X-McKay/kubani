"""
Federated agent architecture for k8s-monitor.

This module implements the Voyager-inspired multi-agent system using:
- Skills: Knowledge about when/how to use MCP tools (not code)
- Events: Redis Streams for cross-agent communication
- Agents: Sentinel (watches), Healer (remediates), Explorer (learns)
- Watch Streams: Real-time Kubernetes event detection (vs polling)

Example:
    from k8s_monitor.federated import (
        SentinelAgent,
        HealerAgent,
        ExplorerAgent,
        WatchMode,
        K8S_SKILLS,
        bootstrap_k8s_skills,
    )

    # Bootstrap initial skills
    await bootstrap_k8s_skills()

    # Start watching cluster events (uses watch streams by default)
    sentinel = SentinelAgent(watch_mode=WatchMode.AUTO)
    await sentinel.start()
"""

from k8s_monitor.federated.explorer import ExplorerAgent, run_explorer_cycle
from k8s_monitor.federated.healer import HealerAgent
from k8s_monitor.federated.sentinel import SentinelAgent, WatchMode
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
    "ExplorerAgent",
    "run_explorer_cycle",
    # Watch modes
    "WatchMode",
]
