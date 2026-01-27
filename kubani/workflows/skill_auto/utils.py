"""Shared utility functions for the Skill Auto workflow.

This module contains pure functions for:
- LLM output cleaning (JSON, YAML, Markdown)
- SKILL.md parsing and formatting
- Test case validation
- Iteration persistence
- File system operations
"""

import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from .protocols import FileSystem

logger = logging.getLogger(__name__)


# =============================================================================
# File System Implementation
# =============================================================================


class DefaultFileSystem:
    """Default filesystem implementation using standard library.

    Provides a concrete implementation of the FileSystem protocol
    for use in production code.
    """

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
        """Create directory and parents."""
        Path(path).mkdir(parents=True, exist_ok=True)

    def list_files(self, path: str, pattern: str) -> list[str]:
        """List files matching glob pattern in path."""
        p = Path(path)
        if not p.exists():
            return []
        return [str(f) for f in p.glob(pattern)]

    def copy(self, src: str, dst: str) -> None:
        """Copy file from src to dst."""
        shutil.copy2(src, dst)

    def move(self, src: str, dst: str) -> None:
        """Move file or directory from src to dst."""
        shutil.move(src, dst)

    def list_dir(self, path: str) -> list[str]:
        """List directory contents."""
        p = Path(path)
        if not p.exists():
            return []
        return [f.name for f in p.iterdir()]

    def delete(self, path: str) -> None:
        """Delete file or directory."""
        p = Path(path)
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()


# =============================================================================
# Skill File Operations
# =============================================================================


def write_skill_files(
    fs: "FileSystem",
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
    fs: "FileSystem",
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
# LLM Output Cleaning
# =============================================================================


def extract_json(text: str) -> dict[str, Any]:
    """
    Extract the first complete JSON object from text.

    Handles:
    - Markdown code blocks (```json ... ```)
    - Surrounding text before/after JSON
    - Nested braces
    - Multiple JSON objects (takes first)

    Args:
        text: Text potentially containing JSON

    Returns:
        Parsed JSON as dict

    Raises:
        ValueError: If no valid JSON object found
    """
    # First, try to extract from markdown code block
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if code_block_match:
        text = code_block_match.group(1).strip()

    # Find the first '{' character
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in text: {text[:200]}")

    # Use brace counting to find the matching '}'
    depth = 0
    in_string = False
    escape_next = False
    end = -1

    for i, char in enumerate(text[start:], start=start):
        if escape_next:
            escape_next = False
            continue

        if char == "\\":
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        raise ValueError(f"Unbalanced braces in JSON: {text[:200]}")

    json_str = text[start:end]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Try to fix common LLM issues: single quotes instead of double quotes
        # Convert Python dict syntax to JSON
        try:
            import ast

            # ast.literal_eval can parse Python dict syntax with single quotes
            result = ast.literal_eval(json_str)
            if isinstance(result, dict):
                return result
        except (ValueError, SyntaxError):
            pass

        # Try replacing single quotes with double quotes (simple cases)
        try:
            fixed = json_str.replace("'", '"')
            return json.loads(fixed)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}. Text: {json_str[:200]}") from e


def clean_yaml_output(content: str) -> str:
    """
    Clean YAML output by removing code blocks and thinking tags.

    Args:
        content: Raw LLM output containing YAML

    Returns:
        Cleaned YAML content
    """
    # Remove thinking tags
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content = content.strip()

    # Remove code blocks
    if content.startswith("```yaml"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]

    if content.endswith("```"):
        content = content[:-3]

    return content.strip()


def clean_markdown_output(content: str) -> str:
    """
    Clean markdown output by removing code blocks and thinking tags.

    Args:
        content: Raw LLM output containing Markdown

    Returns:
        Cleaned Markdown content
    """
    # Remove thinking tags
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content = content.strip()

    if content.startswith("```markdown"):
        content = content.split("```markdown", 1)[1]
        if "```" in content:
            content = content.rsplit("```", 1)[0]
    elif content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

    return content.strip()


def clean_llm_output(content: str) -> str:
    """
    Clean LLM output by removing thinking tags and code block markers.

    Args:
        content: Raw LLM output

    Returns:
        Cleaned content
    """
    content = content.strip()

    # Remove LLM thinking tags if present (e.g., <think>...</think>)
    content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)

    # Remove code block markers if present
    if content.startswith("```"):
        lines = content.split("\n")
        # Skip first line (```yaml or ```) and last line if it's closing ```
        if lines[-1].strip().startswith("```"):
            content = "\n".join(lines[1:-1])
        else:
            content = "\n".join(lines[1:])

    return content.strip()


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


# =============================================================================
# Iteration Persistence
# =============================================================================


def save_iteration_result(
    fs: "FileSystem",
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
        fs: File system for operations
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
    fs: "FileSystem",
    skill_path: str,
) -> list[dict[str, Any]]:
    """
    Load all iteration history files from a skill directory.

    Args:
        fs: File system for operations
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


__all__ = [
    # File System
    "DefaultFileSystem",
    # Skill File Operations
    "write_skill_files",
    "create_backup",
    # LLM Output Cleaning
    "extract_json",
    "clean_yaml_output",
    "clean_markdown_output",
    "clean_llm_output",
    # SKILL.md Parsing
    "infer_skill_name",
    "parse_skill_frontmatter",
    "format_skill_content",
    # Test Case Validation
    "validate_test_case_yaml",
    "ensure_test_cases_structure",
    # Iteration Persistence
    "save_iteration_result",
    "load_iteration_history",
]
