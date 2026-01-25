"""File service layer for the Skill Auto workflow.

This module encapsulates all filesystem operations, using a protocol-based
interface for easy mocking in tests.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from .core import format_skill_content, parse_skill_frontmatter

logger = logging.getLogger(__name__)


# =============================================================================
# Protocol Definition
# =============================================================================


class FileServiceProtocol(Protocol):
    """Protocol for file operations - enables easy mocking."""

    def read(self, path: str) -> str:
        """Read file content as string."""
        ...

    def write(self, path: str, content: str) -> None:
        """Write content to file."""
        ...

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        ...

    def mkdir(self, path: str) -> None:
        """Create directory (with parents)."""
        ...

    def list_files(self, path: str, pattern: str) -> list[str]:
        """List files matching glob pattern."""
        ...

    def copy(self, src: str, dst: str) -> None:
        """Copy file from src to dst."""
        ...

    def move(self, src: str, dst: str) -> None:
        """Move file/directory from src to dst."""
        ...

    def list_dir(self, path: str) -> list[str]:
        """List files in directory (just names, not full paths)."""
        ...

    def delete(self, path: str) -> None:
        """Delete a file."""
        ...


# =============================================================================
# Real Implementation
# =============================================================================


class FileService:
    """Real filesystem operations using pathlib."""

    def read(self, path: str) -> str:
        """Read file content as string."""
        return Path(path).read_text()

    def write(self, path: str, content: str) -> None:
        """Write content to file, creating parent directories if needed."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        return Path(path).exists()

    def mkdir(self, path: str) -> None:
        """Create directory with parents."""
        Path(path).mkdir(parents=True, exist_ok=True)

    def list_files(self, path: str, pattern: str) -> list[str]:
        """List files matching glob pattern."""
        return [str(p) for p in Path(path).glob(pattern)]

    def copy(self, src: str, dst: str) -> None:
        """Copy file from src to dst."""
        import shutil

        shutil.copy2(src, dst)

    def move(self, src: str, dst: str) -> None:
        """Move file/directory from src to dst."""
        import shutil

        shutil.move(src, dst)

    def list_dir(self, path: str) -> list[str]:
        """List files in directory (just names, not full paths)."""
        return [p.name for p in Path(path).iterdir()]

    def delete(self, path: str) -> None:
        """Delete a file."""
        Path(path).unlink(missing_ok=True)


# =============================================================================
# High-Level Operations
# =============================================================================


def load_existing_skills(
    fs: FileServiceProtocol,
    skills_path: str,
    include_development: bool = True,
) -> list[dict[str, Any]]:
    """
    Load metadata for all existing skills.

    Args:
        fs: File service for operations
        skills_path: Path to skills directory
        include_development: Whether to include _development skills

    Returns:
        List of skill metadata dicts with name, description, path, triggers
    """
    skills = []

    if not fs.exists(skills_path):
        return skills

    for skill_md in fs.list_files(skills_path, "**/SKILL.md"):
        # Skip _development if not included
        if not include_development and "_development" in skill_md:
            continue

        try:
            content = fs.read(skill_md)
            frontmatter = parse_skill_frontmatter(content)

            # Extract skill directory from SKILL.md path
            skill_dir = str(Path(skill_md).parent)

            skills.append(
                {
                    "name": frontmatter.get("name", Path(skill_dir).name),
                    "description": frontmatter.get("description", ""),
                    "path": skill_dir,
                    "triggers": frontmatter.get("triggers", []),
                }
            )
        except Exception as e:
            logger.warning(f"Failed to load skill {skill_md}: {e}")

    return skills


def write_skill_files(
    fs: FileServiceProtocol,
    spec: dict[str, Any],
    test_cases: str,
    output_dir: str,
) -> dict[str, str]:
    """
    Write skill files to disk.

    Creates:
    - SKILL.md with frontmatter and content
    - test_cases.yaml with test definitions
    - metadata.json with creation info

    Args:
        fs: File service for operations
        spec: Skill specification
        test_cases: Test cases YAML content
        output_dir: Directory to write to

    Returns:
        Dict with path, content, and test_cases for workflow state
    """
    from .core import infer_skill_name

    # Get skill name from spec, or infer from description
    skill_name = spec.get("name")
    if not skill_name:
        description = spec.get("description", "unnamed-skill")
        skill_name = infer_skill_name(description)
        spec["name"] = skill_name  # Update spec for content generation

    skill_dir = f"{output_dir}/{skill_name}"

    # Create directory
    fs.mkdir(skill_dir)

    # Generate SKILL.md content
    skill_content = format_skill_content(spec)
    fs.write(f"{skill_dir}/SKILL.md", skill_content)

    # Write test cases
    fs.write(f"{skill_dir}/test_cases.yaml", test_cases)

    # Write metadata
    metadata = {
        "name": skill_name,
        "version": "0.1.0",
        "status": "development",
        "created_at": datetime.now().isoformat(),
        "created_by": "auto-mode",
        "allowed_tools": ["read", "search", "web_fetch"],
    }
    fs.write(f"{skill_dir}/metadata.json", json.dumps(metadata, indent=2))

    return {
        "path": skill_dir,
        "content": skill_content,
        "test_cases": test_cases,
    }


