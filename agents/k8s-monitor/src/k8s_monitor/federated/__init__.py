"""
Federated agent architecture for k8s-monitor.

This module implements a simple multi-agent system:
- Sentinel: Watches K8s events via MCP, publishes issues to event bus
- Healer: Subscribes to issues, uses agent with MCP tools to investigate/fix
- Explorer: Learns from failures, proposes new markdown skills

Skills are loaded from skills/k8s/ directory as SKILL.md files.
"""

from k8s_monitor.federated.explorer import ExplorerAgent, run_explorer_cycle
from k8s_monitor.federated.healer import HealerAgent
from k8s_monitor.federated.sentinel import SentinelAgent, WatchMode

__all__ = [
    # Agents
    "SentinelAgent",
    "HealerAgent",
    "ExplorerAgent",
    "run_explorer_cycle",
    # Watch modes
    "WatchMode",
]
