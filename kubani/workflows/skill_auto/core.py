"""Pure functions for the Skill Auto workflow.

This module contains all business logic with NO I/O dependencies.
Every function here can be tested instantly without any mocking.
"""

import json
import re
from typing import Any

import yaml

from .models import EvalMetrics, IterationResult, OverlapResult

# =============================================================================
# JSON Extraction
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


# =============================================================================
# LLM Output Cleaning
# =============================================================================


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
# Scoring and Analysis
# =============================================================================

# Constants for score calculation
ACCURACY_WEIGHT = 0.7
LATENCY_WEIGHT = 0.3
LATENCY_BASELINE_MS = 3000.0  # Normalize latency against this baseline
PLATEAU_THRESHOLD = 0.02  # 2% improvement threshold
PLATEAU_WINDOW = 2  # Check last N iterations
REGRESSION_THRESHOLD = 0.20  # 20% drop triggers regression


def compute_score(metrics: EvalMetrics) -> float:
    """
    Compute composite score from metrics.

    Score = accuracy * 0.7 + normalized_latency_score * 0.3

    Where normalized_latency_score = baseline / actual (capped at 1.0)
    Faster execution gets higher latency score.

    Args:
        metrics: Evaluation metrics

    Returns:
        Composite score between 0.0 and 1.0
    """
    # Accuracy component (0.0 - 1.0)
    accuracy_score = metrics.accuracy * ACCURACY_WEIGHT

    # Latency component - faster is better
    # Cap at 1.0 (can't score higher than baseline)
    latency_ratio = min(LATENCY_BASELINE_MS / max(metrics.latency_ms, 1.0), 1.0)
    latency_score = latency_ratio * LATENCY_WEIGHT

    return accuracy_score + latency_score


def is_plateau(
    history: list[IterationResult],
    window: int = PLATEAU_WINDOW,
    threshold: float = PLATEAU_THRESHOLD,
) -> bool:
    """
    Detect if improvement has plateaued.

    Returns True if score improvement is < threshold for the last `window` iterations.

    Args:
        history: List of iteration results
        window: Number of recent iterations to check
        threshold: Minimum improvement percentage to not be considered plateau

    Returns:
        True if plateaued, False otherwise
    """
    if len(history) < window + 1:
        return False

    recent = history[-(window + 1) :]

    for i in range(1, len(recent)):
        prev_score = recent[i - 1].score
        curr_score = recent[i].score

        if prev_score > 0:
            improvement = (curr_score - prev_score) / prev_score
            if improvement >= threshold:
                return False  # Found significant improvement

    return True  # All recent improvements below threshold


def detect_regression(
    history: list[IterationResult],
    current_score: float,
    threshold: float = REGRESSION_THRESHOLD,
) -> dict[str, Any]:
    """
    Detect if current score represents a significant regression.

    A regression is detected when the current score drops more than
    threshold (default 20%) below the best historical score.

    Args:
        history: List of previous iteration results
        current_score: Score from the current iteration
        threshold: Percentage drop that triggers regression (0.0-1.0)

    Returns:
        Dict with:
            - is_regression: bool
            - drop_percentage: float (how much score dropped)
            - best_score: float (best score from history)
            - best_iteration: int (which iteration had best score)
    """
    if not history:
        return {
            "is_regression": False,
            "drop_percentage": 0.0,
            "best_score": current_score,
            "best_iteration": 0,
        }

    # Find best score in history
    best_result = max(history, key=lambda r: r.score)
    best_score = best_result.score
    best_iteration = best_result.iteration

    if best_score <= 0:
        return {
            "is_regression": False,
            "drop_percentage": 0.0,
            "best_score": best_score,
            "best_iteration": best_iteration,
        }

    # Calculate drop percentage
    drop = (best_score - current_score) / best_score
    drop_percentage = drop * 100

    return {
        "is_regression": drop > threshold,
        "drop_percentage": drop_percentage,
        "best_score": best_score,
        "best_iteration": best_iteration,
    }


# =============================================================================
# Skill Name and Metadata
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
# Validation
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
# Overlap Detection Result Helpers
# =============================================================================


def create_no_overlap_result(reason: str = "No existing skills to compare") -> OverlapResult:
    """Create an OverlapResult indicating no overlap."""
    return OverlapResult(
        has_overlap=False,
        confidence=1.0,
        overlapping_skills=[],
        reasoning=reason,
        recommendation="proceed",
    )


def parse_overlap_response(response: str) -> OverlapResult:
    """
    Parse LLM response into OverlapResult.

    Args:
        response: LLM response text containing JSON

    Returns:
        OverlapResult parsed from response
    """
    try:
        data = extract_json(response)
        return OverlapResult(
            has_overlap=data.get("has_overlap", False),
            confidence=data.get("confidence", 0.5),
            overlapping_skills=data.get("overlapping_skills", []),
            reasoning=data.get("reasoning", ""),
            recommendation=data.get("recommendation", "proceed"),
        )
    except (ValueError, KeyError):
        return OverlapResult(
            has_overlap=False,
            confidence=0.0,
            overlapping_skills=[],
            reasoning="Failed to parse overlap response",
            recommendation="proceed",
        )
