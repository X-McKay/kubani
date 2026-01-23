"""
Skill Learner Agent - Learns from failures and proposes new skills.

Usage:
    from kubani.agents.skill_learner import SkillLearnerAgent

    agent = SkillLearnerAgent()
    count = await agent.analyze_and_propose()
"""

from kubani.agents.skill_learner.agent import (
    IncidentCluster,
    SkillLearnerAgent,
    UnmatchedIncident,
)

__all__ = [
    "SkillLearnerAgent",
    "UnmatchedIncident",
    "IncidentCluster",
]
