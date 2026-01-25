"""LLM service layer for the Skill Auto workflow.

Uses the OpenAI library directly with vLLM endpoint, following the pattern
used by other Kubani agents (content_analyst, digest_publisher).
"""

import json
import logging
import re
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .models import OverlapResult

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models for Structured Output
# =============================================================================


class InputParam(BaseModel):
    """Schema for a skill input parameter."""

    type: str = Field(description="Data type: string, number, boolean, array, object")
    description: str = Field(description="What this parameter is for")
    required: bool = Field(default=True, description="Whether this parameter is required")


class OutputField(BaseModel):
    """Schema for a skill output field."""

    type: str = Field(description="Data type: string, number, boolean, array, object")
    description: str = Field(description="What this output contains")


class SkillExample(BaseModel):
    """Schema for a skill example."""

    name: str = Field(description="Example name")
    description: str = Field(description="What this example demonstrates")
    input: dict[str, Any] = Field(description="Example input values")
    expected_output: dict[str, Any] = Field(description="Expected output values")


class SkillSpec(BaseModel):
    """Schema for inferred skill specification."""

    name: str = Field(description="Kebab-case skill name (e.g., 'analyze-logs')")
    description: str = Field(description="One-line description of the skill")
    inputs: dict[str, InputParam] = Field(description="Input parameters")
    outputs: dict[str, OutputField] = Field(description="Output fields")
    steps: list[str] = Field(description="Step-by-step instructions")
    error_handling: list[str] = Field(description="How to handle errors")
    examples: list[SkillExample] = Field(description="2-3 example use cases")


class OverlapAnalysis(BaseModel):
    """Schema for overlap detection analysis."""

    has_overlap: bool = Field(description="Whether significant overlap exists")
    confidence: float = Field(description="Confidence score 0.0-1.0")
    overlapping_skills: list[str] = Field(description="Names of overlapping skills")
    reasoning: str = Field(description="Explanation of the analysis")
    recommendation: str = Field(description="One of: proceed, merge, abort")


# =============================================================================
# Protocol Definition
# =============================================================================


class LLMServiceProtocol(Protocol):
    """Protocol for LLM operations - enables easy mocking."""

    async def infer_skill(self, description: str, context: str | None = None) -> SkillSpec:
        """Infer skill specification from description."""
        ...

    async def detect_overlap(
        self, description: str, existing_skills: list[dict[str, Any]]
    ) -> OverlapAnalysis:
        """Detect if skill overlaps with existing ones."""
        ...

    async def close(self) -> None:
        """Close the client and release resources."""
        ...


# =============================================================================
# Real Implementation using OpenAI library (like other Kubani agents)
# =============================================================================


