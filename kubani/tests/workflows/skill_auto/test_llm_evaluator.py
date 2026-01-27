"""Tests for LLM-based skill evaluator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kubani.workflows.skill_auto.capabilities.llm_evaluator import (
    AssertionResult,
    EvaluationResult,
    SkillEvaluator,
    TestResult,
    _check_single_assertion,
    _get_nested_value,
    check_assertions,
    evaluate_skill_with_config,
)
from kubani.workflows.skill_auto.eval_config import EvalConfiguration

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_config():
    """Create a sample evaluation configuration."""
    return EvalConfiguration(
        name="test-config",
        display_name="Test Config",
        model="test-model",
        base_url="http://localhost:8000/v1",
        enable_thinking=False,
    )


@pytest.fixture
def sample_skill_sop():
    """Sample SKILL.md content."""
    return """# Sum Two Numbers

## Purpose
Add two numbers together.

## Input Format
- `a`: First number
- `b`: Second number

## Output Format
Return a JSON object with:
- `sum`: The sum of a and b

## Examples
Input: {"a": 2, "b": 3}
Output: {"sum": 5}
"""


@pytest.fixture
def sample_test_cases():
    """Sample test cases."""
    return [
        {
            "name": "basic_sum",
            "description": "Test basic addition",
            "inputs": {"a": 2, "b": 3},
            "expected_output": {"sum": 5},
            "assertions": [
                {"type": "exists", "key": "sum"},
                {"type": "type", "key": "sum", "expected": "number"},
                {"type": "equals", "key": "sum", "expected": 5},
            ],
        },
        {
            "name": "negative_numbers",
            "description": "Test with negative numbers",
            "inputs": {"a": -5, "b": 3},
            "expected_output": {"sum": -2},
            "assertions": [
                {"type": "equals", "key": "sum", "expected": -2},
            ],
        },
    ]


# =============================================================================
# Test _get_nested_value
# =============================================================================


class TestGetNestedValue:
    """Tests for nested value extraction."""

    def test_simple_key(self):
        """Test simple key access."""
        data = {"sum": 5}
        assert _get_nested_value(data, "sum") == 5

    def test_nested_key(self):
        """Test dot notation for nested keys."""
        data = {"result": {"value": 42}}
        assert _get_nested_value(data, "result.value") == 42

    def test_array_index(self):
        """Test array index access."""
        data = {"items": [10, 20, 30]}
        assert _get_nested_value(data, "items.1") == 20

    def test_deep_nesting(self):
        """Test deeply nested access."""
        data = {"a": {"b": {"c": [{"d": "found"}]}}}
        assert _get_nested_value(data, "a.b.c.0.d") == "found"

    def test_missing_key(self):
        """Test missing key returns None."""
        data = {"a": 1}
        assert _get_nested_value(data, "b") is None

    def test_empty_key(self):
        """Test empty key returns whole data."""
        data = {"a": 1}
        assert _get_nested_value(data, "") == data

    def test_invalid_array_index(self):
        """Test invalid array index returns None."""
        data = {"items": [1, 2, 3]}
        assert _get_nested_value(data, "items.10") is None


# =============================================================================
# Test _check_single_assertion
# =============================================================================


class TestCheckSingleAssertion:
    """Tests for single assertion checking."""

    def test_exists_pass(self):
        """Test exists assertion passes when value present."""
        result = _check_single_assertion("exists", 42, None, "key")
        assert result["passed"] is True

    def test_exists_fail(self):
        """Test exists assertion fails when value None."""
        result = _check_single_assertion("exists", None, None, "key")
        assert result["passed"] is False

    def test_type_string_pass(self):
        """Test type assertion for string."""
        result = _check_single_assertion("type", "hello", "string", "key")
        assert result["passed"] is True

    def test_type_number_pass(self):
        """Test type assertion for number (int or float)."""
        result = _check_single_assertion("type", 42, "number", "key")
        assert result["passed"] is True
        result = _check_single_assertion("type", 3.14, "number", "key")
        assert result["passed"] is True

    def test_type_fail(self):
        """Test type assertion fails with wrong type."""
        result = _check_single_assertion("type", 42, "string", "key")
        assert result["passed"] is False

    def test_equals_pass(self):
        """Test equals assertion passes."""
        result = _check_single_assertion("equals", 5, 5, "key")
        assert result["passed"] is True

    def test_equals_fail(self):
        """Test equals assertion fails."""
        result = _check_single_assertion("equals", 5, 10, "key")
        assert result["passed"] is False

    def test_contains_string_pass(self):
        """Test contains assertion for string."""
        result = _check_single_assertion("contains", "hello world", "world", "key")
        assert result["passed"] is True

    def test_contains_string_fail(self):
        """Test contains assertion fails for string."""
        result = _check_single_assertion("contains", "hello world", "foo", "key")
        assert result["passed"] is False

    def test_contains_list_pass(self):
        """Test contains assertion for list."""
        result = _check_single_assertion("contains", [1, 2, 3], 2, "key")
        assert result["passed"] is True

    def test_range_pass(self):
        """Test range assertion passes."""
        result = _check_single_assertion("range", 5, {"min": 0, "max": 10}, "key")
        assert result["passed"] is True

    def test_range_fail(self):
        """Test range assertion fails."""
        result = _check_single_assertion("range", 15, {"min": 0, "max": 10}, "key")
        assert result["passed"] is False

    def test_unknown_type(self):
        """Test unknown assertion type fails."""
        result = _check_single_assertion("unknown", 5, 5, "key")
        assert result["passed"] is False


# =============================================================================
# Test check_assertions
# =============================================================================


class TestCheckAssertions:
    """Tests for the check_assertions function."""

    def test_all_pass(self):
        """Test when all assertions pass."""
        output = {"sum": 5}
        assertions = [
            {"type": "exists", "key": "sum"},
            {"type": "type", "key": "sum", "expected": "number"},
            {"type": "equals", "key": "sum", "expected": 5},
        ]

        results = check_assertions(output, assertions)

        assert len(results) == 3
        assert all(r.passed for r in results)

    def test_some_fail(self):
        """Test when some assertions fail."""
        output = {"sum": 5}
        assertions = [
            {"type": "exists", "key": "sum"},
            {"type": "equals", "key": "sum", "expected": 10},
        ]

        results = check_assertions(output, assertions)

        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False

    def test_empty_assertions(self):
        """Test with no assertions."""
        output = {"sum": 5}
        results = check_assertions(output, [])
        assert results == []


# =============================================================================
# Test Data Classes
# =============================================================================


class TestAssertionResult:
    """Tests for AssertionResult dataclass."""

    def test_creation(self):
        """Test basic creation."""
        result = AssertionResult(
            type="equals",
            passed=True,
            message="Value matches",
            expected=5,
            actual=5,
        )

        assert result.type == "equals"
        assert result.passed is True
        assert result.expected == 5
        assert result.actual == 5


class TestTestResult:
    """Tests for TestResult dataclass."""

    def test_creation_success(self):
        """Test creation for successful test."""
        result = TestResult(
            name="test_sum",
            passed=True,
            latency_ms=150.0,
            output={"sum": 5},
        )

        assert result.name == "test_sum"
        assert result.passed is True
        assert result.latency_ms == 150.0

    def test_creation_failure(self):
        """Test creation for failed test."""
        result = TestResult(
            name="test_sum",
            passed=False,
            latency_ms=100.0,
            error="Connection failed",
        )

        assert result.passed is False
        assert result.error == "Connection failed"


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_creation(self):
        """Test basic creation."""
        result = EvaluationResult(
            skill_name="sum-numbers",
            config_name="large-thinking",
            accuracy=0.8,
            tests_passed=4,
            tests_total=5,
            avg_latency_ms=150.0,
            total_duration_ms=1000.0,
        )

        assert result.skill_name == "sum-numbers"
        assert result.accuracy == 0.8
        assert result.tests_passed == 4

    def test_creation_with_error(self):
        """Test creation with error."""
        result = EvaluationResult(
            skill_name="sum-numbers",
            config_name="large-thinking",
            accuracy=0.0,
            tests_passed=0,
            tests_total=0,
            avg_latency_ms=0.0,
            total_duration_ms=0.0,
            error="Failed to load skill",
        )

        assert result.error == "Failed to load skill"


# =============================================================================
# Test SkillEvaluator
# =============================================================================


class TestSkillEvaluator:
    """Tests for SkillEvaluator class."""

    def test_init(self):
        """Test evaluator initialization."""
        evaluator = SkillEvaluator()
        assert evaluator.enable_critic is True

        evaluator = SkillEvaluator(enable_critic=False)
        assert evaluator.enable_critic is False

    def test_build_execution_prompt(self, sample_skill_sop):
        """Test execution prompt building."""
        evaluator = SkillEvaluator()
        prompt = evaluator._build_execution_prompt(sample_skill_sop)

        assert "SKILL SOP:" in prompt
        assert sample_skill_sop in prompt
        assert "CRITICAL INSTRUCTIONS:" in prompt
        assert "JSON" in prompt

    def test_parse_agent_output_json(self):
        """Test parsing raw JSON output."""
        evaluator = SkillEvaluator()

        # Simulate a mock result with direct text
        mock_result = MagicMock()
        mock_result.message = {"content": [{"text": '{"sum": 5}'}]}

        output = evaluator._parse_agent_output(mock_result)
        assert output == {"sum": 5}

    def test_parse_agent_output_code_block(self):
        """Test parsing JSON from code block."""
        evaluator = SkillEvaluator()

        mock_result = MagicMock()
        mock_result.message = {"content": [{"text": '```json\n{"sum": 5}\n```'}]}

        output = evaluator._parse_agent_output(mock_result)
        assert output == {"sum": 5}

    def test_parse_agent_output_with_thinking(self):
        """Test parsing output with thinking tags."""
        evaluator = SkillEvaluator()

        mock_result = MagicMock()
        mock_result.message = {
            "content": [{"text": '<think>Let me calculate...</think>{"sum": 5}'}]
        }

        output = evaluator._parse_agent_output(mock_result)
        assert output == {"sum": 5}

    def test_parse_agent_output_non_json(self):
        """Test parsing non-JSON output."""
        evaluator = SkillEvaluator()

        mock_result = MagicMock()
        mock_result.message = {"content": [{"text": "Just some text"}]}

        output = evaluator._parse_agent_output(mock_result)
        assert output == {"result": "Just some text"}


class TestSkillEvaluatorFileLoading:
    """Tests for file loading in SkillEvaluator."""

    def test_load_skill_sop(self, tmp_path, sample_skill_sop):
        """Test loading SKILL.md."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(sample_skill_sop)

        evaluator = SkillEvaluator()
        content = evaluator._load_skill_sop(skill_dir)

        assert content == sample_skill_sop

    def test_load_skill_sop_not_found(self, tmp_path):
        """Test error when SKILL.md not found."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()

        evaluator = SkillEvaluator()

        with pytest.raises(FileNotFoundError):
            evaluator._load_skill_sop(skill_dir)

    def test_load_test_cases(self, tmp_path, sample_test_cases):
        """Test loading test_cases.yaml."""
        import yaml

        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "test_cases.yaml").write_text(yaml.dump({"test_cases": sample_test_cases}))

        evaluator = SkillEvaluator()
        cases = evaluator._load_test_cases(skill_dir)

        assert len(cases) == 2
        assert cases[0]["name"] == "basic_sum"

    def test_load_test_cases_not_found(self, tmp_path):
        """Test error when test_cases.yaml not found."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()

        evaluator = SkillEvaluator()

        with pytest.raises(FileNotFoundError):
            evaluator._load_test_cases(skill_dir)

    def test_load_test_cases_empty(self, tmp_path):
        """Test error when no test cases in file."""
        import yaml

        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "test_cases.yaml").write_text(yaml.dump({"test_cases": []}))

        evaluator = SkillEvaluator()

        with pytest.raises(ValueError, match="No test cases found"):
            evaluator._load_test_cases(skill_dir)


