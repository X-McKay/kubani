"""Draft a skill specification from a natural language description.

This capability takes a description and optional context, and uses an LLM
to generate a structured skill specification.

Uses Strands structured output for guaranteed type-safe responses.
"""

from ..models import SkillSpec
from ..protocols import LLMClient

# =============================================================================
# Prompts
# =============================================================================

SYSTEM_PROMPT = """/no_think
You are a skill specification designer. Generate detailed, well-structured skill specifications.

IMPORTANT for examples:
- The 'input' field must be a JSON object (dict), not a string
- The 'expected_output' field must be a JSON object (dict), not a string
- Never quote JSON objects as strings"""

USER_PROMPT_TEMPLATE = """Generate a complete skill specification from this description.

SKILL DESCRIPTION:
{description}{context_section}

Create a focused, specific skill with:
- A kebab-case name
- Clear input/output definitions
- Step-by-step instructions
- 2-3 diverse examples covering happy path, edge case, and error case

For each example:
- 'input' must be a dict/object with input values
- 'expected_output' must be a dict/object with expected output values"""


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

    Uses Strands structured output to guarantee type-safe responses.
    The LLM output is automatically validated against the SkillSpec model.

    Args:
        client: LLM client for generation (must support chat_structured)
        description: Natural language description of the skill
        context: Optional additional context to guide generation

    Returns:
        SkillSpec with validated structure

    Raises:
        StructuredOutputException: If output cannot be parsed/validated
    """
    context_section = f"\n\nADDITIONAL CONTEXT:\n{context}" if context else ""
    user_prompt = USER_PROMPT_TEMPLATE.format(
        description=description,
        context_section=context_section,
    )

    # Use structured output if available (FrameworkLLM)
    if hasattr(client, "chat_structured"):
        return await client.chat_structured(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            output_model=SkillSpec,
        )

    # Fallback for mock clients or older implementations
    response = await client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=4000,
    )

    return _parse_json_response(response)


# =============================================================================
# Helper Functions
# =============================================================================


def _parse_json_response(response: str) -> SkillSpec:
    """Parse LLM response into a SkillSpec model (fallback for non-structured output)."""
    import json
    import re

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

    return SkillSpec.model_validate(data)


__all__ = ["draft_skill"]
