"""Utilities for semantic version management."""

import re
from pathlib import Path
from typing import Optional


class SemanticVersion:
    """Semantic version (major.minor.patch)."""

    def __init__(self, major: int, minor: int, patch: int):
        self.major = major
        self.minor = minor
        self.patch = patch

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __repr__(self) -> str:
        return f"SemanticVersion({self.major}, {self.minor}, {self.patch})"

    def __eq__(self, other) -> bool:
        if not isinstance(other, SemanticVersion):
            return False
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __lt__(self, other) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other) -> bool:
        return self == other or self < other

    def __gt__(self, other) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)

    def __ge__(self, other) -> bool:
        return self == other or self > other

    def bump_major(self) -> "SemanticVersion":
        """Bump major version and reset minor and patch to 0."""
        return SemanticVersion(self.major + 1, 0, 0)

    def bump_minor(self) -> "SemanticVersion":
        """Bump minor version and reset patch to 0."""
        return SemanticVersion(self.major, self.minor + 1, 0)

    def bump_patch(self) -> "SemanticVersion":
        """Bump patch version."""
        return SemanticVersion(self.major, self.minor, self.patch + 1)

    @classmethod
    def parse(cls, version_str: str) -> Optional["SemanticVersion"]:
        """
        Parse a semantic version string.

        Args:
            version_str: Version string like "1.2.3" or "v1.2.3"

        Returns:
            SemanticVersion or None if invalid
        """
        # Remove 'v' prefix if present
        version_str = version_str.lstrip("v")

        # Match semantic version pattern
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version_str)
        if not match:
            return None

        major, minor, patch = match.groups()
        return cls(int(major), int(minor), int(patch))


def get_latest_version(skill_dir: Path) -> Optional[SemanticVersion]:
    """
    Get the latest version of a skill from its production directory.

    Args:
        skill_dir: Path to the skill's production directory (e.g., skills/core/my-skill)

    Returns:
        Latest SemanticVersion or None if no versions exist
    """
    if not skill_dir.exists():
        return None

    versions = []
    for version_dir in skill_dir.iterdir():
        if version_dir.is_dir() and version_dir.name.startswith("v"):
            version = SemanticVersion.parse(version_dir.name)
            if version:
                versions.append(version)

    if not versions:
        return None

    return max(versions)


def get_next_version(skill_dir: Path, bump_type: str = "patch") -> SemanticVersion:
    """
    Get the next version for a skill.

    Args:
        skill_dir: Path to the skill's production directory
        bump_type: Type of version bump ("major", "minor", or "patch")

    Returns:
        Next SemanticVersion
    """
    latest = get_latest_version(skill_dir)

    if latest is None:
        # No existing version, start at 1.0.0
        return SemanticVersion(1, 0, 0)

    if bump_type == "major":
        return latest.bump_major()
    elif bump_type == "minor":
        return latest.bump_minor()
    else:  # patch
        return latest.bump_patch()


def format_version_dir(version: SemanticVersion) -> str:
    """
    Format a version as a directory name.

    Args:
        version: SemanticVersion to format

    Returns:
        Directory name like "v1.2.3"
    """
    return f"v{version}"


def bump_version(current_version: str, bump_type: str = "patch") -> str:
    """
    Bump a version string by the specified type.

    Args:
        current_version: Current version string like "1.2.3"
        bump_type: Type of bump ("major", "minor", or "patch")

    Returns:
        New version string
    """
    version = SemanticVersion.parse(current_version)
    if version is None:
        # If can't parse, start fresh
        return "1.0.0"

    if bump_type == "major":
        new_version = version.bump_major()
    elif bump_type == "minor":
        new_version = version.bump_minor()
    else:  # patch
        new_version = version.bump_patch()

    return str(new_version)
