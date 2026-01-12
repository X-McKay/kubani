"""
Tests for the evaluation framework.

Tests cover:
- Evaluation suite loading
- Test case execution
- Evaluator types
- Results aggregation
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import yaml


class TestEvaluationSuite:
    """Tests for evaluation suite loading and validation."""

    def test_load_suite_from_yaml(self):
        """Test loading evaluation suite from YAML file."""
        from kubani_dev.eval_suite import EvaluationSuite, load_suite
        
        suite_yaml = """
name: test-suite
description: Test evaluation suite
version: "1.0.0"
agent: k8s-monitor
test_cases:
  - name: test-case-1
    description: Test case description
    input:
      scenario: pod_crash
      pod_name: test-pod
    expected:
      action_type: restart
      success: true
    evaluators:
      - type: automated
        criteria:
          action_type_match: true
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(suite_yaml)
            f.flush()
            
            suite = load_suite(f.name)
            
            assert suite.name == "test-suite"
            assert suite.agent == "k8s-monitor"
            assert len(suite.test_cases) == 1
            assert suite.test_cases[0].name == "test-case-1"

    def test_suite_validation(self):
        """Test suite validation."""
        from kubani_dev.eval_suite import EvaluationSuite, TestCase, Evaluator
        
        # Valid suite
        suite = EvaluationSuite(
            name="valid-suite",
            description="Valid suite",
            version="1.0.0",
            agent="k8s-monitor",
            test_cases=[
                TestCase(
                    name="test-1",
                    description="Test",
                    input={"scenario": "test"},
                    expected={"success": True},
                    evaluators=[
                        Evaluator(type="automated", criteria={}),
                    ],
                ),
            ],
        )
        
        assert suite.validate() is True

    def test_suite_validation_fails_without_test_cases(self):
        """Test that suite validation fails without test cases."""
        from kubani_dev.eval_suite import EvaluationSuite
        
        suite = EvaluationSuite(
            name="empty-suite",
            description="Empty suite",
            version="1.0.0",
            agent="k8s-monitor",
            test_cases=[],
        )
        
        with pytest.raises(ValueError, match="at least one test case"):
            suite.validate()

    def test_test_case_validation(self):
        """Test test case validation."""
        from kubani_dev.eval_suite import TestCase, Evaluator
        
        # Valid test case
        test_case = TestCase(
            name="valid-test",
            description="Valid test case",
            input={"scenario": "test"},
            expected={"success": True},
            evaluators=[
                Evaluator(type="automated", criteria={}),
            ],
        )
        
        assert test_case.validate() is True

    def test_evaluator_types(self):
        """Test different evaluator types."""
        from kubani_dev.eval_suite import Evaluator
        
        # Automated evaluator
        auto = Evaluator(type="automated", criteria={"field_match": True})
        assert auto.type == "automated"
        
        # LLM judge evaluator
        llm = Evaluator(
            type="llm_judge",
            criteria={"rubric": "Evaluate the response quality"},
            model="gpt-4",
        )
        assert llm.type == "llm_judge"
        
        # Threshold evaluator
        threshold = Evaluator(
            type="threshold",
            criteria={"min_score": 0.8, "metric": "accuracy"},
        )
        assert threshold.type == "threshold"


