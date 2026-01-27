"""Shared utility functions for the Skill Auto workflow.

This module contains skill-specific pure functions for:
- SKILL.md parsing and formatting
- Test case validation
- Skill file operations
- Backup management

Common utilities (DefaultFileSystem, LLM parsing, iteration persistence)
are imported from kubani.framework.utils.
"""

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

import yaml

# Re-export common utilities from framework for backwards compatibility
from kubani.framework.utils import (
    DefaultFileSystem,
    clean_llm_output,
    clean_markdown_output,
    clean_yaml_output,
    extract_json,
    load_iteration_history,
    save_iteration_result,
)

if TYPE_CHECKING:
    from kubani.framework.protocols import FileSystemProtocol

logger = logging.getLogger(__name__)


# =============================================================================
# Skill File Operations
# =============================================================================


def write_skill_files(
    fs: "FileSystemProtocol",
    spec: dict[str, Any],
    test_cases: str,
    output_dir: str,
) -> dict[str, str]:
    """
    Write skill files to disk.

    Creates:
    - SKILL.md from the spec
    - test_cases.yaml with the test cases
    - metadata.json with skill metadata

    Args:
        fs: File system for operations
        spec: Skill specification dict
        test_cases: Test cases YAML content
        output_dir: Directory to write to

    Returns:
        Dict with path, content, and test_cases
    """
    skill_name = spec.get("name", "unnamed-skill")
    skill_dir = f"{output_dir}/{skill_name}"

    # Ensure directory exists
    fs.mkdir(skill_dir)

    # Generate and write SKILL.md
    skill_content = format_skill_content(spec)
    skill_path = f"{skill_dir}/SKILL.md"
    fs.write(skill_path, skill_content)

    # Write test_cases.yaml
    test_path = f"{skill_dir}/test_cases.yaml"
    fs.write(test_path, test_cases)

    # Write metadata.json
    metadata = {
        "name": skill_name,
        "version": spec.get("version", "0.1.0"),
        "description": spec.get("description", ""),
        "status": "development",
        "created_at": datetime.now().isoformat(),
    }
    metadata_path = f"{skill_dir}/metadata.json"
    fs.write(metadata_path, json.dumps(metadata, indent=2))

    return {
        "path": skill_dir,
        "content": skill_content,
        "test_cases": test_cases,
    }


def create_backup(
    fs: "FileSystemProtocol",
    file_path: str,
    max_backups: int = 3,
) -> str | None:
    """
    Create a backup of a file before modification.

    Creates backup files with .bak.N suffix (e.g., SKILL.md.bak.1).
    Rotates backups when max_backups is reached.

    Args:
        fs: File system for operations
        file_path: Path to file to backup
        max_backups: Maximum number of backups to keep

    Returns:
        Path to the backup file, or None if backup failed
    """
    if not fs.exists(file_path):
        return None

    # Find the next backup number
    backup_num = 1
    while backup_num <= max_backups:
        backup_path = f"{file_path}.bak.{backup_num}"
        if not fs.exists(backup_path):
            break
        backup_num += 1

    # If we've reached max, rotate: delete oldest, shift others down
    if backup_num > max_backups:
        # Delete the oldest backup
        oldest = f"{file_path}.bak.1"
        if fs.exists(oldest):
            fs.delete(oldest)

        # Shift remaining backups down
        for i in range(2, max_backups + 1):
            old_path = f"{file_path}.bak.{i}"
            new_path = f"{file_path}.bak.{i - 1}"
            if fs.exists(old_path):
                fs.move(old_path, new_path)

        backup_num = max_backups

    # Create the backup
    backup_path = f"{file_path}.bak.{backup_num}"
    try:
        content = fs.read(file_path)
        fs.write(backup_path, content)
        return backup_path
    except Exception as e:
        logger.warning(f"Failed to create backup of {file_path}: {e}")
        return None


# =============================================================================
# SKILL.md Parsing and Formatting
# =============================================================================


def infer_skill_name(description: str) -> str:
    """
    Infer a kebab-case skill name from description.

    Takes first few words, filters to alphanumeric, joins with hyphens.

    Args:
        description: Natural language skill description

    Returns:
        Kebab-case skill name (max 30 chars)
    """
    words = description.lower().split()[:4]
    name = "-".join(w for w in words if w.isalnum())
    return name[:30]


