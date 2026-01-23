"""
Base classes for Kubani syndicates.

Usage:
    from kubani.syndicates._base import Syndicate

    class MySyndicate(Syndicate):
        agents = [AgentA, AgentB]

        async def run(self):
            ...
"""

from kubani.syndicates._base.syndicate import Syndicate

__all__ = ["Syndicate"]
