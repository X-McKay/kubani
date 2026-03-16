"""Skill tools for the Nexus agent.

Provides ``load_skill`` — the agent calls this to load full SKILL.md
content for a skill it selected from the XML catalog in its system prompt.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from strands import tool

from kubani.framework.skills.catalog import find_skills_root

logger = logging.getLogger(__name__)


def _load_skill_impl(skill_name: str) -> str:
    """Load a skill's full SKILL.md content by name.

    Searches the filesystem skills directory first. If OCI discovery
    is enabled and the skill isn't found locally, searches the
    SkillLoader's on-disk cache (populated by OCI pulls).

    Args:
        skill_name: Skill name from the catalog (e.g. "investigate-pod-failure").

    Returns:
        Full SKILL.md content string, or an error message if not found.
    """
    # --- Filesystem search ---
    skills_root = find_skills_root()
    if skills_root.exists():
        result = _search_directory(skills_root, skill_name)
        if result is not None:
            return result

    # --- OCI cache search (only if enabled) ---
    oci_enabled = os.environ.get("OCI_DISCOVERY_ENABLED", "false").lower() == "true"
    if oci_enabled:
        result = _search_oci_cache(skill_name)
        if result is not None:
            return result

    return f"Skill '{skill_name}' not found."


def _search_directory(root: Path, skill_name: str) -> str | None:
    """Search a directory tree for a SKILL.md matching the given name."""
    for skill_md in root.rglob("SKILL.md"):
        try:
            content = skill_md.read_text()
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            meta = yaml.safe_load(parts[1]) or {}
            if meta.get("name") == skill_name:
                return content
        except Exception:
            continue
    return None


def _search_oci_cache(skill_name: str) -> str | None:
    """Search the SkillLoader's on-disk cache for a skill.

    The cache directory (default: ~/.kubani/skill-cache/) contains
    subdirectories keyed by OCI digest, each with an extracted SKILL.md.
    """
    try:
        from kubani.framework.registry.skill_loader import get_skill_loader

        loader = get_skill_loader()
        if not loader.cache_dir.exists():
            return None

        return _search_directory(loader.cache_dir, skill_name)
    except Exception:
        logger.warning("OCI cache search failed for %s", skill_name, exc_info=True)
        return None


@tool
def load_skill(skill_name: str) -> str:
    """Load full instructions for a skill by name.

    Call this when you want to activate a skill from the <available_skills>
    catalog in your system prompt. Returns the complete SKILL.md content
    including instructions, preconditions, and steps.

    After loading, follow the skill's instructions using your other tools.
    If the skill has executable scripts, use execute_skill via MCP.

    Args:
        skill_name: The skill name from the catalog (e.g. "investigate-pod-failure")
    """
    return _load_skill_impl(skill_name)
