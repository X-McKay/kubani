"""Tests for draft_test_cases capability."""

import pytest
import yaml

from kubani.workflows.skill_auto.capabilities.draft_test_cases import (
    draft_test_cases,
    generate_harder_tests,
)

# =============================================================================
# Mock LLM Client
# =============================================================================


class MockLLMClient:
    """Mock LLM client that returns configurable responses."""

    def __init__(self, response: str):
        self.response = response
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict[str, str]], **kwargs) -> dict[str, str]:
        self.calls.append(messages)
        return {"content": self.response}


# =============================================================================
# Test Data
# =============================================================================

VALID_TEST_CASES_YAML = """test_cases:
  - name: basic_usage
    description: Test basic successful usage
    inputs:
      query: "test input"
    expected:
      result: "test output"
    assertions:
      - type: contains
        field: result
        value: "test"
        description: Result should contain test"""

VALID_TEST_CASES_IN_CODE_BLOCK = f"""```yaml
{VALID_TEST_CASES_YAML}
```"""

SAMPLE_SPEC = {
    "name": "test-skill",
    "description": "A test skill for unit testing",
    "inputs": {"query": {"type": "string", "description": "Input query", "required": True}},
    "outputs": {"result": {"type": "string", "description": "Output result"}},
    "examples": [
        {
            "name": "example1",
            "description": "Basic example",
            "input": {"query": "hello"},
            "expected_output": {"result": "hello world"},
        }
    ],
}


# =============================================================================
# Tests for draft_test_cases
# =============================================================================


class TestDraftTestCases:
    """Tests for draft_test_cases function."""

    @pytest.mark.asyncio
    async def test_returns_valid_yaml(self):
        """Successfully returns parseable YAML."""
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        result = await draft_test_cases(client, SAMPLE_SPEC)

        # Should be valid YAML
        parsed = yaml.safe_load(result)
        assert "test_cases" in parsed
        assert len(parsed["test_cases"]) > 0

    @pytest.mark.asyncio
    async def test_extracts_yaml_from_code_block(self):
        """Extracts YAML from markdown code block."""
        client = MockLLMClient(VALID_TEST_CASES_IN_CODE_BLOCK)
        result = await draft_test_cases(client, SAMPLE_SPEC)

        # Should be valid YAML without code block markers
        parsed = yaml.safe_load(result)
        assert "test_cases" in parsed

    @pytest.mark.asyncio
    async def test_includes_spec_details_in_prompt(self):
        """Spec details are included in the prompt sent to LLM."""
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        await draft_test_cases(client, SAMPLE_SPEC)

        assert len(client.calls) == 1
        user_message = client.calls[0][1]["content"]
        assert "test-skill" in user_message
        assert "A test skill for unit testing" in user_message
        assert "query" in user_message

    @pytest.mark.asyncio
    async def test_includes_seed_tests_in_prompt(self):
        """Seed tests are included in the prompt when provided."""
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        seed_tests = "existing_test:\n  input: value"
        await draft_test_cases(client, SAMPLE_SPEC, seed_tests=seed_tests)

        user_message = client.calls[0][1]["content"]
        assert "existing_test" in user_message
        assert "SEED TEST CASES" in user_message

    @pytest.mark.asyncio
    async def test_no_seed_section_when_none(self):
        """No seed section when seed_tests is None."""
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        await draft_test_cases(client, SAMPLE_SPEC, seed_tests=None)

        user_message = client.calls[0][1]["content"]
        assert "SEED TEST CASES" not in user_message

    @pytest.mark.asyncio
    async def test_uses_correct_system_prompt(self):
        """Verifies system prompt is for test case design."""
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        await draft_test_cases(client, SAMPLE_SPEC)

        messages = client.calls[0]
        assert messages[0]["role"] == "system"
        assert "test case designer" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_strips_thinking_tags(self):
        """Strips <think> tags from response."""
        response_with_thinking = f"<think>Let me think...</think>{VALID_TEST_CASES_YAML}"
        client = MockLLMClient(response_with_thinking)
        result = await draft_test_cases(client, SAMPLE_SPEC)

        # Should parse without thinking tags
        parsed = yaml.safe_load(result)
        assert "test_cases" in parsed

    @pytest.mark.asyncio
    async def test_handles_empty_spec(self):
        """Handles spec with minimal fields."""
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        minimal_spec = {"name": "minimal", "description": "Minimal spec"}
        result = await draft_test_cases(client, minimal_spec)

        parsed = yaml.safe_load(result)
        assert "test_cases" in parsed