def parse_skill_frontmatter(content: str) -> dict[str, Any]:
    """
    Extract YAML frontmatter from SKILL.md content.

    Args:
        content: SKILL.md file content

    Returns:
        Parsed frontmatter dict, or empty dict if not found
    """
    if not content.startswith("---"):
        return {}

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}

    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def format_skill_content(spec: dict[str, Any]) -> str:
    """
    Generate SKILL.md content from a skill specification.

    Args:
        spec: Skill specification dict with name, description, inputs, outputs, steps, etc.

    Returns:
        Formatted SKILL.md content
    """
    skill_name = spec.get("name", "unnamed-skill")

    # Build frontmatter
    frontmatter = {
        "name": skill_name,
        "description": spec.get("description", ""),
        "version": "0.1.0",
        "category": "_development",
        "triggers": spec.get("triggers", []),
    }

    # Format steps
    steps = spec.get("steps", [])
    steps_text = "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))

    # Format error handling
    error_handling = spec.get("error_handling", ["Handle errors gracefully"])
    error_text = "\n".join(f"- {e}" for e in error_handling)

    # Format inputs
    inputs_text = _format_params(spec.get("inputs", {}))

    # Format outputs
    outputs_text = _format_params(spec.get("outputs", {}))

    return f"""---
{yaml.dump(frontmatter, default_flow_style=False).strip()}
---

# {skill_name.replace("-", " ").title()}

{spec.get("description", "")}

## Inputs

{inputs_text}

## Outputs

{outputs_text}

## Steps

{steps_text}

## Error Handling

{error_text}
"""


def _format_params(params: dict[str, Any]) -> str:
    """Format input/output parameters as markdown."""
    if not params:
        return "None"

    lines = []
    for name, info in params.items():
        if isinstance(info, dict):
            type_str = info.get("type", "any")
            desc = info.get("description", "")
            required = " (required)" if info.get("required") else ""
            lines.append(f"- **{name}** ({type_str}){required}: {desc}")
        else:
            lines.append(f"- **{name}**: {info}")

    return "\n".join(lines)


# =============================================================================
# Test Case Validation
# =============================================================================


def validate_test_case_yaml(yaml_str: str) -> tuple[bool, str | None]:
    """
    Validate test cases YAML structure.

    Checks:
    - Valid YAML syntax
    - Has 'test_cases' key
    - Each test case has 'name' field

    Args:
        yaml_str: YAML content to validate

    Returns:
        Tuple of (is_valid, error_message or None)
    """
    try:
        data = yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        return False, f"Invalid YAML syntax: {e}"

    if data is None:
        return False, "Empty YAML content"

    if not isinstance(data, dict):
        return False, "YAML must be a dict with 'test_cases' key"

    test_cases = data.get("test_cases")
    if test_cases is None:
        return False, "Missing 'test_cases' key"

    if not isinstance(test_cases, list):
        return False, "'test_cases' must be a list"

    for i, tc in enumerate(test_cases):
        if not isinstance(tc, dict):
            return False, f"Test case {i} must be a dict"
        if "name" not in tc:
            return False, f"Test case {i} missing 'name' field"

    return True, None


def ensure_test_cases_structure(yaml_str: str) -> str:
    """
    Ensure YAML has proper test_cases structure.

    If the YAML is a list, wraps it in a test_cases key.

    Args:
        yaml_str: YAML content

    Returns:
        YAML with proper structure
    """
    try:
        data = yaml.safe_load(yaml_str)
        if isinstance(data, list):
            return yaml.dump({"test_cases": data}, default_flow_style=False)
        return yaml_str
    except yaml.YAMLError:
        return yaml_str


__all__ = [
    # Re-exported from framework
    "DefaultFileSystem",
    "extract_json",
    "clean_yaml_output",
    "clean_markdown_output",
    "clean_llm_output",
    "save_iteration_result",
    "load_iteration_history",
    # Skill-specific operations
    "write_skill_files",
    "create_backup",
    # SKILL.md Parsing
    "infer_skill_name",
    "parse_skill_frontmatter",
    "format_skill_content",
    # Test Case Validation
    "validate_test_case_yaml",
    "ensure_test_cases_structure",
]
