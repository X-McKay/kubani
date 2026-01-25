"""Tests for eval_service.py - Evaluation result conversion and formatting.

These tests verify the result conversion and feedback formatting logic
without needing to run actual evaluations.
"""

import pytest

from kubani.workflows.skill_auto.eval_service import (
    extract_failing_tests,
    format_evaluation_feedback,
    results_to_metrics,
)


@pytest.fixture
def sample_eval_result():
    """Sample evaluation result from SkillEvaluatorLLM."""
    return {
        "skill_name": "test-skill",
        "timestamp": "2026-01-25T12:00:00",
        "metrics": {
            "accuracy": 80.0,  # Percentage format
            "tests_passed": 4,
            "tests_total": 5,
            "assertions_passed": 8,
            "assertions_total": 10,
            "avg_latency_ms": 1500.0,
            "avg_critic_confidence": 0.85,
            "total_tokens": {
                "prompt": 5000,
                "completion": 2000,
                "total": 7000,
            },
        },
        "test_results": [
            {
                "name": "test_basic",
                "passed": True,
                "assertions": [{"passed": True, "description": "output exists"}],
            },
            {
                "name": "test_edge_case",
                "passed": False,
                "error": None,
                "assertions": [
                    {
                        "passed": False,
                        "description": "output matches expected",
                        "expected": "success",
                        "actual": "failure",
                    },
                ],
                "critic": {
                    "success": False,
                    "confidence": 0.6,
                    "critique": "Output does not address the edge case properly",
                },
            },
        ],
    }


@pytest.fixture
def perfect_eval_result():
    """Perfect evaluation result."""
    return {
        "metrics": {
            "accuracy": 100.0,
            "tests_passed": 5,
            "tests_total": 5,
            "avg_latency_ms": 500.0,
            "avg_critic_confidence": 0.95,
            "total_tokens": {"prompt": 1000, "completion": 500},
        },
        "test_results": [{"name": f"test_{i}", "passed": True, "assertions": []} for i in range(5)],
    }


@pytest.fixture
def failing_eval_result():
    """Evaluation result with multiple failures."""
    return {
        "metrics": {
            "accuracy": 20.0,
            "tests_passed": 1,
            "tests_total": 5,
            "avg_latency_ms": 3000.0,
            "avg_critic_confidence": 0.3,
            "total_tokens": {"prompt": 8000, "completion": 4000},
        },
        "test_results": [
            {"name": "test_ok", "passed": True, "assertions": []},
            {
                "name": "test_fail_1",
                "passed": False,
                "error": "Timeout after 30s",
                "assertions": [],
            },
            {
                "name": "test_fail_2",
                "passed": False,
                "assertions": [
                    {
                        "passed": False,
                        "description": "field exists",
                        "expected": True,
                        "actual": False,
                    }
                ],
                "critic": {
                    "success": False,
                    "confidence": 0.2,
                    "critique": "Missing required output field",
                },
            },
            {
                "name": "test_fail_3",
                "passed": False,
                "assertions": [
                    {
                        "passed": False,
                        "description": "type check",
                        "expected": "string",
                        "actual": "number",
                    }
                ],
            },
            {
                "name": "test_fail_4",
                "passed": False,
                "error": "Invalid JSON response",
                "assertions": [],
            },
        ],
    }


class TestResultsToMetrics:
    """Tests for results_to_metrics function."""

    def test_converts_accuracy_percentage(self, sample_eval_result):
        """Convert accuracy from percentage to fraction."""
        metrics = results_to_metrics(sample_eval_result)

        assert metrics.accuracy == 0.8  # 80% -> 0.8
        assert metrics.tests_passed == 4
        assert metrics.tests_total == 5

    def test_handles_fraction_accuracy(self):
        """Handle accuracy already as fraction."""
        result = {
            "metrics": {
                "accuracy": 0.75,  # Already fraction
                "tests_passed": 3,
                "tests_total": 4,
                "avg_latency_ms": 1000.0,
                "avg_critic_confidence": 0.8,
                "total_tokens": {},
            }
        }

        metrics = results_to_metrics(result)
        assert metrics.accuracy == 0.75

    def test_extracts_all_fields(self, sample_eval_result):
        """Extract all metric fields."""
        metrics = results_to_metrics(sample_eval_result)

        assert metrics.latency_ms == 1500.0
        assert metrics.critic_confidence == 0.85
        assert metrics.tokens_prompt == 5000
        assert metrics.tokens_completion == 2000

    def test_handles_missing_fields(self):
        """Handle missing fields gracefully."""
        result = {"metrics": {}}

        metrics = results_to_metrics(result)

        assert metrics.accuracy == 0.0
        assert metrics.tests_passed == 0
        assert metrics.latency_ms == 0.0

    def test_handles_empty_result(self):
        """Handle empty result dict."""
        metrics = results_to_metrics({})

        assert metrics.accuracy == 0.0
        assert metrics.tests_total == 0


