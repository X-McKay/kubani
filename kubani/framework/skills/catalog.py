"""Skill catalog for progressive disclosure.

Generates an XML catalog of skill metadata for system prompt injection,
and provides loading functions for filesystem and OCI sources.

Two sources:
- Filesystem: scans kubani/skills/ for SKILL.md files (development)
- OCI: queries SkillLoader for published skills (production)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def build_catalog_xml(
    skills: list[dict],
    denied: list[str] | None = None,
) -> str:
    """Build XML skill catalog for system prompt injection.

    Args:
        skills: List of dicts with at minimum 'name' and 'description' keys.
        denied: Optional glob patterns for skills to exclude from the catalog.

    Returns:
        XML string suitable for embedding in a system prompt. Example::

            <available_skills>
              <skill name="check-pods">Check pod health status</skill>
            </available_skills>
    """
    from fnmatch import fnmatch

    denied = denied or []
    lines = ["<available_skills>"]

    for skill in skills:
        name = skill["name"]
        if any(fnmatch(name, p) for p in denied):
            continue
        # Collapse newlines, truncate to 120 chars
        desc = skill.get("description", "").strip().replace("\n", " ")[:120]
        lines.append(f'  <skill name="{name}">{desc}</skill>')

    lines.append("</available_skills>")
    return "\n".join(lines)


def load_skills_from_filesystem(skills_root: Path) -> list[dict]:
    """Scan a directory tree for SKILL.md files and extract metadata.

    Each SKILL.md must start with YAML frontmatter delimited by ``---``.
    Files without frontmatter or with malformed YAML are silently skipped.

    Args:
        skills_root: Root directory to scan recursively.

    Returns:
        Sorted list of dicts with keys: name, description, path.
        Empty list if directory doesn't exist or contains no valid skills.
    """
    if not skills_root.exists():
        return []

    skills: list[dict] = []

    for skill_md in sorted(skills_root.rglob("SKILL.md")):
        try:
            content = skill_md.read_text()
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            meta = yaml.safe_load(parts[1]) or {}
            skills.append(
                {
                    "name": meta.get("name", skill_md.parent.name),
                    "description": meta.get("description", ""),
                    "path": str(skill_md.parent),
                    "metadata": meta.get("metadata", {}),
                }
            )
        except Exception:
            logger.warning("Failed to parse %s", skill_md, exc_info=True)
            continue

    logger.info("Loaded %d skills from filesystem: %s", len(skills), skills_root)
    return skills


async def load_skills_from_oci() -> list[dict]:
    """Load skill summaries from the OCI registry via SkillLoader.

    Uses the existing ``SkillLoader.list_available_skills()`` which queries
    the Registry API for skills with PRODUCTION status. Each returned dict
    has at minimum 'name' and 'description' keys.

    Returns:
        List of skill summary dicts. Empty list on error.
    """
    from kubani.framework.registry.skill_loader import get_skill_loader

    loader = get_skill_loader()
    try:
        available = await loader.list_available_skills()
        return [
            {
                "name": s["name"],
                "description": s.get("description", ""),
                "oci_id": s.get("id"),
            }
            for s in available
        ]
    except Exception:
        logger.exception("Failed to list skills from OCI registry")
        return []


def find_skills_root() -> Path:
    """Locate the kubani/skills/ directory.

    Resolution order:
    1. SKILLS_PATH environment variable (if set)
    2. Walk up from this file to find pyproject.toml, then kubani/skills/
    3. Fallback to relative path ``kubani/skills``

    Returns:
        Path to the skills root directory.
    """
    env_path = os.environ.get("SKILLS_PATH")
    if env_path:
        return Path(env_path)

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            skills_path = parent / "kubani" / "skills"
            if skills_path.exists():
                return skills_path

    return Path("kubani/skills")
