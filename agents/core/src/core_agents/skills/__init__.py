"""
Skill library framework for knowledge-based agent capabilities.

Skills represent KNOWLEDGE about when and how to use MCP tools, not executable code.
Each skill contains:
- Preconditions (when to apply)
- Actions (MCP tool references)
- Success criteria (how to verify)
- Learning metadata (confidence, usage stats)

This module provides:
- Skill schema (Pydantic models)
- SkillLibrary interface and Qdrant implementation
- Semantic retrieval by preconditions

Example:
    from core_agents.skills import Skill, SkillLibrary, get_skill_library

    # Create a skill (knowledge, not code)
    skill = Skill(
        id="k8s-restart-crashloop",
        name="Restart CrashLoopBackOff Pod",
        domain="k8s",
        category="remediation",
        description="Restart a pod stuck in CrashLoopBackOff",
        preconditions=["Pod status is CrashLoopBackOff", "Restart count > 3"],
        actions=[
            SkillAction(
                description="Delete pod to trigger recreation",
                mcp_tool=MCPToolReference(
                    server="kubernetes-mcp-server",
                    tool="pods_delete",
                    params={"name": "$pod_name", "namespace": "$namespace"},
                ),
            )
        ],
        success_criteria=["New pod reaches Running within 2 minutes"],
    )

    # Store and retrieve skills
    library = await get_skill_library()
    await library.add(skill)
    matches = await library.search("pod crashing repeatedly", domain="k8s")
"""

from core_agents.skills.library import (
    QdrantSkillLibrary,
    SkillLibrary,
    get_skill_library,
)
from core_agents.skills.schema import (
    MCPToolReference,
    Skill,
    SkillAction,
    SkillCategory,
    SkillDomain,
    SkillOutcome,
)

__all__ = [
    # Schema
    "Skill",
    "SkillAction",
    "SkillCategory",
    "SkillDomain",
    "SkillOutcome",
    "MCPToolReference",
    # Library
    "SkillLibrary",
    "QdrantSkillLibrary",
    "get_skill_library",
]
