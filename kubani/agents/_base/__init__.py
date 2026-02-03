"""
Base classes for Kubani agents.

Usage:
    from agents._base import KubaniAgent

    class MyAgent(KubaniAgent):
        async def on_skill_complete(self, skill_name: str, result: dict):
            await self.record_outcome(skill_name, result)

For skills-centric agents:
    from agents._base import SkillsOrchestrator

    class MySkillsAgent(SkillsOrchestrator):
        SKILLS_DOMAIN = "news"
        SKILLS_CATEGORY = "collection"

        async def on_skill_complete(self, skill_name: str, result: dict):
            await self.record_outcome(skill_name, result)
"""

from .agent import KubaniAgent
from .skills_orchestrator import SkillsOrchestrator

__all__ = ["KubaniAgent", "SkillsOrchestrator"]
