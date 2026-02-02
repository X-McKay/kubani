"""Generate test cases for agent specifications.

This capability takes agent information and generates comprehensive
test cases in YAML format, covering expected skills and behaviors.
"""

from typing import Any

import yaml

from kubani.framework.utils import clean_yaml_output
from ...skill_auto.protocols import LLMClient


# =============================================================================
# Prompts
# =============================================================================

SYSTEM_PROMPT = """/no_think
You are a test case designer. Generate comprehensive test cases for AI agents. Return ONLY valid YAML, no markdown code blocks."""

GENERATE_AGENT_TEST_CASES_TEMPLATE = """Generate test cases for this agent specification.

AGENT: {name}
DESCRIPTION: {description}

AVAILABLE SKILLS:
{skills_yaml}

AGENT CONFIG:
{config_yaml}

Generate a YAML file with test_cases key containing 3-5 test cases that cover:
1. Core functionality - typical successful usage of the agent
2. Skill orchestration - verify the agent invokes the correct skills
3. Edge cases - unusual inputs or boundary conditions
4. Error handling - how the agent handles invalid inputs

Each test case should verify:
- That the agent produces appropriate output
- That the agent invokes the expected skills (not too many, not too few)

The YAML must have this structure:
test_cases:
  - name: snake_case_identifier
    prompt: "The user prompt to send to the agent"
    expected_skills:
      - skill-name-1
      - skill-name-2
    expected_output: "Expected output pattern or key phrases to look for"

Return ONLY the YAML content, no markdown code blocks."""


async def draft_agent_test_cases(
    client: LLMClient,
    agent_name: str,
    description: str,
    skills: list[dict[str, str]],
    config: dict[str, Any] | None = None,
) -> str:
    """
    Generate test cases YAML for an agent.

    Uses an LLM to generate comprehensive test cases covering core functionality,
    skill orchestration, edge cases, and error handling.

    Args:
        client: LLM client for generation
        agent_name: Name of the agent
        description: Description of what the agent does
        skills: List of skill dicts with 'name' and 'description' keys
        config: Optional agent configuration dict

    Returns:
        YAML string containing test_cases

    Raises:
        ValueError: If the LLM response is not valid YAML
    """
    skills_yaml = yaml.dump(skills, default_flow_style=False) if skills else "No skills defined"
    config_yaml = yaml.dump(config, default_flow_style=False) if config else "No config"

    user_prompt = GENERATE_AGENT_TEST_CASES_TEMPLATE.format(
        name=agent_name,
        description=description,
        skills_yaml=skills_yaml,
        config_yaml=config_yaml,
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


__all__ = ["draft_agent_test_cases"]
