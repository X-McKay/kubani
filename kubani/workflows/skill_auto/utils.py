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
import re
from datetime import datetime
from pathlib import Path
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


def format_skill_content(
    spec: dict[str, Any],
    domain: str = "general",
    category: str = "_development",
) -> str:
    """
    Generate Agent Skills standard-compliant SKILL.md content.

    Creates a SKILL.md that follows the Agent Skills standard with Kubani extensions:
    - Required fields: name, description, license, compatibility
    - metadata.kubani: domain, category, version, confidence, requires_approval, mcp_servers

    Args:
        spec: Skill specification dict with name, description, inputs, outputs, steps, etc.
        domain: Skill domain (e.g., "news", "k8s", "general")
        category: Skill category within domain (e.g., "collection", "analysis")

    Returns:
        Formatted SKILL.md content
    """
    skill_name = spec.get("name", "unnamed-skill")

    # Build Agent Skills standard-compliant frontmatter
    frontmatter = {
        "name": skill_name,
        "description": spec.get("description", ""),
        "license": "MIT",
        "compatibility": spec.get("compatibility", "No special dependencies"),
        "metadata": {
            "kubani": {
                "domain": domain,
                "category": category,
                "version": spec.get("version", "0.1.0"),
                "confidence": spec.get("confidence", 0.5),  # Start low, increase with iterations
                "requires_approval": spec.get("requires_approval", False),
                "mcp_servers": spec.get("mcp_servers", []),
            }
        },
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

    # Format examples if provided
    examples = spec.get("examples", [])
    examples_text = ""
    if examples:
        examples_text = "\n## Examples\n\n"
        for i, ex in enumerate(examples, 1):
            examples_text += f"### Example {i}\n\n"
            if isinstance(ex, dict):
                if ex.get("input"):
                    examples_text += f"**Input:**\n```\n{ex['input']}\n```\n\n"
                if ex.get("expected_output"):
                    examples_text += f"**Expected Output:**\n```\n{ex['expected_output']}\n```\n\n"
            else:
                examples_text += f"{ex}\n\n"

    return f"""---
{yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).strip()}
---

# {skill_name.replace("-", " ").title()}

{spec.get("description", "")}

## When to Use

Use this skill when you need to:
- {spec.get("primary_use_case", "Perform the primary task described above")}

## Prerequisites

**Required dependencies:**
- {spec.get("compatibility", "No special dependencies")}

## Inputs

{inputs_text}

## Outputs

{outputs_text}

## Instructions

{steps_text}

## Error Handling

{error_text}
{examples_text}
## Success Criteria

- Task completes without errors
- Output matches expected format
- All required fields are populated
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
# Agent Skills Standard Validation
# =============================================================================


def validate_agent_skills_standard(content: str) -> tuple[bool, list[str]]:
    """
    Validate SKILL.md follows Agent Skills standard format.

    Checks for:
    - Required top-level fields: name, description, license, compatibility
    - Required metadata.kubani fields: domain, category, version, confidence
    - Proper value ranges (confidence 0.0-1.0, semver version)

    Args:
        content: SKILL.md file content

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors: list[str] = []
    warnings: list[str] = []
    frontmatter = parse_skill_frontmatter(content)

    if not frontmatter:
        errors.append("No YAML frontmatter found (must start with ---)")
        return False, errors

    # Required top-level fields (Agent Skills standard)
    required_top_level = ["name", "description", "license", "compatibility"]
    for field in required_top_level:
        if field not in frontmatter:
            errors.append(f"Missing required field: {field}")

    # Validate name is kebab-case
    name = frontmatter.get("name", "")
    if name and not re.match(r"^[a-z][a-z0-9-]*[a-z0-9]$", name):
        errors.append(f"name must be kebab-case (e.g., 'fetch-rss-feeds'), got '{name}'")

    # Required metadata.kubani fields (Kubani extensions)
    metadata = frontmatter.get("metadata", {})
    kubani = metadata.get("kubani", {})

    if not kubani:
        errors.append("Missing metadata.kubani section")
    else:
        kubani_required = ["domain", "category", "version", "confidence"]
        for field in kubani_required:
            if field not in kubani:
                errors.append(f"Missing metadata.kubani.{field}")

        # Validate confidence is 0.0-1.0
        confidence = kubani.get("confidence")
        if confidence is not None:
            try:
                conf_val = float(confidence)
                if not (0.0 <= conf_val <= 1.0):
                    errors.append(f"metadata.kubani.confidence must be 0.0-1.0, got {confidence}")
            except (TypeError, ValueError):
                errors.append(f"metadata.kubani.confidence must be a number, got {type(confidence).__name__}")

        # Validate version is semver
        version = kubani.get("version", "")
        if version and not re.match(r"^\d+\.\d+\.\d+$", str(version)):
            errors.append(f"metadata.kubani.version must be semver (e.g., '1.0.0'), got '{version}'")

        # Validate domain is known (warning only)
        known_domains = ["general", "news", "k8s", "security", "diagnostics", "monitoring"]
        domain = kubani.get("domain", "")
        if domain and domain not in known_domains:
            warnings.append(f"metadata.kubani.domain '{domain}' is not a known domain: {known_domains}")

    return len(errors) == 0, errors


def validate_skill_directory(skill_path: str | Path) -> tuple[bool, list[str], list[str]]:
    """
    Validate a complete skill directory.

    Checks:
    - SKILL.md exists and follows Agent Skills standard
    - Test cases exist (test_cases.yaml or test.yaml)
    - Progressive disclosure readiness (metadata vs content separation)

    Args:
        skill_path: Path to skill directory

    Returns:
        Tuple of (is_valid, errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []
    skill_dir = Path(skill_path)

    if not skill_dir.is_dir():
        errors.append(f"Not a directory: {skill_path}")
        return False, errors, warnings

    # Check SKILL.md exists
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        errors.append("Missing SKILL.md")
        return False, errors, warnings

    # Validate SKILL.md content
    content = skill_file.read_text()
    is_valid, content_errors = validate_agent_skills_standard(content)
    errors.extend(content_errors)

    # Check for test cases
    test_files = ["test_cases.yaml", "test.yaml", "tests.yaml"]
    has_tests = any((skill_dir / tf).exists() for tf in test_files)
    if not has_tests:
        warnings.append("No test cases found (expected test_cases.yaml)")

    # Check for progressive disclosure readiness
    # SKILL.md should have clear sections for metadata-only summary
    if "## When to Use" not in content and "## Purpose" not in content:
        warnings.append("Missing 'When to Use' or 'Purpose' section for progressive disclosure")

    return len(errors) == 0, errors, warnings


def assess_test_coverage(
    skill_path: str | Path,
) -> dict[str, Any]:
    """
    Assess test case coverage for a skill.

    Analyzes test cases against skill inputs/outputs to determine coverage.

    Args:
        skill_path: Path to skill directory

    Returns:
        Dict with coverage metrics: test_count, coverage_pct, warnings
    """
    skill_dir = Path(skill_path)
    result = {
        "test_count": 0,
        "assertions_count": 0,
        "coverage_pct": 0.0,
        "has_edge_cases": False,
        "has_error_cases": False,
        "warnings": [],
    }

    # Find test file
    test_files = ["test_cases.yaml", "test.yaml", "tests.yaml"]
    test_file = None
    for tf in test_files:
        path = skill_dir / tf
        if path.exists():
            test_file = path
            break

    if not test_file:
        result["warnings"].append("No test cases file found")
        return result

    try:
        test_data = yaml.safe_load(test_file.read_text())
        test_cases = test_data.get("test_cases", []) if isinstance(test_data, dict) else []

        result["test_count"] = len(test_cases)

        # Count assertions
        for tc in test_cases:
            assertions = tc.get("assertions", [])
            result["assertions_count"] += len(assertions)

            # Check for edge/error cases by name
            name = tc.get("name", "").lower()
            if any(kw in name for kw in ["edge", "boundary", "limit", "empty", "null"]):
                result["has_edge_cases"] = True
            if any(kw in name for kw in ["error", "invalid", "fail", "malformed"]):
                result["has_error_cases"] = True

        # Calculate coverage percentage based on test count
        # Minimum 5 tests recommended, 10+ for good coverage
        if result["test_count"] >= 10:
            result["coverage_pct"] = 1.0
        elif result["test_count"] >= 5:
            result["coverage_pct"] = 0.7
        elif result["test_count"] >= 3:
            result["coverage_pct"] = 0.5
        else:
            result["coverage_pct"] = result["test_count"] * 0.15

        # Warnings
        if result["test_count"] < 3:
            result["warnings"].append(f"Only {result['test_count']} tests, recommend at least 5")
        if not result["has_edge_cases"]:
            result["warnings"].append("No edge case tests detected")
        if not result["has_error_cases"]:
            result["warnings"].append("No error handling tests detected")

    except yaml.YAMLError as e:
        result["warnings"].append(f"Failed to parse test file: {e}")

    return result


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
    # Agent Skills Standard Validation
    "validate_agent_skills_standard",
    "validate_skill_directory",
    "assess_test_coverage",
]
