"""
Tests for the evaluation framework.

Tests cover:
- Evaluation suite loading and validation
- Grader types and execution
- Harness configuration
- Results tracking
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import yaml


class TestEvaluationSuiteModels:
    """Tests for evaluation suite models."""

    def test_grader_type_enum(self):
        """Test GraderType enum values."""
        from kubani.cli.eval_suite import GraderType
        
        assert GraderType.CODE.value == "code"
        assert GraderType.MODEL.value == "model"
        assert GraderType.HUMAN.value == "human"

    def test_task_status_enum(self):
        """Test TaskStatus enum values."""
        from kubani.cli.eval_suite import TaskStatus
        
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.PASSED.value == "passed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.ERROR.value == "error"

    def test_grader_from_dict_code(self):
        """Test Grader.from_dict() for code graders."""
        from kubani.cli.eval_suite import Grader, GraderType
        
        data = {
            "type": "code",
            "name": "test_grader",
            "assert": "outcome.success == True",
            "weight": 1.0,
            "required": True,
        }
        
        grader = Grader.from_dict(data)
        
        assert grader.type == GraderType.CODE
        assert grader.name == "test_grader"
        assert grader.assertion == "outcome.success == True"
        assert grader.weight == 1.0

    def test_grader_from_dict_model(self):
        """Test Grader.from_dict() for model graders."""
        from kubani.cli.eval_suite import Grader, GraderType
        
        data = {
            "type": "model",
            "name": "llm_judge",
            "rubric": "Evaluate the response quality",
            "criteria": ["accuracy", "completeness"],
        }
        
        grader = Grader.from_dict(data)
        
        assert grader.type == GraderType.MODEL
        assert grader.rubric == "Evaluate the response quality"
        assert len(grader.criteria) == 2

    def test_environment_setup_from_dict(self):
        """Test EnvironmentSetup.from_dict()."""
        from kubani.cli.eval_suite import EnvironmentSetup
        
        data = {
            "setup": ["kubectl apply -f test.yaml"],
            "teardown": ["kubectl delete -f test.yaml"],
            "fixtures": {"test.yaml": "apiVersion: v1\nkind: Pod"},
            "timeout": 120,
        }
        
        env = EnvironmentSetup.from_dict(data)
        
        assert len(env.setup_commands) == 1
        assert len(env.teardown_commands) == 1
        assert "test.yaml" in env.fixtures
        assert env.timeout_seconds == 120

    def test_eval_task_from_dict(self):
        """Test EvalTask.from_dict()."""
        from kubani.cli.eval_suite import EvalTask
        
        data = {
            "name": "test_task",
            "prompt": "Investigate the pod failure",
            "description": "Test task description",
            "graders": [
                {"type": "code", "assert": "outcome.success == True"},
            ],
            "max_turns": 5,
            "timeout": 60,
            "trials": 3,
            "tags": ["k8s", "pod"],
        }
        
        task = EvalTask.from_dict(data)
        
        assert task.name == "test_task"
        assert task.prompt == "Investigate the pod failure"
        assert len(task.graders) == 1
        assert task.max_turns == 5
        assert task.trials == 3
        assert "k8s" in task.tags

    def test_eval_task_id_generation(self):
        """Test EvalTask.task_id() generation."""
        from kubani.cli.eval_suite import EvalTask
        
        task = EvalTask(
            name="test_task",
            prompt="Test prompt",
        )
        
        task_id = task.task_id()
        
        assert len(task_id) == 12
        assert task_id.isalnum()

    def test_eval_suite_from_yaml(self):
        """Test EvalSuite.from_yaml()."""
        from kubani.cli.eval_suite import EvalSuite
        
        yaml_content = """
