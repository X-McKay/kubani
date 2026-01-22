"""Skill Loader Mixin - Load and execute skills."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_framework.base import AgentBase
    from agent_framework.trace import ExecutionTrace

logger = logging.getLogger(__name__)


class SkillLoaderMixin:
    """
    Mixin for skill loading and execution.

    Provides access to skills from the skills directory.

    Usage:
        class MyAgent(AgentBase, SkillLoaderMixin):
            async def initialize(self) -> None:
                await super().initialize()
                await self.init_skills()

            async def run(self) -> None:
                trace = await self.execute_skill(
                    "investigate-pod-failure",
                    context={"pod": "nginx-abc"},
                )
    """

    async def init_skills(
        self: AgentBase,
        skills_dir: str | Path | None = None,
    ) -> None:
        """
        Initialize skill loader.

        Args:
            skills_dir: Directory containing skills (default: agents/skills/)
        """
        from agent_framework.skill_executor import SkillExecutor

        if skills_dir is None:
            # Default to agents/skills/ relative to repo root
            skills_dir = Path(__file__).parents[5] / "agents" / "skills"

        self._skill_loader = SkillExecutor(
            skills_dir=skills_dir,
            llm_client=getattr(self, "_llm_client", None),
            mcp_client=getattr(self, "_mcp_client", None),
        )

        logger.info(f"Skills initialized from {skills_dir}")

    @property
    def skills(self: AgentBase) -> Any:
        """Get the skill executor."""
        if self._skill_loader is None:
            raise RuntimeError(
                "Skills not initialized. Call await self.init_skills() in initialize()."
            )
        return self._skill_loader

    async def execute_skill(
        self: AgentBase,
        skill_name: str,
        context: dict[str, Any] | None = None,
    ) -> ExecutionTrace:
        """
        Execute a skill by name.

        Args:
            skill_name: Name of the skill
            context: Context data for the skill

        Returns:
            Execution trace
        """
        return await self.skills.execute(skill_name, context or {})

    async def list_skills(self: AgentBase) -> list[str]:
        """List available skills."""
        skills_dir = self.skills.skills_dir
        skill_names = []

        for skill_file in skills_dir.rglob("SKILL.md"):
            # Extract skill name from path
            rel_path = skill_file.relative_to(skills_dir)
            skill_name = str(rel_path.parent)
            skill_names.append(skill_name)

        return sorted(skill_names)
