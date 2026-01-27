"""Tests for the evaluation orchestrator."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kubani.workflows.skill_auto.capabilities.eval_orchestrator import (
    EvalOrchestrator,
    evaluate_full,
    evaluate_quick,
)
from kubani.workflows.skill_auto.capabilities.llm_evaluator import (
    AssertionResult,
    EvaluationResult,
    TestResult,
)
from kubani.workflows.skill_auto.eval_config import (
    ComparisonReport,
    ConfigurationResult,
    EvalConfiguration,
)

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
def sample_evaluation_result():
    """Create a sample evaluation result."""
    return EvaluationResult(
        skill_name="test-skill",
        config_name="test-config",
        accuracy=0.8,
        tests_passed=4,
        tests_total=5,
        avg_latency_ms=150.0,
        total_duration_ms=1000.0,
        test_results=[
            TestResult(
                name="test1",
                passed=True,
                latency_ms=100.0,
                assertions_passed=[
                    AssertionResult(
                        type="exists", passed=True, message="OK", expected=None, actual=5
                    )
                ],
                assertions_failed=[],
                output={"result": 5},
            ),
            TestResult(
                name="test2",
                passed=False,
                latency_ms=200.0,
                assertions_passed=[],
                assertions_failed=[
                    AssertionResult(
                        type="equals",
                        passed=False,
                        message="Expected 10, got 5",
                        expected=10,
                        actual=5,
                    )
                ],
                output={"result": 5},
            ),
        ],
    )


# =============================================================================
# Test EvalOrchestrator Initialization
# =============================================================================


class TestEvalOrchestratorInit:
    """Tests for EvalOrchestrator initialization."""

    def test_default_init(self):
        """Test default initialization."""
        orchestrator = EvalOrchestrator()
        assert orchestrator.enable_critic is True
        assert orchestrator.timeout_per_config == 600

    def test_custom_init(self):
        """Test custom initialization."""
        orchestrator = EvalOrchestrator(enable_critic=False, timeout_per_config=300)
        assert orchestrator.enable_critic is False
        assert orchestrator.timeout_per_config == 300


# =============================================================================
# Test Quick Evaluation
# =============================================================================


class TestRunQuick:
    """Tests for quick evaluation."""

    @pytest.mark.asyncio
    async def test_run_quick_success(self, sample_evaluation_result):
        """Test successful quick evaluation."""
        orchestrator = EvalOrchestrator()

        with patch.object(orchestrator, "_run_with_config") as mock_run:
            mock_result = ConfigurationResult(
                config=MagicMock(),
                metrics={"accuracy": 0.8},
                test_results=[],
            )
            mock_run.return_value = mock_result

            result = await orchestrator.run_quick(Path("/fake/path"))

            assert result is mock_result
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_quick_custom_url(self):
        """Test quick evaluation with custom URL and model."""
        orchestrator = EvalOrchestrator()

        with patch.object(orchestrator, "_run_with_config") as mock_run:
            mock_run.return_value = ConfigurationResult(
                config=MagicMock(),
                metrics={},
                test_results=[],
            )

            await orchestrator.run_quick(
                Path("/fake/path"),
                base_url="http://custom:8000/v1",
                model="custom-model",
            )

            # Verify the config was created with custom values
            call_args = mock_run.call_args
            config = call_args[0][1]  # Second positional arg is config
            assert config.base_url == "http://custom:8000/v1"
            assert config.model == "custom-model"


# =============================================================================
# Test Full Evaluation
# =============================================================================


class TestRunFull:
    """Tests for full evaluation."""

    @pytest.mark.asyncio
    async def test_run_full_parallel(self, sample_evaluation_result):
        """Test full evaluation in parallel mode."""
        orchestrator = EvalOrchestrator()

        def mock_result_for_config(path, config):
            """Create a mock result based on the config."""
            return ConfigurationResult(
                config=config,
                metrics={
                    "accuracy": 0.8 if "large" in config.name else 0.6,
                    "avg_latency_ms": 100.0,
                    "tests_passed": 4,
                    "tests_total": 5,
                    "avg_tokens_per_test": {"total": 500.0},
                    "total_tokens": {"total": 2500},
                },
                test_results=[],
            )

        with patch.object(orchestrator, "_run_with_config") as mock_run:
            mock_run.side_effect = mock_result_for_config

            report = await orchestrator.run_full(Path("/fake/skill"), parallel=True)

            # Should have called _run_with_config 4 times (one for each config)
            assert mock_run.call_count == 4

            # Report should be a ComparisonReport
            assert isinstance(report, ComparisonReport)
            assert report.skill_name == "skill"
            assert report.mode == "full"
            assert len(report.results) == 4

    @pytest.mark.asyncio
    async def test_run_full_sequential(self, sample_evaluation_result):
        """Test full evaluation in sequential mode."""
        orchestrator = EvalOrchestrator()

        call_order = []

        async def mock_result_for_config(path, config):
            """Track call order and create mock result."""
            call_order.append(config.name)
            return ConfigurationResult(
                config=config,
                metrics={
                    "accuracy": 0.7,
                    "avg_latency_ms": 100.0,
                    "tests_passed": 3,
                    "tests_total": 5,
                },
                test_results=[],
            )

        with patch.object(orchestrator, "_run_with_config") as mock_run:
            mock_run.side_effect = mock_result_for_config

            report = await orchestrator.run_full(Path("/fake/skill"), parallel=False)

            # Should have run 4 configs
            assert mock_run.call_count == 4
            assert len(report.results) == 4

    @pytest.mark.asyncio
    async def test_run_full_handles_exceptions(self):
        """Test that full evaluation handles exceptions gracefully."""
        orchestrator = EvalOrchestrator()

        async def mock_with_failure(path, config):
            """Fail for one specific config."""
            if config.name == "small-thinking":
                raise RuntimeError("Connection failed")
            return ConfigurationResult(
                config=config,
                metrics={"accuracy": 0.8},
                test_results=[],
            )

        with patch.object(orchestrator, "_run_with_config") as mock_run:
            mock_run.side_effect = mock_with_failure

            report = await orchestrator.run_full(Path("/fake/skill"), parallel=False)

            # Should still have all 4 results
            assert len(report.results) == 4

            # The failed config should have an error
            assert report.results["small-thinking"].error is not None
            assert "Connection failed" in report.results["small-thinking"].error


# =============================================================================
# Test Run With Mode
# =============================================================================


class TestRunWithMode:
    """Tests for run_with_mode method."""

    @pytest.mark.asyncio
    async def test_quick_mode(self):
        """Test run_with_mode with quick mode."""
        orchestrator = EvalOrchestrator()

        with patch.object(orchestrator, "run_quick") as mock_quick:
            mock_quick.return_value = ConfigurationResult(
                config=MagicMock(),
                metrics={},
                test_results=[],
            )

            result = await orchestrator.run_with_mode(Path("/fake/skill"), mode="quick")

            mock_quick.assert_called_once()
            assert isinstance(result, ConfigurationResult)

    @pytest.mark.asyncio
    async def test_full_mode(self):
        """Test run_with_mode with full mode."""
        orchestrator = EvalOrchestrator()

        with patch.object(orchestrator, "run_full") as mock_full:
            mock_full.return_value = ComparisonReport(
                skill_name="test",
                mode="full",
                timestamp="2024-01-01T00:00:00",
            )

            result = await orchestrator.run_with_mode(Path("/fake/skill"), mode="full")

            mock_full.assert_called_once()
            assert isinstance(result, ComparisonReport)

    @pytest.mark.asyncio
    async def test_invalid_mode(self):
        """Test run_with_mode with invalid mode raises ValueError."""
        orchestrator = EvalOrchestrator()

        with pytest.raises(ValueError, match="Unknown evaluation mode"):
            await orchestrator.run_with_mode(Path("/fake/skill"), mode="invalid")


# =============================================================================
# Test Internal Methods
# =============================================================================


class TestRunWithConfig:
    """Tests for _run_with_config method."""

    @pytest.mark.asyncio
    async def test_successful_evaluation(self, sample_config, sample_evaluation_result):
        """Test successful config evaluation."""
        orchestrator = EvalOrchestrator()

        with patch(
            "kubani.workflows.skill_auto.capabilities.eval_orchestrator.SkillEvaluator"
        ) as MockEvaluator:
            mock_evaluator = MagicMock()
            mock_evaluator.evaluate_skill = AsyncMock(return_value=sample_evaluation_result)
            MockEvaluator.return_value = mock_evaluator

            result = await orchestrator._run_with_config(Path("/fake/skill"), sample_config)

            assert isinstance(result, ConfigurationResult)
            assert result.config is sample_config
            assert result.accuracy == 0.8
            assert result.tests_passed == 4
            assert result.error is None

    @pytest.mark.asyncio
    async def test_evaluation_timeout(self, sample_config):
        """Test evaluation timeout handling."""
        import asyncio

        orchestrator = EvalOrchestrator(timeout_per_config=1)

        async def slow_evaluate(*args, **kwargs):
            """Simulate slow evaluation."""
            await asyncio.sleep(10)
            return MagicMock()

        with patch(
            "kubani.workflows.skill_auto.capabilities.eval_orchestrator.SkillEvaluator"
        ) as MockEvaluator:
            mock_evaluator = MagicMock()
            mock_evaluator.evaluate_skill = slow_evaluate
            MockEvaluator.return_value = mock_evaluator

            result = await orchestrator._run_with_config(Path("/fake/skill"), sample_config)

            assert result.error is not None
            assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_evaluation_exception(self, sample_config):
        """Test evaluation exception handling."""
        orchestrator = EvalOrchestrator()

        with patch(
            "kubani.workflows.skill_auto.capabilities.eval_orchestrator.SkillEvaluator"
        ) as MockEvaluator:
            mock_evaluator = MagicMock()
            mock_evaluator.evaluate_skill = AsyncMock(side_effect=RuntimeError("Database error"))
            MockEvaluator.return_value = mock_evaluator

            result = await orchestrator._run_with_config(Path("/fake/skill"), sample_config)

            assert result.error is not None
            assert "Database error" in result.error


# =============================================================================
# Test Convenience Functions
# =============================================================================


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    @pytest.mark.asyncio
    async def test_evaluate_quick(self):
        """Test evaluate_quick convenience function."""
        with patch(
            "kubani.workflows.skill_auto.capabilities.eval_orchestrator.EvalOrchestrator"
        ) as MockOrch:
            mock_orch = MagicMock()
            mock_orch.run_quick = AsyncMock(
                return_value=ConfigurationResult(
                    config=MagicMock(),
                    metrics={},
                    test_results=[],
                )
            )
            MockOrch.return_value = mock_orch

            result = await evaluate_quick("/fake/path")

            mock_orch.run_quick.assert_called_once()
            assert isinstance(result, ConfigurationResult)

    @pytest.mark.asyncio
    async def test_evaluate_quick_string_path(self):
        """Test evaluate_quick with string path."""
        with patch(
            "kubani.workflows.skill_auto.capabilities.eval_orchestrator.EvalOrchestrator"
        ) as MockOrch:
            mock_orch = MagicMock()
            mock_orch.run_quick = AsyncMock(
                return_value=ConfigurationResult(
                    config=MagicMock(),
                    metrics={},
                    test_results=[],
                )
            )
            MockOrch.return_value = mock_orch

            await evaluate_quick("/fake/path")

            # Verify Path was created from string
            call_args = mock_orch.run_quick.call_args
            assert isinstance(call_args[0][0], Path)

    @pytest.mark.asyncio
    async def test_evaluate_full(self):
        """Test evaluate_full convenience function."""
        with patch(
            "kubani.workflows.skill_auto.capabilities.eval_orchestrator.EvalOrchestrator"
        ) as MockOrch:
            mock_orch = MagicMock()
            mock_orch.run_full = AsyncMock(
                return_value=ComparisonReport(
                    skill_name="test",
                    mode="full",
                    timestamp="2024-01-01T00:00:00",
                )
            )
            MockOrch.return_value = mock_orch

            result = await evaluate_full("/fake/path", parallel=True)

            mock_orch.run_full.assert_called_once_with(Path("/fake/path"), parallel=True)
            assert isinstance(result, ComparisonReport)
