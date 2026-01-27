"""Improve a skill based on evaluation feedback.

This module provides functions for:
- Generating improved SKILL.md content using LLM
- Reverting to a previous best version when regression detected
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..utils import clean_markdown_output

if TYPE_CHECKING:
    from ..protocols import FileSystem, LLMClient


# =============================================================================
# Prompts
# =============================================================================

SYSTEM_PROMPT = """/no_think
You are a skill improver. Improve skills based on evaluation feedback.
Return ONLY the improved SKILL.md content, no explanation or markdown code blocks."""

USER_PROMPT_TEMPLATE = """Improve this skill based on the evaluation feedback.

CURRENT SKILL:
{skill_content}

EVALUATION FEEDBACK:
{feedback}

Generate an improved version of the SKILL.md that:
1. Addresses the issues identified in the feedback
2. Improves clarity and specificity of instructions
3. Adds better error handling guidance if needed
4. Maintains the same input/output interface

Return ONLY the improved SKILL.md content, no explanation."""


# =============================================================================
# Improvement Functions
# =============================================================================


async def improve_skill(
    client: "LLMClient",
    skill_content: str,
    feedback: str,
) -> str:
    """
    Generate improved SKILL.md content based on feedback.

    Uses the LLM to analyze evaluation feedback and generate an improved
    version of the skill that addresses identified issues.

    Args:
        client: LLM client for generation
        skill_content: Current SKILL.md content
        feedback: Evaluation feedback describing issues to address

    Returns:
        Improved SKILL.md content

    Raises:
        ValueError: If LLM returns empty or invalid content
    """
    user_prompt = USER_PROMPT_TEMPLATE.format(
        skill_content=skill_content,
        feedback=feedback,
    )

    response = await client.chat(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.5,  # Slightly higher temp for creative improvement
    )

    if not response:
        raise ValueError("LLM returned empty response")

    # Clean up LLM output (remove think tags, code blocks)
    cleaned = clean_markdown_output(response)

    if not cleaned:
        raise ValueError("LLM returned empty content after cleaning")

    return cleaned


# =============================================================================
# Revert Functions
# =============================================================================


def revert_to_best_version(
    fs: "FileSystem",
    skill_path: str,
    content: str,
    test_cases: str,
    create_backups: bool = True,
    max_backups: int | None = None,
) -> dict[str, Any]:
    """
    Revert skill files to a previous best version.

    Creates backup of current files before reverting (if enabled).

    Args:
        fs: File system for operations
        skill_path: Path to the skill directory
        content: SKILL.md content to restore
        test_cases: test_cases.yaml content to restore
        create_backups: Whether to create backups before reverting
        max_backups: Maximum number of backups to keep (None = unlimited)

    Returns:
        Dict with revert status and backup info
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    skill_md = f"{skill_path}/SKILL.md"
    test_yaml = f"{skill_path}/test_cases.yaml"

    # Backup current files (if enabled)
    if create_backups:
        if fs.exists(skill_md):
            _create_backup(fs, skill_md, timestamp, max_backups)

        if fs.exists(test_yaml):
            _create_backup(fs, test_yaml, timestamp, max_backups)

    # Write reverted content
    fs.write(skill_md, content)
    fs.write(test_yaml, test_cases)

    return {
        "reverted": True,
        "backup_timestamp": timestamp if create_backups else None,
    }


# =============================================================================
# Backup Helpers
# =============================================================================


def _create_backup(
    fs: "FileSystem",
    file_path: str,
    timestamp: str,
    max_backups: int | None = None,
) -> str:
    """
    Create a timestamped backup of a file.

    Args:
        fs: File system for operations
        file_path: Path to file to backup
        timestamp: Timestamp string for backup filename
        max_backups: Maximum number of backups to keep (None = unlimited)

    Returns:
        Path to backup file
    """
    backup_path = f"{file_path}.backup.{timestamp}"

    if fs.exists(file_path):
        content = fs.read(file_path)
        fs.write(backup_path, content)

        # Clean up old backups if limit specified
        if max_backups is not None and max_backups > 0:
            _cleanup_old_backups(fs, file_path, max_backups)

    return backup_path


def _cleanup_old_backups(
    fs: "FileSystem",
    file_path: str,
    max_backups: int,
) -> list[str]:
    """
    Remove old backup files, keeping only the most recent ones.

    Args:
        fs: File system for operations
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
        except (NotImplementedError, AttributeError):
            # FileSystem doesn't support list_dir - skip cleanup
            return []

    # Sort by timestamp (most recent first)
    backup_files.sort(key=lambda x: x[1], reverse=True)

    # Delete old backups beyond the limit
    for filename, _ in backup_files[max_backups:]:
        backup_path = os.path.join(parent_dir, filename)
        fs.delete(backup_path)
        deleted.append(backup_path)

    return deleted


__all__ = [
    "improve_skill",
    "revert_to_best_version",
]