def save_iteration_result(
    fs: FileServiceProtocol,
    skill_path: str,
    iteration: int,
    score: float,
    improved: bool,
    action: str,
    metrics: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """
    Save iteration result to a JSON file for auditing.

    Creates iteration_N.json in the skill directory.

    Args:
        fs: File service for operations
        skill_path: Path to the skill directory
        iteration: Iteration number
        score: Computed score
        improved: Whether this iteration improved
        action: Action taken
        metrics: Optional metrics dict
        error: Optional error message

    Returns:
        Dict with save status
    """
    iteration_file = f"{skill_path}/iteration_{iteration}.json"

    data = {
        "iteration": iteration,
        "score": score,
        "improved": improved,
        "action": action,
        "error": error,
        "saved_at": datetime.now().isoformat(),
    }

    if metrics:
        data["metrics"] = metrics

    fs.write(iteration_file, json.dumps(data, indent=2))

    return {
        "saved": True,
        "file": iteration_file,
    }


def load_iteration_history(
    fs: FileServiceProtocol,
    skill_path: str,
) -> list[dict[str, Any]]:
    """
    Load all iteration history files from a skill directory.

    Args:
        fs: File service for operations
        skill_path: Path to the skill directory

    Returns:
        List of iteration result dicts, sorted by iteration number
    """
    history = []

    if not fs.exists(skill_path):
        return history

    for iteration_file in fs.list_files(skill_path, "iteration_*.json"):
        try:
            content = fs.read(iteration_file)
            data = json.loads(content)
            history.append(data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to load {iteration_file}: {e}")

    # Sort by iteration number
    history.sort(key=lambda x: x.get("iteration", 0))

    return history


def create_backup(
    fs: FileServiceProtocol,
    file_path: str,
    timestamp: str | None = None,
    max_backups: int | None = None,
) -> str:
    """
    Create a timestamped backup of a file.

    Args:
        fs: File service for operations
        file_path: Path to file to backup
        timestamp: Optional timestamp string (defaults to current time)
        max_backups: Maximum number of backups to keep (None = unlimited)

    Returns:
        Path to backup file
    """
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    backup_path = f"{file_path}.backup.{timestamp}"

    if fs.exists(file_path):
        content = fs.read(file_path)
        fs.write(backup_path, content)

        # Clean up old backups if limit specified
        if max_backups is not None and max_backups > 0:
            cleanup_old_backups(fs, file_path, max_backups)

    return backup_path


def cleanup_old_backups(
    fs: FileServiceProtocol,
    file_path: str,
    max_backups: int,
) -> list[str]:
    """
    Remove old backup files, keeping only the most recent ones.

    Args:
        fs: File service for operations
        file_path: Original file path (backups are {file_path}.backup.{timestamp})
        max_backups: Maximum number of backups to keep

    Returns:
        List of deleted backup paths
    """
    import os
    import re

    deleted = []
    parent_dir = os.path.dirname(file_path) or "."
    base_name = os.path.basename(file_path)
    backup_pattern = re.compile(rf"^{re.escape(base_name)}\.backup\.(\d{{8}}_\d{{6}})$")

    # Find all backup files for this file
    backup_files = []
    if fs.exists(parent_dir):
        try:
            for f in fs.list_dir(parent_dir):
                match = backup_pattern.match(f)
                if match:
                    backup_files.append((f, match.group(1)))  # (filename, timestamp)
        except NotImplementedError:
            # FileService doesn't support list_dir - skip cleanup
            return []

    # Sort by timestamp (most recent first)
    backup_files.sort(key=lambda x: x[1], reverse=True)

    # Delete old backups beyond the limit
    for filename, _ in backup_files[max_backups:]:
        backup_path = os.path.join(parent_dir, filename)
        fs.delete(backup_path)
        deleted.append(backup_path)

    return deleted


def revert_to_version(
    fs: FileServiceProtocol,
    skill_path: str,
    content: str,
    test_cases: str,
    create_backups: bool = True,
    max_backups: int | None = None,
) -> dict[str, Any]:
    """
    Revert skill files to a previous version.

    Creates backup of current files before reverting (if enabled).

    Args:
        fs: File service for operations
        skill_path: Path to the skill directory
        content: SKILL.md content to restore
        test_cases: test_cases.yaml content to restore
        create_backups: Whether to create backups before reverting
        max_backups: Maximum number of backups to keep (None = unlimited)

    Returns:
        Dict with revert status
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Backup current files (if enabled)
    skill_md = f"{skill_path}/SKILL.md"
    test_yaml = f"{skill_path}/test_cases.yaml"

    if create_backups:
        if fs.exists(skill_md):
            create_backup(fs, skill_md, timestamp, max_backups)

        if fs.exists(test_yaml):
            create_backup(fs, test_yaml, timestamp, max_backups)

    # Write reverted content
    fs.write(skill_md, content)
    fs.write(test_yaml, test_cases)

    return {
        "reverted": True,
        "backup_timestamp": timestamp if create_backups else None,
    }


def promote_skill(
    fs: FileServiceProtocol,
    skill_path: str,
    target_category: str,
    skills_root: str,
) -> dict[str, Any]:
    """
    Promote a skill from _development to production location.

    Moves the skill directory and updates metadata.

    Args:
        fs: File service for operations
        skill_path: Path to the development skill directory
        target_category: Target category directory (e.g., "general", "k8s")
        skills_root: Root skills directory (e.g., "kubani/skills")

    Returns:
        Dict with success status and promoted_path
    """
    skill_name = Path(skill_path).name
    target_dir = f"{skills_root}/{target_category}"
    target_path = f"{target_dir}/{skill_name}"

    # Ensure target category exists
    fs.mkdir(target_dir)

    # Move skill directory
    fs.move(skill_path, target_path)

    # Update metadata
    metadata_path = f"{target_path}/metadata.json"
    if fs.exists(metadata_path):
        content = fs.read(metadata_path)
        metadata = json.loads(content)
    else:
        metadata = {}

    metadata["status"] = "production"
    metadata["promoted_at"] = datetime.now().isoformat()
    metadata["category"] = target_category

    fs.write(metadata_path, json.dumps(metadata, indent=2))

    return {
        "success": True,
        "promoted_path": target_path,
        "skill_name": skill_name,
    }
