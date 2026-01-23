"""
Kubani Syndicates.

Syndicates are missions that orchestrate multiple agents to accomplish objectives.
Each syndicate defines which agents participate and how they coordinate.

Usage:
    from syndicates import K8sMonitorSyndicate, NewsDigestSyndicate

    # Start a syndicate
    syndicate = K8sMonitorSyndicate()
    await syndicate.start()

    # Or create a custom syndicate
    from syndicates import Syndicate
    from agents.event_classifier import EventClassifierAgent
    from agents.remediator import RemediatorAgent

    class MySyndicate(Syndicate):
        agents = [EventClassifierAgent, RemediatorAgent]

        async def run(self):
            classifier = self.get_agent(EventClassifierAgent)
            remediator = self.get_agent(RemediatorAgent)
            # ... orchestration logic
"""

from syndicates._base.syndicate import Syndicate
from syndicates.k8s_monitor import K8sMonitorSyndicate
from syndicates.news_digest import NewsDigestSyndicate

__all__ = ["Syndicate", "K8sMonitorSyndicate", "NewsDigestSyndicate"]
