"""Unit tests for the LLM service layer.

These tests verify the service logic (prompt building, parsing) works correctly
using mock LLM clients, without any actual LLM calls.
"""

import json

import pytest

from kubani.workflows.skill_auto.services.llm import (
    LLMService,
    OverlapAnalysis,
    SkillSpec,
    clean_markdown_output,
    clean_yaml_output,
)


class MockLLMClient:
    """
    A mock LLM client for testing the service layer.

    This client records the prompts it receives and returns
    pre-configured responses for testing.
    """

    def __init__(self, response_to_return: str):
        self.last_messages: list[dict[str, str]] = []
        self.last_temperature: float = 0.0
        self.last_max_tokens: int = 0
        self._response = response_to_return
        self.call_count = 0

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> dict[str, any]:
        self.last_messages = messages
        self.last_temperature = temperature
        self.last_max_tokens = max_tokens
        self.call_count += 1
        return {"content": self._response}


class TestMockLLMClient:
    """Verify the mock client works correctly."""

    def test_mock_returns_configured_response(self):
        """Mock client should return the configured response."""
        mock = MockLLMClient("test response")
        result = mock.chat([{"role": "user", "content": "hello"}])
        assert result["content"] == "test response"

    def test_mock_records_messages(self):
        """Mock client should record the messages it receives."""
        mock = MockLLMClient("response")
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user prompt"},
        ]
        mock.chat(messages, temperature=0.5, max_tokens=1000)

        assert mock.last_messages == messages
        assert mock.last_temperature == 0.5
        assert mock.last_max_tokens == 1000


class TestLLMServiceDetectOverlap:
    """Tests for the detect_overlap method."""

    @pytest.mark.asyncio
    async def test_returns_no_overlap_for_empty_skills(self):
        """Should return no overlap when there are no existing skills."""
        mock_client = MockLLMClient("")  # Won't be called
        service = LLMService(client=mock_client)

        result = await service.detect_overlap("A new skill", [])

        assert result.has_overlap is False
        assert result.confidence == 1.0
        assert result.overlapping_skills == []
        assert result.recommendation == "proceed"
        assert mock_client.call_count == 0  # No LLM call needed

    @pytest.mark.asyncio
    async def test_parses_overlap_response_correctly(self):
        """Should correctly parse the LLM's JSON response."""
        mock_response = json.dumps(
            {
                "has_overlap": True,
                "confidence": 0.85,
                "overlapping_skills": ["existing-skill"],
                "reasoning": "Both skills handle log analysis",
                "recommendation": "merge",
            }
        )
        mock_client = MockLLMClient(mock_response)
        service = LLMService(client=mock_client)

        result = await service.detect_overlap(
            "A skill for analyzing logs",
            [{"name": "existing-skill", "description": "Log analyzer"}],
        )

        assert isinstance(result, OverlapAnalysis)
        assert result.has_overlap is True
        assert result.confidence == 0.85
        assert result.overlapping_skills == ["existing-skill"]
        assert result.reasoning == "Both skills handle log analysis"
        assert result.recommendation == "merge"

    @pytest.mark.asyncio
    async def test_prompt_includes_skill_description(self):
        """Should include the skill description in the prompt."""
        mock_response = json.dumps(
            {
                "has_overlap": False,
                "confidence": 0.9,
                "overlapping_skills": [],
                "reasoning": "Distinct functionality",
                "recommendation": "proceed",
            }
        )
        mock_client = MockLLMClient(mock_response)
        service = LLMService(client=mock_client)

        await service.detect_overlap(
            "A skill for parsing JSON files",
            [{"name": "xml-parser", "description": "Parses XML files"}],
        )

        user_prompt = mock_client.last_messages[1]["content"]
        assert "A skill for parsing JSON files" in user_prompt
        assert "xml-parser" in user_prompt

    @pytest.mark.asyncio
    async def test_handles_json_in_code_block(self):
        """Should handle JSON wrapped in markdown code blocks."""
        mock_response = """```json
{
    "has_overlap": false,
    "confidence": 0.95,
    "overlapping_skills": [],
    "reasoning": "No overlap",
    "recommendation": "proceed"
}
```"""
        mock_client = MockLLMClient(mock_response)
        service = LLMService(client=mock_client)

        result = await service.detect_overlap(
            "A new skill", [{"name": "other", "description": "Other"}]
        )

        assert result.has_overlap is False
        assert result.confidence == 0.95