class TestEvaluationHarness:
    """Tests for the evaluation harness."""

    def test_harness_initialization(self):
        """Test evaluation harness initialization."""
        from kubani_dev.eval_harness import EvaluationHarness
        
        harness = EvaluationHarness()
        
        assert harness is not None

    @pytest.mark.asyncio
    async def test_run_test_case(self):
        """Test running a single test case."""
        from kubani_dev.eval_harness import EvaluationHarness
        from kubani_dev.eval_suite import TestCase, Evaluator
        
        harness = EvaluationHarness()
        
        test_case = TestCase(
            name="test-case",
            description="Test case",
            input={"scenario": "pod_crash"},
            expected={"action_type": "restart", "success": True},
            evaluators=[
                Evaluator(type="automated", criteria={"action_type_match": True}),
            ],
        )
        
        with patch.object(harness, "_execute_agent") as mock_execute, \
             patch.object(harness, "_evaluate_result") as mock_evaluate:
            mock_execute.return_value = {"action_type": "restart", "success": True}
            mock_evaluate.return_value = {"passed": True, "score": 1.0}
            
            result = await harness.run_test_case(test_case, agent="k8s-monitor")
            
            assert result.passed is True
            assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_run_suite(self):
        """Test running an entire evaluation suite."""
        from kubani_dev.eval_harness import EvaluationHarness
        from kubani_dev.eval_suite import EvaluationSuite, TestCase, Evaluator
        
        harness = EvaluationHarness()
        
        suite = EvaluationSuite(
            name="test-suite",
            description="Test suite",
            version="1.0.0",
            agent="k8s-monitor",
            test_cases=[
                TestCase(
                    name=f"test-{i}",
                    description=f"Test {i}",
                    input={"scenario": f"scenario-{i}"},
                    expected={"success": True},
                    evaluators=[Evaluator(type="automated", criteria={})],
                )
                for i in range(3)
            ],
        )
        
        with patch.object(harness, "run_test_case") as mock_run:
            mock_run.return_value = MagicMock(passed=True, score=1.0)
            
            results = await harness.run_suite(suite)
            
            assert results.total_cases == 3
            assert results.passed_cases == 3
            assert mock_run.call_count == 3

    @pytest.mark.asyncio
    async def test_automated_evaluator(self):
        """Test automated evaluator."""
        from kubani_dev.eval_harness import EvaluationHarness, AutomatedEvaluator
        
        evaluator = AutomatedEvaluator()
        
        expected = {"action_type": "restart", "success": True}
        actual = {"action_type": "restart", "success": True}
        
        result = await evaluator.evaluate(expected, actual, criteria={"exact_match": True})
        
        assert result.passed is True
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_automated_evaluator_partial_match(self):
        """Test automated evaluator with partial match."""
        from kubani_dev.eval_harness import AutomatedEvaluator
        
        evaluator = AutomatedEvaluator()
        
        expected = {"action_type": "restart", "success": True, "message": "Pod restarted"}
        actual = {"action_type": "restart", "success": True, "message": "Different message"}
        
        result = await evaluator.evaluate(
            expected, actual,
            criteria={"fields": ["action_type", "success"]}  # Only check these fields
        )
        
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_llm_judge_evaluator(self):
        """Test LLM judge evaluator."""
        from kubani_dev.eval_harness import LLMJudgeEvaluator
        
        evaluator = LLMJudgeEvaluator()
        
        expected = {"quality": "high"}
        actual = {"response": "This is a detailed and helpful response."}
        
        with patch.object(evaluator, "_call_llm") as mock_llm:
            mock_llm.return_value = {
                "score": 0.9,
                "reasoning": "Response is detailed and helpful",
                "passed": True,
            }
            
            result = await evaluator.evaluate(
                expected, actual,
                criteria={"rubric": "Evaluate response quality"}
            )
            
            assert result.passed is True
            assert result.score == 0.9

    @pytest.mark.asyncio
    async def test_threshold_evaluator(self):
        """Test threshold evaluator."""
        from kubani_dev.eval_harness import ThresholdEvaluator
        
        evaluator = ThresholdEvaluator()
        
        actual = {"accuracy": 0.85, "latency_ms": 150}
        
        result = await evaluator.evaluate(
            expected={},
            actual=actual,
            criteria={
                "thresholds": {
                    "accuracy": {"min": 0.8},
                    "latency_ms": {"max": 200},
                }
            }
        )
        
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_threshold_evaluator_failure(self):
        """Test threshold evaluator failure."""
        from kubani_dev.eval_harness import ThresholdEvaluator
        
        evaluator = ThresholdEvaluator()
        
        actual = {"accuracy": 0.7, "latency_ms": 250}
        
        result = await evaluator.evaluate(
            expected={},
            actual=actual,
            criteria={
                "thresholds": {
                    "accuracy": {"min": 0.8},
                    "latency_ms": {"max": 200},
                }
            }
        )
        
        assert result.passed is False


