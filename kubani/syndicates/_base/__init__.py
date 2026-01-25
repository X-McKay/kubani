"""
Base classes for Kubani syndicates.

Usage:
    from syndicates._base import Syndicate

    class MySyndicate(Syndicate):
        agents = [AgentA, AgentB]

        async def run(self):
            ...
"""

from .syndicate import Syndicate

__all__ = ["Syndicate"]