suite: test_suite
description: Test suite description
agent: k8s-monitor
version: "1.0"
tasks:
  - name: task1
    prompt: Test prompt 1
    graders:
      - type: code
        assert: outcome.success == True
  - name: task2
    prompt: Test prompt 2
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            
            suite = EvalSuite.from_yaml(Path(f.name))
            
            assert suite.name == "test_suite"
            assert suite.agent == "k8s-monitor"
            assert len(suite.tasks) == 2

    def test_eval_suite_id_generation(self):
        """Test EvalSuite.suite_id() generation."""
        from kubani.cli.eval_suite import EvalSuite
        
        suite = EvalSuite(
            name="test_suite",
            version="1.0",
        )
        
        suite_id = suite.suite_id()
        
        assert len(suite_id) == 12
        assert suite_id.isalnum()


class TestEvaluationResults:
    """Tests for evaluation result models."""

    def test_trial_result_dataclass(self):
        """Test TrialResult dataclass."""
        from kubani.cli.eval_suite import TrialResult, TaskStatus
        
        result = TrialResult(
            trial_number=1,
            status=TaskStatus.PASSED,
            duration_seconds=10.5,
            score=0.9,
        )
        
        assert result.trial_number == 1
        assert result.status == TaskStatus.PASSED
        assert result.duration_seconds == 10.5
        assert result.score == 0.9

    def test_task_result_dataclass(self):
        """Test TaskResult dataclass."""
        from kubani.cli.eval_suite import TaskResult, EvalTask
        
        task = EvalTask(name="test_task", prompt="Test prompt")
        result = TaskResult(task=task)
        
        assert result.task.name == "test_task"
        assert len(result.trials) == 0

    def test_suite_result_dataclass(self):
        """Test SuiteResult dataclass."""
        from kubani.cli.eval_suite import SuiteResult, EvalSuite
        
        suite = EvalSuite(name="test_suite", agent="k8s-monitor")
        result = SuiteResult(suite=suite)
        
        assert result.suite.name == "test_suite"
        assert len(result.task_results) == 0


class TestCodeGrader:
    """Tests for the CodeGrader class."""

    def test_code_grader_initialization(self):
        """Test CodeGrader initialization."""
        from kubani.cli.eval_harness import CodeGrader
        
        grader = CodeGrader()
        assert grader is not None

    def test_code_grader_evaluate_pass(self):
        """Test CodeGrader.evaluate() with passing assertion."""
        from kubani.cli.eval_harness import CodeGrader
        from kubani.cli.eval_suite import Grader, GraderType
        
        grader = CodeGrader()
        grader_def = Grader(
            type=GraderType.CODE,
            assertion="outcome.success == True",
        )
        
        outcome = {"success": True}
        transcript = []
        
        passed, score, message = grader.evaluate(grader_def, outcome, transcript)
        
        assert passed is True
        assert score == 1.0

    def test_code_grader_evaluate_fail(self):
        """Test CodeGrader.evaluate() with failing assertion."""
        from kubani.cli.eval_harness import CodeGrader
        from kubani.cli.eval_suite import Grader, GraderType
        
        grader = CodeGrader()
        grader_def = Grader(
            type=GraderType.CODE,
            assertion="outcome.success == True",
        )
        
        outcome = {"success": False}
        transcript = []
        
        passed, score, message = grader.evaluate(grader_def, outcome, transcript)
        
        assert passed is False
        assert score == 0.0

    def test_code_grader_no_assertion(self):
        """Test CodeGrader.evaluate() with no assertion."""
        from kubani.cli.eval_harness import CodeGrader
        from kubani.cli.eval_suite import Grader, GraderType
        
        grader = CodeGrader()
        grader_def = Grader(type=GraderType.CODE, assertion="")
        
        passed, score, message = grader.evaluate(grader_def, {}, [])
        
        assert passed is True
        assert score == 1.0


class TestModelGrader:
    """Tests for the ModelGrader class."""

    def test_model_grader_initialization(self):
        """Test ModelGrader initialization."""
        from kubani.cli.eval_harness import ModelGrader
        
        grader = ModelGrader(
            api_url="http://localhost:8000/v1",
            model="gpt-4",
        )
        
        assert grader.api_url == "http://localhost:8000/v1"
        assert grader.model == "gpt-4"


