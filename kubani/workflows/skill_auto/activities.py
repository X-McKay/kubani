"""Activities for the Skill Auto workflow."""

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from kubani.workflows.skill_auto.models import (
    OverlapResult,
)

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from text, handling markdown code blocks."""
    # Try to find JSON in code blocks first
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if json_match:
        text = json_match.group(1).strip()

    # Find JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return json.loads(text[start:end])

    raise ValueError(f"Could not extract JSON from: {text[:200]}")


async def detect_skill_overlap(
    description: str,
    existing_skills: list[dict[str, str]],
    llm_client: Any,
) -> OverlapResult:
    """
    Detect if a new skill overlaps with existing skills.

    Args:
        description: Description of the new skill
        existing_skills: List of existing skills with name and description
        llm_client: LLM client for analysis

    Returns:
        OverlapResult with overlap assessment
    """
    if not existing_skills:
        return OverlapResult(
            has_overlap=False,
            confidence=1.0,
            overlapping_skills=[],
            reasoning="No existing skills to compare against",
            recommendation="proceed",
        )

    # Format existing skills for prompt
    skills_text = "\n".join(
        f"- {s['name']}: {s.get('description', 'No description')}" for s in existing_skills
    )

    prompt = f"""Analyze whether this new skill overlaps with any existing skills.

NEW SKILL DESCRIPTION:
{description}

EXISTING SKILLS:
{skills_text}

Respond with a JSON object:
{{
    "has_overlap": boolean,
    "confidence": float (0.0-1.0),
    "overlapping_skills": ["skill-name", ...],
    "reasoning": "explanation of why overlap exists or not",
    "recommendation": "proceed" | "merge" | "abort"
}}

Consider skills as overlapping if they:
- Address the same problem domain
- Would be triggered by similar scenarios
- Provide redundant functionality

Recommend "merge" if the new skill could enhance an existing one.
Recommend "abort" if the new skill is essentially a duplicate.
Recommend "proceed" if the skill is sufficiently distinct."""

    response = await llm_client.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,  # Low temperature for consistent analysis
    )

    try:
        data = _extract_json(response["content"])
        return OverlapResult(
            has_overlap=data.get("has_overlap", False),
            confidence=data.get("confidence", 0.5),
            overlapping_skills=data.get("overlapping_skills", []),
            reasoning=data.get("reasoning", ""),
            recommendation=data.get("recommendation", "proceed"),
        )
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse overlap detection response: {e}")
        return OverlapResult(
            has_overlap=False,
            confidence=0.0,
            overlapping_skills=[],
            reasoning=f"Failed to analyze: {e}",
            recommendation="proceed",
        )


async def load_existing_skills(
    skills_path: Path,
    include_development: bool = True,
) -> list[dict[str, str]]:
    """
    Load metadata for all existing skills.

    Args:
        skills_path: Path to skills directory
        include_development: Whether to include _development skills

    Returns:
        List of skill metadata dicts with name, description, path
    """
    skills = []

    if not skills_path.exists():
        return skills

    for skill_md in skills_path.rglob("SKILL.md"):
        # Skip _development if not included
        if not include_development and "_development" in str(skill_md):
            continue

        try:
            content = skill_md.read_text()

            # Parse YAML frontmatter
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    skills.append(
                        {
                            "name": frontmatter.get("name", skill_md.parent.name),
                            "description": frontmatter.get("description", ""),
                            "path": str(skill_md.parent),
                            "triggers": frontmatter.get("triggers", []),
                        }
                    )
        except Exception as e:
            logger.warning(f"Failed to load skill {skill_md}: {e}")

    return skills


async def infer_skill_structure(
    description: str,
    llm_client: Any,
    context: str | None = None,
) -> dict[str, Any]:
    """
    Infer skill structure from a description.

    Uses LLM to generate a complete skill specification including
    name, inputs, outputs, steps, and example test cases.

    Args:
        description: Natural language description of the skill
        llm_client: LLM client for generation
        context: Optional additional context

    Returns:
        Skill specification dict
    """
    context_section = f"\n\nADDITIONAL CONTEXT:\n{context}" if context else ""

    prompt = f"""Generate a complete skill specification from this description.

SKILL DESCRIPTION:
{description}{context_section}

Respond with a JSON object:
{{
    "name": "kebab-case-name",
    "description": "One-line description of what the skill does",
    "inputs": {{
        "param_name": {{
            "type": "string|number|boolean|array|object",
            "description": "What this parameter is for",
            "required": true|false
        }}
    }},
    "outputs": {{
        "field_name": {{
            "type": "string|number|boolean|array|object",
            "description": "What this output contains"
        }}
    }},
    "steps": [
        "Step 1: What to do first",
        "Step 2: What to do next",
        ...
    ],
    "error_handling": [
        "Handle case when X fails",
        ...
    ],
    "examples": [
        {{
            "name": "Example name",
            "description": "What this example demonstrates",
            "input": {{"param": "value"}},
            "expected_output": {{"field": "expected value"}}
        }}
    ]
}}

Make the skill focused and specific. Include 2-3 diverse examples that cover:
- A typical happy path case
- An edge case or boundary condition
- An error case if applicable"""

    response = await llm_client.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    return _extract_json(response["content"])


async def generate_test_cases(
    spec: dict[str, Any],
    llm_client: Any,
    seed_tests: str | None = None,
) -> str:
    """
    Generate test cases YAML from skill specification.

    Args:
        spec: Skill specification with examples
        llm_client: LLM client for generation
        seed_tests: Optional seed test cases to expand from

    Returns:
        YAML string with test cases
    """
    seed_section = ""
    if seed_tests:
        seed_section = f"""
SEED TEST CASES (expand from these):
{seed_tests}
"""

    examples_text = yaml.dump(spec.get("examples", []), default_flow_style=False)

    prompt = f"""Generate test cases for this skill specification.

SKILL: {spec.get("name")}
DESCRIPTION: {spec.get("description")}

INPUTS:
{yaml.dump(spec.get("inputs", {}), default_flow_style=False)}

OUTPUTS:
{yaml.dump(spec.get("outputs", {}), default_flow_style=False)}

EXAMPLES FROM SPEC:
{examples_text}
{seed_section}

Generate a YAML file with 3-5 test cases that cover:
1. Happy path - typical successful usage
2. Edge case - boundary conditions or unusual inputs
3. Error handling - invalid inputs or failure scenarios

Each test case should have:
- name: snake_case identifier
- description: What this test validates
- inputs: Input values for the test
- expected: Expected output fields (can be partial)
- assertions: List of checks with type, field, and description

Assertion types available:
- equals: Exact value match
- contains: Substring or membership check
- exists: Field is present
- not_empty: Field has a truthy value
- type: Check field type (string, number, boolean, list, dict)

Respond with ONLY the YAML content, no code blocks or explanation."""

    response = await llm_client.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    content = response["content"].strip()

    # Remove code block markers if present
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    return content
