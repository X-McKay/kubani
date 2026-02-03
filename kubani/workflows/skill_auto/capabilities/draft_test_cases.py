"""Generate test cases for a skill specification.

This capability takes a skill specification and generates comprehensive
test cases in YAML format, covering happy path, edge cases, and error scenarios.

Uses Pydantic structured output to guarantee valid test case structure,
avoiding issues with LLMs generating invalid YAML syntax like Python expressions.
"""

import logging
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from ..protocols import LLMClient
from ..utils import clean_yaml_output

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models for Structured Output
# =============================================================================


class TestAssertion(BaseModel):
    """A single assertion to verify test output."""

    type: Literal["equals", "contains", "exists", "similarity"] = Field(
        description="Type of assertion: equals for exact match, contains for substring, exists for presence, similarity for semantic"
    )
    field: str = Field(description="The output field to check")
    value: str | int | float | bool | None = Field(
        default=None, description="Expected value (for equals/contains/similarity)"
    )
    threshold: float | None = Field(
        default=None, description="Similarity threshold 0.0-1.0 (for similarity type)"
    )
    description: str = Field(description="Why this assertion matters")


class TestCase(BaseModel):
    """A single test case for a skill."""

    name: str = Field(description="Snake_case identifier for the test")
    description: str = Field(description="What this test validates")
    inputs: dict[str, Any] = Field(description="Input values for the skill")
    expected: dict[str, Any] = Field(
        default_factory=dict, description="Expected output fields (can be partial)"
    )
    assertions: list[TestAssertion] = Field(
        default_factory=list, description="Assertions to verify the output"
    )


class TestCaseList(BaseModel):
    """Collection of test cases for a skill."""

    test_cases: list[TestCase] = Field(description="List of test cases")

# =============================================================================
# Prompts
# =============================================================================

SYSTEM_PROMPT = """/no_think
You are a test case designer. Generate comprehensive test cases for skills.

CRITICAL RULES:
1. All string values must be literal text - NO programming expressions
2. For long text inputs, write realistic example text (not code to generate it)
3. Use "contains" assertions for free-form text outputs (not "equals")
4. Use "equals" only for exact matches: numbers, booleans, enum values"""

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

Generate 3-5 test cases that cover:
1. Happy path - typical successful usage
2. Edge case - boundary conditions or unusual inputs
3. Error handling - invalid inputs or failure scenarios

ASSERTION TYPES - choose the appropriate type for each field:
- equals: For exact matches (numbers, booleans, enum values, status codes)
- contains: For checking key phrases in text outputs (preferred for descriptions, explanations)
- exists: For checking that a field is present and non-empty
- similarity: For semantic similarity checks (set threshold 0.7-0.9)

IMPORTANT: For text inputs that need to be long, write realistic example text.
Do NOT use "equals" for free-form text outputs - use "contains" instead."""

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
    max_retries: int = 2,
) -> str:
    """
    Generate test cases YAML from skill specification.

    Uses Pydantic structured output to guarantee valid test case structure.
    The LLM returns structured data that is then serialized to YAML.

    Args:
        client: LLM client for generation (must support chat_structured)
        spec: Skill specification dict with name, description, inputs, outputs, examples
        seed_tests: Optional seed test cases to expand from
        max_retries: Maximum regeneration attempts on failure

    Returns:
        YAML string containing test_cases

    Raises:
        ValueError: If structured output fails after retries
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

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            # Use structured output to guarantee valid structure
            result = await client.chat_structured(
                messages,
                output_model=TestCaseList,
                temperature=0.3,
                max_tokens=4000,
            )

            # Convert Pydantic model to YAML
            # Use model_dump() for clean dict conversion, exclude None values
            data = result.model_dump(exclude_none=True)
            yaml_output = yaml.dump(data, default_flow_style=False, sort_keys=False)

            logger.info(f"Generated {len(result.test_cases)} test cases via structured output")
            return yaml_output

        except Exception as e:
            last_error = e
            logger.warning(f"Structured output attempt {attempt + 1} failed: {e}")

            if attempt < max_retries:
                # Add context about the error for retry
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"{user_prompt}\n\nPREVIOUS ERROR: {e}\nPlease generate valid test cases.",
                    },
                ]

    # If structured output fails, fall back to text generation with YAML parsing
    logger.warning("Structured output failed, falling back to text generation")
    return await _draft_test_cases_text_fallback(client, spec, seed_tests)


async def _draft_test_cases_text_fallback(
    client: LLMClient,
    spec: dict[str, Any],
    seed_tests: str | None = None,
) -> str:
    """Fallback to text-based generation if structured output fails."""
    seed_section = f"\nSEED TEST CASES (expand from these):\n{seed_tests}" if seed_tests else ""

    # Use original template with explicit YAML format instructions
    user_prompt = f"""Generate test cases for this skill specification.

SKILL: {spec.get("name", "unknown")}
DESCRIPTION: {spec.get("description", "")}

INPUTS:
{yaml.dump(spec.get("inputs", {}), default_flow_style=False)}

OUTPUTS:
{yaml.dump(spec.get("outputs", {}), default_flow_style=False)}

EXAMPLES FROM SPEC:
{yaml.dump(spec.get("examples", []), default_flow_style=False)}
{seed_section}

Generate 3-5 test cases. Return ONLY valid YAML with this structure:

test_cases:
  - name: test_name
    description: What this tests
    inputs:
      field: value
    expected:
      field: value
    assertions:
      - type: contains
        field: output_field
        value: "expected phrase"
        description: Why this matters

CRITICAL: All values must be literal text. NO programming expressions."""

    response = await client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=4000,
    )

    cleaned = clean_yaml_output(response)

    # Validate and try to parse
    try:
        parsed = yaml.safe_load(cleaned)
        if isinstance(parsed, dict) and "test_cases" in parsed:
            return cleaned
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to generate valid YAML: {e}") from e

    raise ValueError("Generated content does not contain valid test_cases structure")


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

    Uses Pydantic structured output to guarantee valid test case structure.

    Args:
        client: LLM client for generation (must support chat_structured)
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

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        # Use structured output to guarantee valid structure
        result = await client.chat_structured(
            messages,
            output_model=TestCaseList,
            temperature=0.3,
            max_tokens=4000,
        )

        # Convert Pydantic model to YAML
        data = result.model_dump(exclude_none=True)
        yaml_output = yaml.dump(data, default_flow_style=False, sort_keys=False)

        logger.info(f"Generated {len(result.test_cases)} harder test cases via structured output")
        return yaml_output

    except Exception as e:
        # Fall back to text generation
        logger.warning(f"Structured output failed for harder tests: {e}, falling back to text")
        response = await client.chat(messages, temperature=0.3, max_tokens=4000)
        return clean_yaml_output(response)


__all__ = [
    "draft_test_cases",
    "generate_harder_tests",
    # Pydantic models for structured output
    "TestAssertion",
    "TestCase",
    "TestCaseList",
]
