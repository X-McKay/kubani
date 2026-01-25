"""
Kubani Agents.

Agents are roles/personas that use skills to perform specific work.
Each agent has a system prompt, skill configuration, and optional hooks.

Usage:
    from agents import KubaniAgent

    class SentinelAgent(KubaniAgent):
        '''Detects and classifies Kubernetes cluster events.'''

        async def on_skill_complete(self, skill_name: str, result: dict):
            await self.record_outcome(skill_name, result)
"""

from ._base.agent import KubaniAgent

__all__ = ["KubaniAgent"]
