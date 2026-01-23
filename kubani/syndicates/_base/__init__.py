"""
Base classes for Kubani syndicates.

Usage:
    from syndicates._base import Syndicate

    class MySyndicate(Syndicate):
        agents = [AgentA, AgentB]

        async def run(self):
            # Access SOPs directory for strands-agents-sops MCP
            sops_path = self.sops_dir
            ...
"""

from syndicates._base.syndicate import Syndicate

__all__ = ["Syndicate"]