class LLMService:
    """LLM service using OpenAI library with vLLM endpoint."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 300.0,
    ):
        """
        Initialize LLM service.

        Args:
            base_url: Base URL for the API (should include /v1)
            model: Model name to use
            api_key: API key (optional for some local LLMs)
            timeout: Request timeout in seconds
        """
        from openai import OpenAI

        # Ensure base_url ends with /v1
        base_url = base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        self.model = model
        self.timeout = timeout

        self._client = OpenAI(
            api_key=api_key or "not-needed",
            base_url=base_url,
            timeout=timeout,
        )

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> str:
        """Make a chat completion request and return the response content."""
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        return response.choices[0].message.content or ""

    def _parse_json_response(self, response: str, model_class: type[BaseModel]) -> BaseModel:
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
        data = json.loads(response)
        return model_class.model_validate(data)

    async def infer_skill(self, description: str, context: str | None = None) -> SkillSpec:
        """
        Infer skill specification from description.

        Args:
            description: Natural language description of the skill
            context: Optional additional context

        Returns:
            SkillSpec with validated structure
        """
        context_section = f"\n\nADDITIONAL CONTEXT:\n{context}" if context else ""

        system_prompt = "You are a skill specification designer. Generate detailed, well-structured skill specifications. Always respond with valid JSON."

        user_prompt = f"""Generate a complete skill specification from this description.

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

        response = self._call_llm(system_prompt, user_prompt)
        return self._parse_json_response(response, SkillSpec)

    async def detect_overlap(
        self, description: str, existing_skills: list[dict[str, Any]]
    ) -> OverlapAnalysis:
        """
        Detect if a new skill overlaps with existing skills.

        Args:
            description: Description of the new skill
            existing_skills: List of existing skills with name and description

        Returns:
            OverlapAnalysis with overlap assessment
        """
        if not existing_skills:
            return OverlapAnalysis(
                has_overlap=False,
                confidence=1.0,
                overlapping_skills=[],
                reasoning="No existing skills to compare against",
                recommendation="proceed",
            )

        skills_text = "\n".join(
            f"- {s['name']}: {s.get('description', 'No description')}" for s in existing_skills
        )

        system_prompt = "You are a skill analyst. Analyze whether skills overlap based on their functionality. Always respond with valid JSON."

        user_prompt = f"""Analyze whether this new skill overlaps with any existing skills.

NEW SKILL DESCRIPTION:
{description}

EXISTING SKILLS:
{skills_text}

Consider skills as overlapping if they:
- Address the same problem domain
- Would be triggered by similar scenarios
- Provide redundant functionality

Recommend "merge" if the new skill could enhance an existing one.
Recommend "abort" if the new skill is essentially a duplicate.
Recommend "proceed" if the skill is sufficiently distinct.

Respond with JSON:
{{
    "has_overlap": true/false,
    "confidence": 0.0-1.0,
    "overlapping_skills": ["skill-name"],
    "reasoning": "Explanation",
    "recommendation": "proceed|merge|abort"
}}"""

        response = self._call_llm(system_prompt, user_prompt)
        return self._parse_json_response(response, OverlapAnalysis)

    async def generate_test_cases(self, spec: dict[str, Any], seed_tests: str | None = None) -> str:
        """
        Generate test cases YAML from skill specification.

        Args:
            spec: Skill specification with examples
            seed_tests: Optional seed test cases to expand from

        Returns:
            YAML string with test cases
        """
        import yaml

        seed_section = f"\nSEED TEST CASES (expand from these):\n{seed_tests}" if seed_tests else ""
        examples_text = yaml.dump(spec.get("examples", []), default_flow_style=False)

        system_prompt = "You are a test case designer. Generate comprehensive test cases for skills. Return ONLY valid YAML, no markdown code blocks."

        user_prompt = f"""Generate test cases for this skill specification.

SKILL: {spec.get("name")}
DESCRIPTION: {spec.get("description")}

INPUTS:
{yaml.dump(spec.get("inputs", {}), default_flow_style=False)}

OUTPUTS:
{yaml.dump(spec.get("outputs", {}), default_flow_style=False)}

EXAMPLES FROM SPEC:
{examples_text}
{seed_section}

Generate a YAML file with test_cases key containing 3-5 test cases that cover:
1. Happy path - typical successful usage
2. Edge case - boundary conditions or unusual inputs
3. Error handling - invalid inputs or failure scenarios

The YAML must have this structure:
test_cases:
  - name: snake_case_identifier
    description: What this test validates
    inputs:
      # Input values for the test
    expected:
      # Expected output fields (can be partial)
    assertions:
      - type: equals
        field: some_field
        description: Why this check matters

Return ONLY the YAML content, no markdown code blocks."""

        response = self._call_llm(system_prompt, user_prompt)
        return clean_yaml_output(response)

    async def generate_harder_tests(
        self,
        skill_name: str,
        current_test_cases: str,
        accuracy: float,
        tests_passed: int,
        tests_total: int,
        failing_tests: list[dict[str, str]],
        count: int = 2,
    ) -> str:
        """Generate harder test cases targeting weaknesses."""
        failures_text = "\n".join(
            f"- {t['name']}: {t.get('reason', 'Unknown reason')}" for t in failing_tests
        )

        system_prompt = "You are a test case designer. Generate comprehensive test cases for skills. Return ONLY valid YAML, no markdown code blocks."

        user_prompt = f"""Generate {count} harder test cases for the skill "{skill_name}".

CURRENT TEST CASES:
{current_test_cases}

CURRENT PERFORMANCE:
- Accuracy: {accuracy * 100:.1f}%
- Tests passed: {tests_passed}/{tests_total}

FAILING TESTS AND REASONS:
{failures_text}

Generate {count} NEW test cases that:
1. Target the identified weaknesses and failure patterns
2. Test edge cases and boundary conditions
3. Are harder than the current tests

Return ONLY the YAML content for the new test cases."""

        response = self._call_llm(system_prompt, user_prompt)
        return clean_yaml_output(response)

    async def generate_improvement(self, skill_content: str, feedback: str) -> str:
        """Generate improved SKILL.md content based on feedback."""
        system_prompt = "You are a skill improver. Improve skills based on evaluation feedback. Return ONLY the improved SKILL.md content, no explanation or markdown code blocks."

        user_prompt = f"""Improve this skill based on the evaluation feedback.

CURRENT SKILL:
{skill_content}

EVALUATION FEEDBACK:
{feedback}

Generate an improved version of the SKILL.md that:
1. Addresses the issues identified in the feedback
2. Improves clarity and specificity of instructions
3. Adds better error handling guidance if needed
4. Maintains the same input/output interface

Return ONLY the improved SKILL.md content, no explanation."""

        response = self._call_llm(system_prompt, user_prompt)
        return clean_markdown_output(response)

    async def close(self) -> None:
        """Close the service (no-op for OpenAI client, but maintains interface)."""
        pass


