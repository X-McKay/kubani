"""
Base classes for Kubani agents.

Usage:
    from kubani.agents._base import KubaniAgent

    class MyAgent(KubaniAgent):
        async def on_skill_complete(self, skill_name: str, result: dict):
            await self.record_outcome(skill_name, result)
"""

from kubani.agents._base.agent import KubaniAgent

__all__ = ["KubaniAgent"]