# =============================================================================
# Tests for generate_harder_tests
# =============================================================================


class TestGenerateHarderTests:
    """Tests for generate_harder_tests function."""

    @pytest.mark.asyncio
    async def test_returns_valid_yaml(self):
        """Successfully returns parseable YAML."""
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        result = await generate_harder_tests(
            client,
            skill_name="test-skill",
            current_tests="existing: tests",
            accuracy=0.6,
            tests_passed=3,
            tests_total=5,
            failing_tests=[{"name": "test1", "reason": "Output mismatch"}],
        )

        # Should be valid YAML
        parsed = yaml.safe_load(result)
        assert "test_cases" in parsed

    @pytest.mark.asyncio
    async def test_includes_performance_metrics_in_prompt(self):
        """Performance metrics are included in prompt."""
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        await generate_harder_tests(
            client,
            skill_name="test-skill",
            current_tests="existing: tests",
            accuracy=0.6,
            tests_passed=3,
            tests_total=5,
            failing_tests=[],
        )

        user_message = client.calls[0][1]["content"]
        assert "60.0%" in user_message
        assert "3/5" in user_message

    @pytest.mark.asyncio
    async def test_includes_failing_tests_in_prompt(self):
        """Failing test details are included in prompt."""
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        await generate_harder_tests(
            client,
            skill_name="test-skill",
            current_tests="existing: tests",
            accuracy=0.6,
            tests_passed=3,
            tests_total=5,
            failing_tests=[
                {"name": "edge_case_test", "reason": "Boundary condition failed"},
                {"name": "error_test", "reason": "Wrong error message"},
            ],
        )

        user_message = client.calls[0][1]["content"]
        assert "edge_case_test" in user_message
        assert "Boundary condition failed" in user_message
        assert "error_test" in user_message

    @pytest.mark.asyncio
    async def test_includes_skill_name_in_prompt(self):
        """Skill name is included in prompt."""
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        await generate_harder_tests(
            client,
            skill_name="my-special-skill",
            current_tests="existing: tests",
            accuracy=0.5,
            tests_passed=2,
            tests_total=4,
            failing_tests=[],
        )

        user_message = client.calls[0][1]["content"]
        assert "my-special-skill" in user_message

    @pytest.mark.asyncio
    async def test_uses_custom_count(self):
        """Respects custom count parameter."""
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        await generate_harder_tests(
            client,
            skill_name="test-skill",
            current_tests="existing: tests",
            accuracy=0.5,
            tests_passed=2,
            tests_total=4,
            failing_tests=[],
            count=5,
        )

        user_message = client.calls[0][1]["content"]
        assert "5 harder test cases" in user_message or "Generate 5 NEW" in user_message

    @pytest.mark.asyncio
    async def test_handles_empty_failing_tests(self):
        """Handles case with no failing tests."""
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        result = await generate_harder_tests(
            client,
            skill_name="test-skill",
            current_tests="existing: tests",
            accuracy=1.0,
            tests_passed=5,
            tests_total=5,
            failing_tests=[],
        )

        user_message = client.calls[0][1]["content"]
        assert "None - all tests passed" in user_message

        # Should still return valid YAML
        parsed = yaml.safe_load(result)
        assert "test_cases" in parsed

    @pytest.mark.asyncio
    async def test_handles_missing_reason_in_failing_tests(self):
        """Handles failing tests without reason field."""
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        await generate_harder_tests(
            client,
            skill_name="test-skill",
            current_tests="existing: tests",
            accuracy=0.5,
            tests_passed=2,
            tests_total=4,
            failing_tests=[{"name": "no_reason_test"}],  # No reason field
        )

        user_message = client.calls[0][1]["content"]
        assert "no_reason_test" in user_message
        assert "Unknown reason" in user_message

    @pytest.mark.asyncio
    async def test_strips_code_blocks(self):
        """Strips code blocks from response."""
        response_in_block = f"```yaml\n{VALID_TEST_CASES_YAML}\n```"
        client = MockLLMClient(response_in_block)
        result = await generate_harder_tests(
            client,
            skill_name="test-skill",
            current_tests="existing: tests",
            accuracy=0.5,
            tests_passed=2,
            tests_total=4,
            failing_tests=[],
        )

        # Should parse without code block markers
        parsed = yaml.safe_load(result)
        assert "test_cases" in parsed
