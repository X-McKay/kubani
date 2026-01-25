"""
Skill Learner Agent - Learns from failures and proposes new skills.

Usage:
    from agents.skill_learner import SkillLearnerAgent

    agent = SkillLearnerAgent()
    count = await agent.analyze_and_propose()
"""

from .agent import (
    IncidentCluster,
    SkillLearnerAgent,
    UnmatchedIncident,
)

__all__ = [
    "SkillLearnerAgent",
    "UnmatchedIncident",
    "IncidentCluster",
]
