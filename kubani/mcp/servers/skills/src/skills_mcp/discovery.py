"""
Skill discovery module.

Discovers skills from the filesystem by scanning for SKILL.md files
and parsing their frontmatter.
"""

import fnmatch
import logging
from pathlib import Path

import frontmatter

from skills_mcp.models import SkillInfo, SkillMetadata

logger = logging.getLogger(__name__)


class SkillDiscovery:
    """
    Discovers and indexes skills from the filesystem.

    Skills are expected to follow the AgentSkills.io directory structure:
        domain/category/skill-name/SKILL.md

    Example:
        k8s/diagnostic/check-pod-health/SKILL.md
    """

    def __init__(self, skills_path: str | Path):
        """
        Initialize skill discovery.

        Args:
            skills_path: Root path to the skills directory
        """
        self.skills_path = Path(skills_path).resolve()
        self._skills_cache: dict[str, SkillInfo] | None = None

    def discover_all(self, force_refresh: bool = False) -> list[SkillInfo]:
        """
        Discover all skills from the filesystem.

        Args:
            force_refresh: Force re-scan even if cached

        Returns:
            List of discovered skills
        """
        if self._skills_cache is not None and not force_refresh:
            return list(self._skills_cache.values())

        skills = {}

        if not self.skills_path.exists():
            logger.warning(f"Skills path does not exist: {self.skills_path}")
            return []

        # Find all SKILL.md files
        for skill_md in self.skills_path.rglob("SKILL.md"):
            try:
                skill = self._parse_skill(skill_md)
                if skill:
                    skills[skill.path] = skill
                    logger.debug(f"Discovered skill: {skill.path}")
            except Exception as e:
                logger.error(f"Failed to parse {skill_md}: {e}")

        self._skills_cache = skills
        logger.info(f"Discovered {len(skills)} skills from {self.skills_path}")
        return list(skills.values())

    def get_skill(self, skill_path: str) -> SkillInfo | None:
        """
        Get a specific skill by path.

        Args:
            skill_path: Skill path (e.g., "k8s/diagnostic/check-pod-health")

        Returns:
            SkillInfo if found, None otherwise
        """
        if self._skills_cache is None:
            self.discover_all()

        return self._skills_cache.get(skill_path) if self._skills_cache else None

    def filter_skills(
        self,
        skills: list[SkillInfo] | None = None,
        domain: str | None = None,
        category: str | None = None,
        allowed: list[str] | None = None,
        denied: list[str] | None = None,
    ) -> list[SkillInfo]:
        """
        Filter skills based on criteria.

        Args:
            skills: Skills to filter (defaults to all discovered)
            domain: Filter by domain (e.g., "k8s")
            category: Filter by category (e.g., "diagnostic")
            allowed: Glob patterns for allowed skills
            denied: Glob patterns for denied skills

        Returns:
            Filtered list of skills
        """
        if skills is None:
            skills = self.discover_all()

        filtered = []

        for skill in skills:
            # Skip development skills by default
            if skill.path.startswith("_"):
                continue

            # Filter by domain
            if domain and skill.metadata.domain != domain:
                continue

            # Filter by category
            if category and skill.metadata.category != category:
                continue

            # Check denied patterns first
            if denied:
                if any(fnmatch.fnmatch(skill.path, pattern) for pattern in denied):
                    logger.debug(f"Skill {skill.path} denied by pattern")
                    continue

            # Check allowed patterns
            if allowed:
                if not any(fnmatch.fnmatch(skill.path, pattern) for pattern in allowed):
                    logger.debug(f"Skill {skill.path} not in allowed patterns")
                    continue

            filtered.append(skill)

        return filtered

    def _parse_skill(self, skill_md_path: Path) -> SkillInfo | None:
        """
        Parse a SKILL.md file into SkillInfo.

        Args:
            skill_md_path: Path to SKILL.md file

        Returns:
            SkillInfo or None if parsing fails
        """
        skill_dir = skill_md_path.parent

        # Calculate skill path relative to skills root
        try:
            rel_path = skill_dir.relative_to(self.skills_path)
            skill_path = str(rel_path).replace("\\", "/")
        except ValueError:
            logger.error(f"Skill {skill_md_path} is not under {self.skills_path}")
            return None

        # Parse frontmatter
        try:
            post = frontmatter.load(skill_md_path)
        except Exception as e:
            logger.error(f"Failed to parse frontmatter for {skill_md_path}: {e}")
            return None

        # Extract metadata
        fm = post.metadata
        name = fm.get("name", skill_dir.name)
        version = fm.get("version", "1.0.0")
        description = fm.get("description", "")

        # Parse metadata section
        metadata_dict = fm.get("metadata", {})
        # Also check top-level for backward compatibility
        if not metadata_dict:
            metadata_dict = {
                "domain": fm.get("domain", ""),
                "category": fm.get("category", ""),
                "requires-approval": fm.get("requires-approval", False),
                "confidence": fm.get("confidence", 0.5),
                "mcp-servers": fm.get("mcp-servers"),
            }

        # Infer domain/category from path if not specified
        path_parts = skill_path.split("/")
        if len(path_parts) >= 2:
            if not metadata_dict.get("domain"):
                metadata_dict["domain"] = path_parts[0]
            if not metadata_dict.get("category") and len(path_parts) >= 2:
                metadata_dict["category"] = path_parts[1]

        try:
            metadata = SkillMetadata.model_validate(metadata_dict)
        except Exception as e:
            logger.warning(f"Invalid metadata for {skill_path}: {e}")
            metadata = SkillMetadata()

        # Find scripts
        scripts_dir = skill_dir / "scripts"
        scripts = []
        if scripts_dir.exists():
            scripts = [
                f.name
                for f in scripts_dir.iterdir()
                if f.is_file() and f.suffix in (".py", ".sh", ".bash")
            ]

        # Check for tests
        has_tests = (skill_dir / "test.yaml").exists() or (skill_dir / "tests").exists()

        return SkillInfo(
            path=skill_path,
            name=name,
            version=version,
            description=description,
            metadata=metadata,
            content=post.content,
            scripts=scripts,
            has_tests=has_tests,
            skill_dir=str(skill_dir),
        )

    def refresh(self) -> list[SkillInfo]:
        """Force refresh the skill cache."""
        return self.discover_all(force_refresh=True)


# Global discovery instance
_discovery: SkillDiscovery | None = None


def get_discovery(skills_path: str | Path | None = None) -> SkillDiscovery:
    """
    Get the global skill discovery instance.

    Args:
        skills_path: Override skills path (creates new instance if different)

    Returns:
        SkillDiscovery instance
    """
    global _discovery

    if skills_path is not None:
        skills_path = Path(skills_path).resolve()
        if _discovery is None or _discovery.skills_path != skills_path:
            _discovery = SkillDiscovery(skills_path)

    if _discovery is None:
        raise ValueError("Skills path not configured. Call get_discovery(path) first.")

    return _discovery
