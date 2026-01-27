"""Tests for draft_skill capability."""

import pytest

from kubani.framework.testing.mocks import MockLLM
from kubani.workflows.skill_auto.capabilities.draft_skill import draft_skill
from kubani.workflows.skill_auto.models import SkillSpec

# =============================================================================
# Test Data
# =============================================================================

VALID_SKILL_SPEC_JSON = """{
    "name": "test-skill",
    "description": "A test skill for unit testing",
    "inputs": {
        "query": {
            "type": "string",
            "description": "Input query",
            "required": true
        }
    },
    "outputs": {
        "result": {
            "type": "string",
            "description": "Output result"
        }
    },
    "steps": ["Step 1: Parse input", "Step 2: Process", "Step 3: Return result"],
    "error_handling": ["Handle invalid input gracefully"],
    "examples": [
        {
            "name": "basic_example",
            "description": "Basic usage example",
            "input": {"query": "test"},
            "expected_output": {"result": "test result"}
        }
    ]
}"""

VALID_SKILL_SPEC_IN_CODE_BLOCK = f"""Here is the skill specification:

```json
{VALID_SKILL_SPEC_JSON}
```

This covers the main use cases."""


# =============================================================================
# Tests
# =============================================================================


class TestDraftSkill:
    """Tests for draft_skill capability."""

    @pytest.mark.asyncio
    async def test_returns_valid_skill_spec(self):
        """Successfully parses valid JSON response into SkillSpec."""
        client = MockLLM(responses=[VALID_SKILL_SPEC_JSON])
        result = await draft_skill(client, "Create a skill that does X")

        assert isinstance(result, SkillSpec)
        assert result.name == "test-skill"
        assert result.description == "A test skill for unit testing"
        assert "query" in result.inputs
        assert result.inputs["query"].type == "string"
        assert len(result.steps) == 3

    @pytest.mark.asyncio
    async def test_extracts_json_from_code_block(self):
        """Extracts JSON from markdown code block."""
        client = MockLLM(responses=[VALID_SKILL_SPEC_IN_CODE_BLOCK])
        result = await draft_skill(client, "Create a skill")

        assert isinstance(result, SkillSpec)
        assert result.name == "test-skill"

    @pytest.mark.asyncio
    async def test_includes_context_in_prompt(self):
        """Context is included in the prompt sent to LLM."""
        client = MockLLM(responses=[VALID_SKILL_SPEC_JSON])
        await draft_skill(client, "Do X", context="Extra context here")

        # Verify context was included in the prompt
        assert client.call_count == 1
        user_message = client.calls[0]["messages"][1]["content"]
        assert "Extra context here" in user_message
        assert "ADDITIONAL CONTEXT" in user_message

    @pytest.mark.asyncio
    async def test_no_context_section_when_none(self):
        """No context section when context is None."""
        client = MockLLM(responses=[VALID_SKILL_SPEC_JSON])
        await draft_skill(client, "Do X", context=None)

        user_message = client.calls[0]["messages"][1]["content"]
        assert "ADDITIONAL CONTEXT" not in user_message

    @pytest.mark.asyncio
    async def test_raises_on_invalid_json(self):
        """Raises ValueError when LLM returns invalid JSON."""
        client = MockLLM(responses=["not valid json at all"])
        with pytest.raises(ValueError, match="Invalid JSON"):
            await draft_skill(client, "Create a skill")

    @pytest.mark.asyncio
    async def test_raises_on_missing_required_fields(self):
        """Raises ValidationError when JSON is missing required fields."""
        incomplete_json = '{"name": "test", "description": "test"}'
        client = MockLLM(responses=[incomplete_json])
        with pytest.raises(ValueError):  # JSON parsing or Pydantic ValidationError
            await draft_skill(client, "Create a skill")

    @pytest.mark.asyncio
    async def test_strips_thinking_tags(self):
        """Strips <think> tags from response before parsing."""
        response_with_thinking = f"<think>Let me think about this...</think>{VALID_SKILL_SPEC_JSON}"
        client = MockLLM(responses=[response_with_thinking])
        result = await draft_skill(client, "Create a skill")

        assert isinstance(result, SkillSpec)
        assert result.name == "test-skill"

    @pytest.mark.asyncio
    async def test_uses_correct_prompts(self):
        """Verifies system and user prompts are structured correctly."""
        client = MockLLM(responses=[VALID_SKILL_SPEC_JSON])
        await draft_skill(client, "Build a logging skill")

        assert client.call_count == 1
        messages = client.calls[0]["messages"]

        # Check system message
        assert messages[0]["role"] == "system"
        assert "skill specification designer" in messages[0]["content"]

        # Check user message
        assert messages[1]["role"] == "user"
        assert "Build a logging skill" in messages[1]["content"]
        assert "kebab-case name" in messages[1]["content"]