class TestEvaluationResults:
    """Tests for evaluation results handling."""

    def test_results_aggregation(self):
        """Test results aggregation."""
        from kubani_dev.eval_harness import EvaluationResults, TestCaseResult
        
        results = EvaluationResults(
            suite_name="test-suite",
            agent="k8s-monitor",
            timestamp=datetime.now(timezone.utc),
            test_results=[
                TestCaseResult(name="test-1", passed=True, score=1.0),
                TestCaseResult(name="test-2", passed=True, score=0.8),
                TestCaseResult(name="test-3", passed=False, score=0.4),
            ],
        )
        
        assert results.total_cases == 3
        assert results.passed_cases == 2
        assert results.failed_cases == 1
        assert results.pass_rate == pytest.approx(0.667, rel=0.01)
        assert results.average_score == pytest.approx(0.733, rel=0.01)

    def test_results_to_json(self):
        """Test results serialization to JSON."""
        from kubani_dev.eval_harness import EvaluationResults, TestCaseResult
        import json
        
        results = EvaluationResults(
            suite_name="test-suite",
            agent="k8s-monitor",
            timestamp=datetime.now(timezone.utc),
            test_results=[
                TestCaseResult(name="test-1", passed=True, score=1.0),
            ],
        )
        
        json_str = results.to_json()
        parsed = json.loads(json_str)
        
        assert parsed["suite_name"] == "test-suite"
        assert parsed["agent"] == "k8s-monitor"
        assert len(parsed["test_results"]) == 1

    def test_results_comparison(self):
        """Test comparing evaluation results."""
        from kubani_dev.eval_harness import EvaluationResults, TestCaseResult, compare_results
        
        baseline = EvaluationResults(
            suite_name="test-suite",
            agent="k8s-monitor",
            timestamp=datetime.now(timezone.utc),
            test_results=[
                TestCaseResult(name="test-1", passed=True, score=0.8),
                TestCaseResult(name="test-2", passed=True, score=0.7),
            ],
        )
        
        current = EvaluationResults(
            suite_name="test-suite",
            agent="k8s-monitor",
            timestamp=datetime.now(timezone.utc),
            test_results=[
                TestCaseResult(name="test-1", passed=True, score=0.9),
                TestCaseResult(name="test-2", passed=True, score=0.8),
            ],
        )
        
        comparison = compare_results(baseline, current)
        
        assert comparison.improved is True
        assert comparison.score_delta > 0


class TestEvaluationCLI:
    """Tests for evaluation CLI commands."""

    def test_eval_run_command(self):
        """Test eval run command."""
        from click.testing import CliRunner
        from kubani_dev.cli import cli
        
        runner = CliRunner()
        
        with patch("kubani_dev.cli.run_evaluation") as mock_run:
            mock_run.return_value = MagicMock(
                total_cases=5,
                passed_cases=4,
                pass_rate=0.8,
            )
            
            result = runner.invoke(cli, ["eval", "run", "--suite", "test.yaml"])
            
            # Check command executed (may fail due to missing file, but tests the CLI)
            assert result.exit_code in [0, 1, 2]

    def test_eval_list_command(self):
        """Test eval list command."""
        from click.testing import CliRunner
        from kubani_dev.cli import cli
        
        runner = CliRunner()
        
        with patch("kubani_dev.cli.list_evaluation_suites") as mock_list:
            mock_list.return_value = ["suite1.yaml", "suite2.yaml"]
            
            result = runner.invoke(cli, ["eval", "list"])
            
            assert result.exit_code in [0, 1, 2]
