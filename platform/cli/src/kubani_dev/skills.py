"""
Skills Manager for Kubani.

Provides tools for managing, validating, and searching agent skills.
"""

import logging
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SkillManager:
    """
    Manages Kubani agent skills.

    Provides functionality for:
    - Listing all skills
    - Searching skills by keyword
    - Validating skill format
    - Getting skill details
    """

    REQUIRED_SECTIONS = [
        "Name",
        "Description",
        "When to Use",
        "Prerequisites",
        "Steps",
        "Expected Outcome",
    ]

    RECOMMENDED_SECTIONS = [
        "Version",
        "Author",
        "Category",
        "Dependencies",
        "Examples",
        "Troubleshooting",
    ]

    def __init__(self, skills_path: Path):
        self.skills_path = skills_path

    def list_all(self) -> dict[str, list[str]]:
        """List all skills organized by category."""
        skills: dict[str, list[str]] = {}

        for skill_file in self.skills_path.rglob("SKILL.md"):
            category = skill_file.parent.parent.name
            skill_name = skill_file.parent.name

            if category not in skills:
                skills[category] = []
            skills[category].append(skill_name)

        return skills

    def get_skill(self, skill_path: str) -> Optional[dict[str, Any]]:
        """
        Get skill details.

        Args:
            skill_path: Path like "k8s/pod-restart" or "general/analytics/detect-metric-anomaly"
        """
        parts = skill_path.split("/")

        # Try different path combinations
        possible_paths = [
            self.skills_path / "/".join(parts) / "SKILL.md",
            self.skills_path / "general" / "/".join(parts) / "SKILL.md",
            self.skills_path / "k8s" / "/".join(parts) / "SKILL.md",
        ]

        for path in possible_paths:
            if path.exists():
                return self._parse_skill(path)

        return None

    def _parse_skill(self, skill_file: Path) -> dict[str, Any]:
        """Parse a SKILL.md file."""
        content = skill_file.read_text()

        # Extract metadata from YAML frontmatter if present
        metadata = {}
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                frontmatter = content[3:end].strip()
                for line in frontmatter.split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip().lower()] = value.strip()
                content = content[end + 3:].strip()

        # Extract sections
        sections = {}
        current_section = None
        current_content = []

        for line in content.split("\n"):
            if line.startswith("## "):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = line[3:].strip()
                current_content = []
            elif line.startswith("# "):
                # Main title
                metadata["name"] = line[2:].strip()
            else:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return {
            "name": metadata.get("name", skill_file.parent.name),
            "description": sections.get("Description", ""),
            "metadata": metadata,
            "sections": sections,
            "path": str(skill_file),
        }

    def validate_skill(self, skill_file: Path) -> list[str]:
        """
        Validate a skill file format.

        Returns list of validation errors.
        """
        errors = []

        if not skill_file.exists():
            return [f"File not found: {skill_file}"]

        content = skill_file.read_text()

        # Check for required sections
        for section in self.REQUIRED_SECTIONS:
            if f"## {section}" not in content:
                errors.append(f"Missing required section: {section}")

        # Check for recommended sections (warnings, not errors)
        for section in self.RECOMMENDED_SECTIONS:
            if f"## {section}" not in content:
                logger.debug(f"Missing recommended section: {section}")

        # Check for empty sections
        sections = re.findall(r"## ([^\n]+)\n(.*?)(?=## |\Z)", content, re.DOTALL)
        for name, body in sections:
            if not body.strip():
                errors.append(f"Empty section: {name}")

        # Check for version in metadata or content
        if "version:" not in content.lower() and "## Version" not in content:
            errors.append("Missing version information")

        return errors

    def validate_all(self) -> dict[str, list[str]]:
        """Validate all skills and return errors by path."""
        results = {}

        for skill_file in self.skills_path.rglob("SKILL.md"):
            rel_path = skill_file.relative_to(self.skills_path)
            errors = self.validate_skill(skill_file)
            results[str(rel_path)] = errors

        return results

    def search(self, keyword: str) -> list[dict[str, Any]]:
        """Search skills by keyword."""
        keyword_lower = keyword.lower()
        matches = []

        for skill_file in self.skills_path.rglob("SKILL.md"):
            content = skill_file.read_text().lower()
            if keyword_lower in content:
                skill = self._parse_skill(skill_file)
                matches.append(skill)

        return matches
