"""Generate test cases for a skill specification.

This capability takes a skill specification and generates comprehensive
test cases in YAML format, covering happy path, edge cases, and error scenarios.
"""

from typing import Any

import yaml

from ..protocols import LLMClient
from ..utils import clean_yaml_output

# =============================================================================
# Prompts
# =============================================================================

SYSTEM_PROMPT = """/no_think
You are a test case designer. Generate comprehensive test cases for skills. Return ONLY valid YAML, no markdown code blocks."""

GENERATE_TEST_CASES_TEMPLATE = """Generate test cases for this skill specification.

SKILL: {name}
DESCRIPTION: {description}

INPUTS:
{inputs_yaml}

OUTPUTS:
{outputs_yaml}

EXAMPLES FROM SPEC:
{examples_yaml}
{seed_section}

Generate a YAML file with test_cases key containing 3-5 test cases that cover:
1. Happy path - typical successful usage
2. Edge case - boundary conditions or unusual inputs
3. Error handling - invalid inputs or failure scenarios

ASSERTION TYPES - choose the appropriate type for each field:
- type: equals - For exact matches: numbers, booleans, enum-like values (e.g., error codes, status values)
- type: contains - For checking key phrases in text outputs (preferred for descriptions, explanations, recommendations)
- type: exists - For checking that a field is present and non-empty
- type: similarity - For semantic similarity checks (threshold 0.7-0.9)

IMPORTANT: Do NOT use "equals" for free-form text outputs like descriptions, explanations, or recommendations.
LLM outputs vary in wording - use "contains" to check for key phrases instead.

The YAML must have this structure:
test_cases:
  - name: snake_case_identifier
    description: What this test validates
    inputs:
      # Input values for the test
    expected:
      # Expected output fields (can be partial)
    assertions:
      - type: contains  # or equals/exists/similarity as appropriate
        field: some_field
        value: "key phrase to check for"  # for contains
        description: Why this check matters

Return ONLY the YAML content, no markdown code blocks."""

GENERATE_HARDER_TESTS_TEMPLATE = """Generate {count} harder test cases for the skill "{skill_name}".

CURRENT TEST CASES:
{current_tests}

CURRENT PERFORMANCE:
- Accuracy: {accuracy_pct:.1f}%
- Tests passed: {tests_passed}/{tests_total}

FAILING TESTS AND REASONS:
{failures_text}

Generate {count} NEW test cases that:
1. Target the identified weaknesses and failure patterns
2. Test edge cases and boundary conditions
3. Are harder than the current tests

ASSERTION TYPES - choose appropriately:
- type: equals - For exact matches (numbers, booleans, enum values)
- type: contains - For key phrases in text (preferred for free-form text outputs)
- type: exists - For checking field presence
- type: similarity - For semantic similarity (threshold 0.7-0.9)

IMPORTANT: Do NOT use "equals" for free-form text - use "contains" with key phrases instead.

Return ONLY the YAML content for the new test cases."""


# =============================================================================
# Main Functions
# =============================================================================


async def draft_test_cases(
    client: LLMClient,
    spec: dict[str, Any],
    seed_tests: str | None = None,
) -> str:
    """
    Generate test cases YAML from skill specification.

    Uses an LLM to generate comprehensive test cases covering happy path,
    edge cases, and error scenarios.

    Args:
        client: LLM client for generation
        spec: Skill specification dict with name, description, inputs, outputs, examples
        seed_tests: Optional seed test cases to expand from

    Returns:
        YAML string containing test_cases

    Raises:
        ValueError: If the LLM response is not valid YAML
    """
    seed_section = f"\nSEED TEST CASES (expand from these):\n{seed_tests}" if seed_tests else ""

    user_prompt = GENERATE_TEST_CASES_TEMPLATE.format(
        name=spec.get("name", "unknown"),
        description=spec.get("description", ""),
        inputs_yaml=yaml.dump(spec.get("inputs", {}), default_flow_style=False),
        outputs_yaml=yaml.dump(spec.get("outputs", {}), default_flow_style=False),
        examples_yaml=yaml.dump(spec.get("examples", []), default_flow_style=False),
        seed_section=seed_section,
    )

    response = await client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=4000,
    )

    return clean_yaml_output(response)


async def generate_harder_tests(
    client: LLMClient,
    skill_name: str,
    current_tests: str,
    accuracy: float,
    tests_passed: int,
    tests_total: int,
    failing_tests: list[dict[str, str]],
    count: int = 2,
) -> str:
    """
    Generate harder test cases targeting identified weaknesses.

    Creates new test cases that focus on the patterns where the skill
    is currently failing or performing poorly.

    Args:
        client: LLM client for generation
        skill_name: Name of the skill being tested
        current_tests: Current test cases YAML
        accuracy: Current accuracy (0.0-1.0)
        tests_passed: Number of tests passed
        tests_total: Total number of tests
        failing_tests: List of dicts with 'name' and 'reason' for failures
        count: Number of new test cases to generate

    Returns:
        YAML string containing new test cases
    """
    failures_text = "\n".join(
        f"- {t['name']}: {t.get('reason', 'Unknown reason')}" for t in failing_tests
    )

    user_prompt = GENERATE_HARDER_TESTS_TEMPLATE.format(
        count=count,
        skill_name=skill_name,
        current_tests=current_tests,
        accuracy_pct=accuracy * 100,
        tests_passed=tests_passed,
        tests_total=tests_total,
        failures_text=failures_text if failures_text else "None - all tests passed",
    )

    response = await client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=4000,
    )

    return clean_yaml_output(response)


__all__ = ["draft_test_cases", "generate_harder_tests"]