class TestLLMServiceInferSkill:
    """Tests for the infer_skill method."""

    @pytest.mark.asyncio
    async def test_parses_skill_spec_correctly(self):
        """Should correctly parse a skill specification response."""
        mock_response = json.dumps(
            {
                "name": "analyze-logs",
                "description": "Analyzes log files for errors",
                "inputs": {
                    "log_path": {
                        "type": "string",
                        "description": "Path to log file",
                        "required": True,
                    }
                },
                "outputs": {"errors": {"type": "array", "description": "List of errors found"}},
                "steps": ["Read log file", "Parse entries", "Identify errors"],
                "error_handling": ["Return empty array if file not found"],
                "examples": [
                    {
                        "name": "basic_analysis",
                        "description": "Analyze a simple log",
                        "input": {"log_path": "/var/log/app.log"},
                        "expected_output": {"errors": []},
                    }
                ],
            }
        )
        mock_client = MockLLMClient(mock_response)
        service = LLMService(client=mock_client)

        result = await service.infer_skill("A skill that analyzes log files for errors")

        assert isinstance(result, SkillSpec)
        assert result.name == "analyze-logs"
        assert result.description == "Analyzes log files for errors"
        assert "log_path" in result.inputs
        assert len(result.steps) == 3

    @pytest.mark.asyncio
    async def test_includes_context_in_prompt(self):
        """Should include optional context in the prompt."""
        mock_response = json.dumps(
            {
                "name": "test-skill",
                "description": "Test",
                "inputs": {},
                "outputs": {},
                "steps": [],
                "error_handling": [],
                "examples": [],
            }
        )
        mock_client = MockLLMClient(mock_response)
        service = LLMService(client=mock_client)

        await service.infer_skill("A skill", context="Additional context here")

        user_prompt = mock_client.last_messages[1]["content"]
        assert "Additional context here" in user_prompt


class TestLLMServiceGenerateImprovement:
    """Tests for the generate_improvement method."""

    @pytest.mark.asyncio
    async def test_returns_improved_content(self):
        """Should return the improved skill content."""
        improved_content = """---
name: improved-skill
version: 1.1.0
---

# Improved Skill

Better instructions here."""

        mock_client = MockLLMClient(improved_content)
        service = LLMService(client=mock_client)

        result = await service.generate_improvement(
            skill_content="Original content", feedback="Make it better"
        )

        assert "improved-skill" in result
        assert "Better instructions" in result

    @pytest.mark.asyncio
    async def test_prompt_includes_feedback(self):
        """Should include the feedback in the prompt."""
        mock_client = MockLLMClient("improved content")
        service = LLMService(client=mock_client)

        await service.generate_improvement(
            skill_content="Current skill content",
            feedback="Tests are failing because XYZ",
        )

        user_prompt = mock_client.last_messages[1]["content"]
        assert "Current skill content" in user_prompt
        assert "Tests are failing because XYZ" in user_prompt


class TestCleanYamlOutput:
    """Tests for the clean_yaml_output helper function."""

    def test_removes_yaml_code_block(self):
        """Should remove ```yaml markers."""
        input_text = "```yaml\nkey: value\n```"
        result = clean_yaml_output(input_text)
        assert result == "key: value"

    def test_removes_generic_code_block(self):
        """Should remove generic ``` markers."""
        input_text = "```\nkey: value\n```"
        result = clean_yaml_output(input_text)
        assert result == "key: value"

    def test_removes_thinking_tags(self):
        """Should remove <think> tags."""
        input_text = "<think>thinking...</think>\nkey: value"
        result = clean_yaml_output(input_text)
        assert result == "key: value"

    def test_handles_clean_yaml(self):
        """Should pass through clean YAML unchanged."""
        input_text = "key: value"
        result = clean_yaml_output(input_text)
        assert result == "key: value"


class TestCleanMarkdownOutput:
    """Tests for the clean_markdown_output helper function."""

    def test_removes_markdown_code_block(self):
        """Should remove ```markdown markers."""
        input_text = "```markdown\n# Title\n```"
        result = clean_markdown_output(input_text)
        assert result == "# Title"

    def test_removes_thinking_tags(self):
        """Should remove <think> tags."""
        input_text = "<think>reasoning</think>\n# Title"
        result = clean_markdown_output(input_text)
        assert result == "# Title"

    def test_handles_clean_markdown(self):
        """Should pass through clean markdown unchanged."""
        input_text = "# Title\n\nContent"
        result = clean_markdown_output(input_text)
        assert result == "# Title\n\nContent"