class TestExtractFailingTests:
    """Tests for extract_failing_tests function."""

    def test_extracts_failing_tests(self, sample_eval_result):
        """Extract failing test information."""
        failing = extract_failing_tests(sample_eval_result)

        assert len(failing) == 1
        assert failing[0]["name"] == "test_edge_case"

    def test_includes_error_message(self, failing_eval_result):
        """Include error message when present."""
        failing = extract_failing_tests(failing_eval_result)

        timeout_test = next(f for f in failing if f["name"] == "test_fail_1")
        assert "Timeout" in timeout_test["reason"]

    def test_includes_assertion_details(self, failing_eval_result):
        """Include failed assertion details."""
        failing = extract_failing_tests(failing_eval_result)

        assertion_test = next(f for f in failing if f["name"] == "test_fail_2")
        assert "field exists" in assertion_test["reason"]

    def test_empty_for_perfect_result(self, perfect_eval_result):
        """Return empty list for perfect results."""
        failing = extract_failing_tests(perfect_eval_result)
        assert failing == []

    def test_handles_empty_test_results(self):
        """Handle missing test_results."""
        failing = extract_failing_tests({})
        assert failing == []


class TestFormatEvaluationFeedback:
    """Tests for format_evaluation_feedback function."""

    def test_includes_metrics_summary(self, sample_eval_result):
        """Include metrics summary in feedback."""
        feedback = format_evaluation_feedback(sample_eval_result)

        assert "80.0%" in feedback
        assert "4/5" in feedback
        assert "1500" in feedback

    def test_includes_failing_tests(self, sample_eval_result):
        """Include failing test details."""
        feedback = format_evaluation_feedback(sample_eval_result)

        assert "test_edge_case" in feedback
        assert "Failing tests:" in feedback

    def test_includes_critic_feedback(self, sample_eval_result):
        """Include critic feedback when available."""
        feedback = format_evaluation_feedback(sample_eval_result)

        assert "Critic feedback:" in feedback
        assert "edge case" in feedback.lower()

    def test_perfect_result_no_failures(self, perfect_eval_result):
        """Perfect result has no failure section."""
        feedback = format_evaluation_feedback(perfect_eval_result)

        assert "100.0%" in feedback
        assert "Failing tests:" not in feedback

    def test_limits_critic_feedback(self, failing_eval_result):
        """Limit critic feedback to 3 items."""
        feedback = format_evaluation_feedback(failing_eval_result)

        # Count critic feedback lines
        lines = feedback.split("\n")
        critic_section_started = False
        critic_count = 0
        for line in lines:
            if "Critic feedback:" in line:
                critic_section_started = True
            elif critic_section_started and line.strip().startswith("-"):
                critic_count += 1

        # Should be limited to 3
        assert critic_count <= 3


class TestImproveService:
    """Tests for ImproveService class."""

    def test_cleans_think_tags(self, tmp_path):
        """Verify <think> tags are removed from LLM output."""
        from unittest.mock import MagicMock

        from kubani.workflows.skill_auto.eval_service import ImproveService

        # Create a mock LLM client
        mock_llm = MagicMock()
        mock_llm.chat.return_value = {
            "content": """<think>
Let me think about this improvement...
</think>

---
name: test-skill
version: 0.2.0
---

# Test Skill

Improved content here.""",
            "tokens": {"prompt": 100, "completion": 50},
        }

        # Create skill file
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\n---\n\n# Test")

        # Run improvement
        service = ImproveService(mock_llm)
        result = service.improve_skill(str(skill_dir), "Improve the skill")

        # Verify think tags are removed
        assert result["improved"] is True
        assert "<think>" not in result["new_content"]
        assert "</think>" not in result["new_content"]
        assert "---" in result["new_content"]
        assert "# Test Skill" in result["new_content"]

    def test_cleans_markdown_code_blocks(self, tmp_path):
        """Verify markdown code blocks are removed from LLM output."""
        from unittest.mock import MagicMock

        from kubani.workflows.skill_auto.eval_service import ImproveService

        mock_llm = MagicMock()
        mock_llm.chat.return_value = {
            "content": """```markdown
---
name: test-skill
---

# Test Skill
```""",
            "tokens": {},
        }

        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\n---\n\n# Test")

        service = ImproveService(mock_llm)
        result = service.improve_skill(str(skill_dir), "Improve the skill")

        assert result["improved"] is True
        assert "```" not in result["new_content"]
        assert "---" in result["new_content"]

    def test_handles_missing_skill_file(self, tmp_path):
        """Return error when SKILL.md doesn't exist."""
        from unittest.mock import MagicMock

        from kubani.workflows.skill_auto.eval_service import ImproveService

        mock_llm = MagicMock()
        skill_dir = tmp_path / "nonexistent-skill"
        skill_dir.mkdir()

        service = ImproveService(mock_llm)
        result = service.improve_skill(str(skill_dir), "Improve the skill")

        assert result["improved"] is False
        assert "not found" in result["error"]