# =============================================================================
# Helper Functions
# =============================================================================


def clean_yaml_output(content: str) -> str:
    """Clean YAML output by removing code blocks and thinking tags."""
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
    """Clean markdown output by removing code blocks and thinking tags."""
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


# =============================================================================
# Compatibility Functions (for existing activity code)
# =============================================================================


async def infer_skill_structure(
    llm: LLMService | Any, description: str, context: str | None = None
) -> dict[str, Any]:
    """Wrapper for backward compatibility with activities."""
    if hasattr(llm, "infer_skill"):
        spec = await llm.infer_skill(description, context)
        return spec.model_dump()
    else:
        # Fallback for mock services in tests
        raise NotImplementedError("Use LLMService.infer_skill()")


async def detect_overlap(
    llm: LLMService | Any, description: str, existing_skills: list[dict[str, Any]]
) -> OverlapResult:
    """Wrapper for backward compatibility with activities."""
    if hasattr(llm, "detect_overlap"):
        analysis = await llm.detect_overlap(description, existing_skills)
        return OverlapResult(
            has_overlap=analysis.has_overlap,
            confidence=analysis.confidence,
            overlapping_skills=analysis.overlapping_skills,
            reasoning=analysis.reasoning,
            recommendation=analysis.recommendation,
        )
    else:
        raise NotImplementedError("Use LLMService.detect_overlap()")


async def generate_test_cases(
    llm: LLMService | Any, spec: dict[str, Any], seed_tests: str | None = None
) -> str:
    """Wrapper for backward compatibility with activities."""
    if hasattr(llm, "generate_test_cases"):
        return await llm.generate_test_cases(spec, seed_tests)
    else:
        raise NotImplementedError("Use LLMService.generate_test_cases()")


async def generate_harder_tests(
    llm: LLMService | Any,
    skill_name: str,
    current_test_cases: str,
    accuracy: float,
    tests_passed: int,
    tests_total: int,
    failing_tests: list[dict[str, str]],
    count: int = 2,
) -> str:
    """Wrapper for backward compatibility with activities."""
    if hasattr(llm, "generate_harder_tests"):
        return await llm.generate_harder_tests(
            skill_name,
            current_test_cases,
            accuracy,
            tests_passed,
            tests_total,
            failing_tests,
            count,
        )
    else:
        raise NotImplementedError("Use LLMService.generate_harder_tests()")


async def generate_improvement(llm: LLMService | Any, skill_content: str, feedback: str) -> str:
    """Wrapper for backward compatibility with activities."""
    if hasattr(llm, "generate_improvement"):
        return await llm.generate_improvement(skill_content, feedback)
    else:
        raise NotImplementedError("Use LLMService.generate_improvement()")