class TestEvalHarness:
    """Tests for the EvalHarness class."""

    def test_harness_config_dataclass(self):
        """Test HarnessConfig dataclass."""
        from kubani.cli.eval_harness import HarnessConfig
        
        config = HarnessConfig(
            project_root=Path("/home/ubuntu/kubani"),
            evals_dir=Path("/home/ubuntu/kubani/evaluations"),
            output_dir=Path("/tmp/eval-results"),
        )
        
        assert config.project_root == Path("/home/ubuntu/kubani")
        assert config.parallel_trials == 1  # default

    def test_eval_harness_initialization(self):
        """Test EvalHarness initialization."""
        from kubani.cli.eval_harness import EvalHarness, HarnessConfig
        
        config = HarnessConfig(
            project_root=Path("/home/ubuntu/kubani"),
            evals_dir=Path("/home/ubuntu/kubani/evaluations"),
            output_dir=Path("/tmp/eval-results"),
        )
        
        harness = EvalHarness(config)
        
        assert harness.config == config
        assert harness.code_grader is not None
        assert harness.model_grader is not None


class TestEnvironmentManager:
    """Tests for the EnvironmentManager class."""

    def test_environment_manager_initialization(self):
        """Test EnvironmentManager initialization."""
        from kubani.cli.eval_harness import EnvironmentManager
        
        manager = EnvironmentManager(project_root=Path("/home/ubuntu/kubani"))
        
        assert manager.project_root == Path("/home/ubuntu/kubani")


class TestAgentExecutor:
    """Tests for the AgentExecutor class."""

    def test_agent_executor_initialization(self):
        """Test AgentExecutor initialization."""
        from kubani.cli.eval_harness import AgentExecutor
        
        executor = AgentExecutor(
            agent_name="k8s-monitor",
            project_root=Path("/home/ubuntu/kubani"),
        )
        
        assert executor.agent_name == "k8s-monitor"


class TestEvalSuiteLoader:
    """Tests for the EvalSuiteLoader class."""

    def test_suite_loader_initialization(self):
        """Test EvalSuiteLoader initialization."""
        from kubani.cli.eval_suite import EvalSuiteLoader
        
        loader = EvalSuiteLoader(evals_dir=Path("/home/ubuntu/kubani/evaluations"))
        
        assert loader.evals_dir == Path("/home/ubuntu/kubani/evaluations")

    def test_suite_loader_list_suites(self):
        """Test EvalSuiteLoader.list_suites()."""
        from kubani.cli.eval_suite import EvalSuiteLoader
        
        loader = EvalSuiteLoader(evals_dir=Path("/home/ubuntu/kubani/evaluations"))
        
        suites = loader.list_suites()
        
        # Should find at least the k8s and news suites we created
        assert len(suites) >= 2


class TestEvaluationYAMLSuites:
    """Tests for the YAML evaluation suites."""

    def test_k8s_evaluation_suite_exists(self):
        """Test that k8s evaluation suite exists."""
        suite_path = Path("/home/ubuntu/kubani/evaluations/k8s/pod_remediation.yaml")
        
        assert suite_path.exists()

    def test_k8s_evaluation_suite_loads(self):
        """Test that k8s evaluation suite loads correctly."""
        from kubani.cli.eval_suite import EvalSuite
        
        suite_path = Path("/home/ubuntu/kubani/evaluations/k8s/pod_remediation.yaml")
        suite = EvalSuite.from_yaml(suite_path)
        
        assert suite.name is not None
        assert len(suite.tasks) > 0

    def test_news_evaluation_suite_exists(self):
        """Test that news evaluation suite exists."""
        suite_path = Path("/home/ubuntu/kubani/evaluations/news/digest_quality.yaml")
        
        assert suite_path.exists()

    def test_news_evaluation_suite_loads(self):
        """Test that news evaluation suite loads correctly."""
        from kubani.cli.eval_suite import EvalSuite
        
        suite_path = Path("/home/ubuntu/kubani/evaluations/news/digest_quality.yaml")
        suite = EvalSuite.from_yaml(suite_path)
        
        assert suite.name is not None
        assert len(suite.tasks) > 0
