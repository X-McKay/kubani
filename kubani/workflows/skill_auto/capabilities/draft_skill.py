"""Draft a skill specification from a natural language description.

This capability takes a description and optional context, and uses an LLM
to generate a structured skill specification.
"""

import json
import re

from ..models import SkillSpec
from ..protocols import LLMClient

# =============================================================================
# Prompts
# =============================================================================

SYSTEM_PROMPT = """You are a skill specification designer. Generate detailed, well-structured skill specifications. Always respond with valid JSON."""

USER_PROMPT_TEMPLATE = """Generate a complete skill specification from this description.

SKILL DESCRIPTION:
{description}{context_section}

Create a focused, specific skill with:
- A kebab-case name
- Clear input/output definitions
- Step-by-step instructions
- 2-3 diverse examples covering happy path, edge case, and error case

Respond with JSON matching this schema:
{{
    "name": "kebab-case-name",
    "description": "One-line description",
    "inputs": {{
        "param_name": {{"type": "string", "description": "What it is", "required": true}}
    }},
    "outputs": {{
        "field_name": {{"type": "string", "description": "What it contains"}}
    }},
    "steps": ["Step 1", "Step 2", "Step 3"],
    "error_handling": ["How to handle error X"],
    "examples": [
        {{
            "name": "example_name",
            "description": "What this demonstrates",
            "input": {{"param": "value"}},
            "expected_output": {{"field": "value"}}
        }}
    ]
}}"""


# =============================================================================
# Main Function
# =============================================================================


async def draft_skill(
    client: LLMClient,
    description: str,
    context: str | None = None,
) -> SkillSpec:
    """
    Draft a skill specification from a description.

    Uses an LLM to generate a structured skill specification based on
    the provided natural language description.

    Args:
        client: LLM client for generation
        description: Natural language description of the skill
        context: Optional additional context to guide generation

    Returns:
        SkillSpec with validated structure

    Raises:
        ValueError: If the LLM response cannot be parsed as valid JSON
        ValidationError: If the JSON doesn't match SkillSpec schema
    """
    context_section = f"\n\nADDITIONAL CONTEXT:\n{context}" if context else ""
    user_prompt = USER_PROMPT_TEMPLATE.format(
        description=description,
        context_section=context_section,
    )

    response = await client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=4000,
    )

    return _parse_json_response(response, SkillSpec)


# =============================================================================
# Helper Functions
# =============================================================================


def _parse_json_response(response: str, model_class: type[SkillSpec]) -> SkillSpec:
    """Parse LLM response into a Pydantic model."""
    # Strip thinking tags if present
    response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
    response = response.strip()

    # Extract JSON from markdown code blocks
    if "```json" in response:
        json_start = response.find("```json") + 7
        json_end = response.find("```", json_start)
        response = response[json_start:json_end].strip()
    elif "```" in response:
        json_start = response.find("```") + 3
        json_end = response.find("```", json_start)
        response = response[json_start:json_end].strip()

    # Parse JSON
    try:
        data = json.loads(response)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in LLM response: {e}. Response: {response[:200]}") from e

    return model_class.model_validate(data)


__all__ = ["draft_skill"]
