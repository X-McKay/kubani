"""
Skills Orchestrator - Base class for skills-centric agents.

Extends KubaniAgent with skills discovery and progressive disclosure.
Agents extending this class are thin orchestrators that delegate to skills.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from kubani.framework.skills import (
    build_catalog_xml,
    find_skills_root,
    load_skills_from_filesystem,
)

from .agent import KubaniAgent

logger = logging.getLogger(__name__)


class SkillsOrchestrator(KubaniAgent):
    """
    Base class for skills-centric agents.

    Discovers skills based on domain/category filters and generates
    a skills catalog for the system prompt. Skills are loaded progressively:
    - Phase 1: Metadata only (name, description) in system prompt
    - Phase 2: Full SKILL.md content loaded on demand via load_skill tool

    Subclasses should:
    1. Set SKILLS_DOMAIN and SKILLS_CATEGORY class attributes
    2. Override _get_task_prompt() to generate task-specific prompts
    3. Implement on_skill_complete() for learning integration
    """

    # Override in subclass to filter skills
    SKILLS_DOMAIN: str | None = None
    SKILLS_CATEGORY: str | None = None
    SKILLS_ROOT: Path | None = None  # Defaults to kubani/skills

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the orchestrator with skill discovery."""
        super().__init__(agent_dir)

        # Discover skills
        self._skills: list[dict] = []
        self._discover_skills()

    def _discover_skills(self) -> None:
        """Discover skills based on domain/category filters."""
        skills_root = self.SKILLS_ROOT
        if skills_root is None:
            skills_root = find_skills_root()

        if not skills_root.exists():
            logger.warning(f"Skills root not found: {skills_root}")
            return

        all_skills = load_skills_from_filesystem(skills_root)

        # Filter by domain/category using metadata from frontmatter
        filtered = []
        for skill in all_skills:
            meta = skill.get("metadata", {})
            if self.SKILLS_DOMAIN and meta.get("domain") != self.SKILLS_DOMAIN:
                continue
            if self.SKILLS_CATEGORY and meta.get("category") != self.SKILLS_CATEGORY:
                continue
            filtered.append(skill)

        self._skills = filtered

        logger.info(
            f"Discovered {len(self._skills)} skills for {self.name} "
            f"(domain={self.SKILLS_DOMAIN}, category={self.SKILLS_CATEGORY})"
        )

    @property
    def skills(self) -> list[dict]:
        """Get discovered skills."""
        return self._skills

    def _generate_skills_prompt(self) -> str:
        """
        Generate skills catalog for system prompt (Phase 1 disclosure).

        Returns metadata-only catalog to minimize token usage.
        Full skill content is loaded on demand via load_skill tool.
        """
        if not self._skills:
            return "\n## No Skills Available\n"

        return "\n# Available Skills\n\n" + build_catalog_xml(self._skills)

    @property
    def prompt(self) -> str:
        """Get system prompt with skills catalog appended."""
        base_prompt = super().prompt
        skills_prompt = self._generate_skills_prompt()

        # Add instructions for using skills
        usage_instructions = """

## Using Skills

When you need to perform a task, check the available skills above.
To use a skill:
1. Use the load_skill tool to get full instructions
2. Follow the steps in the skill exactly
3. Report results in the format specified by the skill
"""

        return base_prompt + skills_prompt + usage_instructions

    def get_skill_path(self, skill_name: str) -> Path | None:
        """Get the path to a skill's SKILL.md file."""
        for skill in self._skills:
            if skill["name"] == skill_name:
                path = skill.get("path")
                if path:
                    return Path(path) / "SKILL.md"
        return None

    def _get_task_prompt(self, **kwargs: Any) -> str:
        """
        Generate a task-specific prompt for the agent.

        Override in subclass to create prompts for specific operations.

        Args:
            **kwargs: Task-specific parameters

        Returns:
            Prompt string for the task
        """
        return "Execute the task using available skills."

    def _extract_json(self, text: str) -> dict[str, Any] | list[Any]:
        """Extract JSON from text, handling markdown code blocks."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from code block
        match = re.search(r"```(?:json)?\n(.*?)\n```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        raise ValueError("No valid JSON found in response")
