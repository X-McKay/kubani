"""
Kubani Syndicates.

Syndicates are missions that orchestrate multiple agents to accomplish objectives.
Each syndicate defines which agents participate and how they coordinate.

Usage:
    from kubani.syndicates import Syndicate
    from kubani.agents.sentinel import SentinelAgent
    from kubani.agents.healer import HealerAgent

    class K8sMonitorSyndicate(Syndicate):
        agents = [SentinelAgent, HealerAgent]

        async def run(self):
            sentinel = self.get_agent(SentinelAgent)
            healer = self.get_agent(HealerAgent)
            # ... orchestration logic
"""

from kubani.syndicates._base.syndicate import Syndicate

__all__ = ["Syndicate"]
