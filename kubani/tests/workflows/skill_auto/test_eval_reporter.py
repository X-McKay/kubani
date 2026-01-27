"""Tests for the evaluation reporter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kubani.workflows.skill_auto.capabilities.eval_reporter import (
    EvalReporter,
    format_for_cli,
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
        name="large-thinking",
        display_name="Large + Thinking",
        model="Qwen/Qwen3-8B",
        base_url="http://localhost:8000/v1",
        enable_thinking=True,
    )


@pytest.fixture
def sample_config_result(sample_config):
    """Create a sample configuration result."""
    return ConfigurationResult(
        config=sample_config,
        metrics={
            "accuracy": 0.8,
            "avg_latency_ms": 150.0,
            "tests_passed": 4,
            "tests_total": 5,
            "avg_tokens_per_test": {"total": 500.0},
            "total_tokens": {"total": 2500},
        },
        test_results=[
            {
                "name": "test_basic",
                "passed": True,
                "latency_ms": 100.0,
                "output": {"sum": 5},
                "assertions_passed": [{"type": "exists", "message": "OK"}],
                "assertions_failed": [],
            },
            {
                "name": "test_negative",
                "passed": False,
                "latency_ms": 200.0,
                "output": {"sum": 5},
                "assertions_passed": [],
                "assertions_failed": [
                    {"type": "equals", "message": "Expected -2, got 5", "expected": -2, "actual": 5}
                ],
            },
        ],
    )


@pytest.fixture
def sample_comparison_report(sample_config):
    """Create a sample comparison report."""
    configs = [
        EvalConfiguration(
            name="large-thinking",
            display_name="Large + Thinking",
            model="Qwen/Qwen3-8B",
            base_url="http://localhost:8000/v1",
            enable_thinking=True,
        ),
        EvalConfiguration(
            name="small-no-think",
            display_name="Small - No Think",
            model="Qwen/Qwen3-0.6B",
            base_url="http://localhost:8000/v1",
            enable_thinking=False,
        ),
    ]

    results = {
        "large-thinking": ConfigurationResult(
            config=configs[0],
            metrics={
                "accuracy": 0.9,
                "avg_latency_ms": 200.0,
                "tests_passed": 9,
                "tests_total": 10,
                "avg_tokens_per_test": {"total": 600.0},
                "total_tokens": {"total": 6000},
            },
            test_results=[],
        ),
        "small-no-think": ConfigurationResult(
            config=configs[1],
            metrics={
                "accuracy": 0.7,
                "avg_latency_ms": 50.0,
                "tests_passed": 7,
                "tests_total": 10,
                "avg_tokens_per_test": {"total": 200.0},
                "total_tokens": {"total": 2000},
            },
            test_results=[],
        ),
    }

    return ComparisonReport(
        skill_name="sum-numbers",
        mode="full",
        timestamp="2024-01-15T10:30:00Z",
        results=results,
    )


# =============================================================================
# Test Quick Report Formatting
# =============================================================================


class TestFormatQuickReport:
    """Tests for quick report formatting."""

    def test_successful_report(self, sample_config_result):
        """Test formatting a successful evaluation."""
        reporter = EvalReporter()
        output = reporter.format_quick_report(sample_config_result)

        assert "Large + Thinking" in output
        assert "80.0%" in output or "80%" in output
        assert "4/5" in output
        assert "150" in output
        assert "Qwen/Qwen3-8B" in output
        assert "Enabled" in output

    def test_shows_failed_tests(self, sample_config_result):
        """Test that failed tests are shown."""
        reporter = EvalReporter()
        output = reporter.format_quick_report(sample_config_result)

        assert "test_negative" in output
        assert "Expected -2, got 5" in output

    def test_error_report(self, sample_config):
        """Test formatting an error result."""
        result = ConfigurationResult(
            config=sample_config,
            metrics={},
            test_results=[],
            error="Connection refused",
        )

        reporter = EvalReporter()
        output = reporter.format_quick_report(result)

        assert "FAILED" in output
        assert "Connection refused" in output

    def test_excellent_status(self, sample_config):
        """Test excellent status message for high accuracy."""
        result = ConfigurationResult(
            config=sample_config,
            metrics={
                "accuracy": 0.95,
                "avg_latency_ms": 100.0,
                "tests_passed": 19,
                "tests_total": 20,
            },
            test_results=[],
        )

        reporter = EvalReporter()
        output = reporter.format_quick_report(result)

        assert "Excellent" in output or "✅" in output


# =============================================================================
# Test Comparison Table Formatting
# =============================================================================


class TestFormatComparisonTable:
    """Tests for comparison table formatting."""

    def test_table_output(self, sample_comparison_report):
        """Test comparison table output."""
        reporter = EvalReporter()
        output = reporter.format_comparison_table(sample_comparison_report)

        assert "sum-numbers" in output
        assert "full" in output
        assert "large-thinking" in output
        assert "small-no-think" in output
        assert "90" in output or "90.0%" in output
        assert "70" in output or "70.0%" in output

    def test_rankings_shown(self, sample_comparison_report):
        """Test that rankings are displayed."""
        reporter = EvalReporter()
        output = reporter.format_comparison_table(sample_comparison_report)

        assert "Rankings" in output
        assert "Best Accuracy" in output or "Accuracy" in output
        assert "Fastest" in output

    def test_empty_report(self):
        """Test handling empty report."""
        report = ComparisonReport(
            skill_name="empty-skill",
            mode="full",
            timestamp="2024-01-01T00:00:00Z",
            results={},
        )

        reporter = EvalReporter()
        output = reporter.format_comparison_table(report)

        assert "No configurations" in output or "empty-skill" in output


# =============================================================================
# Test Markdown Formatting
# =============================================================================


class TestFormatMarkdownReport:
    """Tests for Markdown report formatting."""

    def test_single_config_markdown(self, sample_config_result):
        """Test Markdown formatting for single config."""
        reporter = EvalReporter()
        output = reporter.format_markdown_report(sample_config_result)

        assert "# Evaluation Report" in output
        assert "## Summary" in output
        assert "80" in output
        assert "Qwen/Qwen3-8B" in output
        assert "test_basic" in output
        assert "test_negative" in output

    def test_comparison_markdown(self, sample_comparison_report):
        """Test Markdown formatting for comparison report."""
        reporter = EvalReporter()
        output = reporter.format_markdown_report(sample_comparison_report)

        assert "# Comparison Report" in output
        assert "| Configuration" in output
        assert "large-thinking" in output
        assert "small-no-think" in output
        assert "## Rankings" in output

    def test_error_markdown(self, sample_config):
        """Test Markdown formatting for error result."""
        result = ConfigurationResult(
            config=sample_config,
            metrics={},
            test_results=[],
            error="Service unavailable",
        )

        reporter = EvalReporter()
        output = reporter.format_markdown_report(result)

        assert "❌ Failed" in output
        assert "Service unavailable" in output


# =============================================================================
# Test Analysis Summary
# =============================================================================


class TestGenerateAnalysisSummary:
    """Tests for LLM-generated analysis."""

    @pytest.mark.asyncio
    async def test_successful_analysis(self, sample_comparison_report):
        """Test generating analysis summary."""
        reporter = EvalReporter()

        with patch("kubani.framework.llm.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(
                return_value="The large-thinking configuration offers the best accuracy "
                "but small-no-think is faster for production."
            )
            mock_get_llm.return_value = mock_llm

            summary = await reporter.generate_analysis_summary(sample_comparison_report)

            assert "large-thinking" in summary or "accuracy" in summary.lower()
            mock_llm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_analysis_failure_handling(self, sample_comparison_report):
        """Test handling of analysis generation failure."""
        reporter = EvalReporter()

        with patch("kubani.framework.llm.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.chat = AsyncMock(side_effect=RuntimeError("API error"))
            mock_get_llm.return_value = mock_llm

            summary = await reporter.generate_analysis_summary(sample_comparison_report)

            assert "unavailable" in summary.lower() or "error" in summary.lower()


# =============================================================================
# Test Save Report
# =============================================================================


class TestSaveReport:
    """Tests for saving reports to files."""

    def test_save_all_formats(self, tmp_path, sample_config_result):
        """Test saving report in all formats."""
        reporter = EvalReporter()

        saved = reporter.save_report(sample_config_result, tmp_path)

        assert "json" in saved
        assert "md" in saved
        assert "txt" in saved

        # Verify files exist
        assert saved["json"].exists()
        assert saved["md"].exists()
        assert saved["txt"].exists()

        # Verify JSON content
        import json

        with open(saved["json"]) as f:
            data = json.load(f)
        assert "metrics" in data
        assert data["config"]["name"] == "large-thinking"

    def test_save_specific_formats(self, tmp_path, sample_config_result):
        """Test saving only specific formats."""
        reporter = EvalReporter()

        saved = reporter.save_report(sample_config_result, tmp_path, formats=["json"])

        assert "json" in saved
        assert "md" not in saved
        assert "txt" not in saved

    def test_save_comparison_report(self, tmp_path, sample_comparison_report):
        """Test saving comparison report."""
        reporter = EvalReporter()

        saved = reporter.save_report(sample_comparison_report, tmp_path)

        assert saved["json"].exists()

        import json

        with open(saved["json"]) as f:
            data = json.load(f)

        assert data["skill_name"] == "sum-numbers"
        assert "configurations" in data
        assert "rankings" in data

    def test_creates_output_directory(self, tmp_path, sample_config_result):
        """Test that output directory is created if needed."""
        reporter = EvalReporter()
        new_dir = tmp_path / "reports" / "deep" / "nested"

        saved = reporter.save_report(sample_config_result, new_dir)

        assert new_dir.exists()
        assert saved["json"].exists()


# =============================================================================
# Test Convenience Functions
# =============================================================================


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_format_for_cli_config_result(self, sample_config_result):
        """Test format_for_cli with ConfigurationResult."""
        output = format_for_cli(sample_config_result)

        assert "Large + Thinking" in output
        assert "80" in output

    def test_format_for_cli_comparison_report(self, sample_comparison_report):
        """Test format_for_cli with ComparisonReport."""
        output = format_for_cli(sample_comparison_report)

        assert "sum-numbers" in output
        assert "large-thinking" in output
        assert "small-no-think" in output