# =============================================================================
# Test Full Evaluation Flow
# =============================================================================


class TestEvaluateSkill:
    """Tests for full evaluation flow."""

    @pytest.mark.asyncio
    async def test_evaluate_skill_file_not_found(self, tmp_path, sample_config):
        """Test evaluation when skill files don't exist."""
        skill_dir = tmp_path / "missing-skill"
        skill_dir.mkdir()

        evaluator = SkillEvaluator()
        result = await evaluator.evaluate_skill(skill_dir, sample_config)

        assert result.accuracy == 0.0
        assert result.error is not None
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_evaluate_skill_with_mock_agent(
        self, tmp_path, sample_config, sample_skill_sop, sample_test_cases
    ):
        """Test full evaluation with mocked agent."""
        import yaml

        # Set up skill directory
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(sample_skill_sop)
        (skill_dir / "test_cases.yaml").write_text(yaml.dump({"test_cases": sample_test_cases}))

        # Mock the Strands Agent
        mock_result = MagicMock()
        mock_result.message = {"content": [{"text": '{"sum": 5}'}]}

        with patch("kubani.workflows.skill_auto.capabilities.llm_evaluator.Agent") as MockAgent:
            mock_agent = MagicMock()
            mock_agent.invoke_async = AsyncMock(return_value=mock_result)
            MockAgent.return_value = mock_agent

            evaluator = SkillEvaluator(enable_critic=False)
            result = await evaluator.evaluate_skill(skill_dir, sample_config)

        assert result.skill_name == "test-skill"
        assert result.config_name == "test-config"
        # First test should pass (sum=5), second should fail (expected sum=-2)
        assert result.tests_total == 2
        assert len(result.test_results) == 2


@pytest.mark.asyncio
async def test_evaluate_skill_with_config_convenience(tmp_path, sample_config, sample_skill_sop):
    """Test the convenience function."""
    import yaml

    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(sample_skill_sop)
    (skill_dir / "test_cases.yaml").write_text(
        yaml.dump(
            {
                "test_cases": [
                    {
                        "name": "simple",
                        "inputs": {"a": 1, "b": 2},
                        "expected_output": {"sum": 3},
                        "assertions": [],
                    }
                ]
            }
        )
    )

    mock_result = MagicMock()
    mock_result.message = {"content": [{"text": '{"sum": 3}'}]}

    with patch("kubani.workflows.skill_auto.capabilities.llm_evaluator.Agent") as MockAgent:
        mock_agent = MagicMock()
        mock_agent.invoke_async = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_agent

        result = await evaluate_skill_with_config(skill_dir, sample_config, enable_critic=False)

    assert result.tests_total == 1
    assert result.tests_passed == 1  # No assertions = auto pass
