"""Evaluation report generation for skill evaluations.

This module provides formatting and reporting capabilities for skill
evaluation results, including:
- Quick evaluation reports (single configuration)
- Comparison tables (multi-configuration full mode)
- LLM-generated analysis summaries
- JSON and Markdown export

Usage:
    from kubani.workflows.skill_auto.capabilities.eval_reporter import EvalReporter

    reporter = EvalReporter()

    # Format quick report
    output = reporter.format_quick_report(config_result)

    # Format comparison table
    table = reporter.format_comparison_table(comparison_report)

    # Generate AI analysis
    analysis = await reporter.generate_analysis_summary(comparison_report)
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from kubani.workflows.skill_auto.eval_config import (
    ComparisonReport,
    ConfigurationResult,
)

logger = logging.getLogger(__name__)


@dataclass
class ReportOutput:
    """Container for report output in multiple formats."""

    text: str
    """Plain text report for CLI display."""

    markdown: str
    """Markdown formatted report."""

    json_data: dict
    """Structured data for programmatic use."""


class EvalReporter:
    """
    Generate human-readable reports from evaluation results.

    Supports multiple output formats:
    - Plain text for CLI display
    - Markdown for documentation
    - JSON for programmatic use
    """

    def format_quick_report(self, result: ConfigurationResult) -> str:
        """
        Format a single configuration evaluation for CLI output.

        Args:
            result: ConfigurationResult from quick evaluation

        Returns:
            Formatted string suitable for terminal display
        """
        if result.error:
            return self._format_error_report(result)

        lines = [
            "",
            "=" * 60,
            f"  Evaluation: {result.config.display_name}",
            "=" * 60,
            "",
            f"  Accuracy:      {result.accuracy:.1%} ({result.tests_passed}/{result.tests_total} tests)",
            f"  Avg Latency:   {result.avg_latency_ms:.0f}ms",
            f"  Model:         {result.config.model}",
            f"  Thinking:      {'Enabled' if result.config.enable_thinking else 'Disabled'}",
            "",
        ]

        # Add failed tests section if any
        failed_tests = [t for t in result.test_results if not t.get("passed", True)]
        if failed_tests:
            lines.append("  Failed Tests:")
            for test in failed_tests[:5]:  # Limit to first 5
                lines.append(f"    - {test.get('name', 'unknown')}")
                if test.get("error"):
                    lines.append(f"      Error: {test['error'][:80]}")
                for assertion in test.get("assertions_failed", [])[:2]:
                    lines.append(f"      {assertion.get('message', 'Assertion failed')}")
            if len(failed_tests) > 5:
                lines.append(f"    ... and {len(failed_tests) - 5} more")
            lines.append("")

        # Add summary
        if result.accuracy >= 0.9:
            lines.append("  ✅ Excellent! Skill is performing well.")
        elif result.accuracy >= 0.7:
            lines.append("  ⚠️  Good, but some tests need attention.")
        else:
            lines.append("  ❌ Significant failures detected. Review needed.")

        lines.append("")
        lines.append("=" * 60)
        lines.append("")

        return "\n".join(lines)

    def format_comparison_table(self, report: ComparisonReport) -> str:
        """
        Format multi-configuration comparison as a table.

        Args:
            report: ComparisonReport from full evaluation

        Returns:
            Formatted comparison table string
        """
        lines = [
            "",
            "=" * 80,
            f"  Full Evaluation: {report.skill_name}",
            f"  Mode: {report.mode} | Timestamp: {report.timestamp}",
            "=" * 80,
            "",
        ]

        # Build comparison table
        matrix = report.get_comparison_matrix()
        rankings = report.get_rankings()
        configs = report.configurations

        if not configs:
            lines.append("  No configurations completed successfully.")
            return "\n".join(lines)

        # Table header
        header = "  {:<20} | {:>10} | {:>12} | {:>12} | {:>10}".format(
            "Configuration", "Accuracy", "Latency (ms)", "Tokens", "Tests"
        )
        separator = "  " + "-" * 74

        lines.append(header)
        lines.append(separator)

        # Table rows
        for config_name in configs:
            result = report.get_result(config_name)
            if result is None or result.error:
                lines.append(
                    "  {:<20} | {:>10} | {:>12} | {:>12} | {:>10}".format(
                        config_name[:20], "ERROR", "-", "-", "-"
                    )
                )
                continue

            accuracy = matrix["accuracy"].get(config_name, 0.0)
            latency = matrix["avg_latency_ms"].get(config_name, 0.0)
            tokens = matrix["avg_tokens"].get(config_name, 0.0)
            tests = matrix["tests_passed"].get(config_name, "0/0")

            lines.append(
                f"  {config_name[:20]:<20} | {accuracy:>9.1%} | {latency:>12.0f} | {tokens:>12.0f} | {tests:>10}"
            )

        lines.append(separator)
        lines.append("")

        # Rankings section
        lines.append("  Rankings:")
        if rankings.get("accuracy"):
            lines.append(f"    Best Accuracy:  {rankings['accuracy'][0]}")
        if rankings.get("latency"):
            lines.append(f"    Fastest:        {rankings['latency'][0]}")
        if rankings.get("tokens"):
            lines.append(f"    Most Efficient: {rankings['tokens'][0]}")

        lines.append("")

        # Add summary if present
        if report.summary:
            lines.append("  Analysis:")
            for line in report.summary.split("\n"):
                lines.append(f"    {line}")
            lines.append("")

        lines.append("=" * 80)
        lines.append("")

        return "\n".join(lines)

    def format_markdown_report(
        self,
        result: ConfigurationResult | ComparisonReport,
    ) -> str:
        """
        Format evaluation results as Markdown.

        Args:
            result: ConfigurationResult or ComparisonReport

        Returns:
            Markdown formatted report
        """
        if isinstance(result, ConfigurationResult):
            return self._format_single_markdown(result)
        else:
            return self._format_comparison_markdown(result)

    def _format_single_markdown(self, result: ConfigurationResult) -> str:
        """Format single config result as Markdown."""
        if result.error:
            return f"""# Evaluation Report

**Status:** ❌ Failed
**Error:** {result.error}
"""

        lines = [
            f"# Evaluation Report: {result.config.display_name}",
            "",
            "## Summary",
            "",
            f"- **Accuracy:** {result.accuracy:.1%} ({result.tests_passed}/{result.tests_total} tests)",
            f"- **Average Latency:** {result.avg_latency_ms:.0f}ms",
            f"- **Model:** {result.config.model}",
            f"- **Thinking Mode:** {'Enabled' if result.config.enable_thinking else 'Disabled'}",
            "",
            "## Test Results",
            "",
        ]

        for test in result.test_results:
            status = "✅" if test.get("passed") else "❌"
            lines.append(f"### {status} {test.get('name', 'Unknown')}")
            lines.append("")
            lines.append(f"- **Latency:** {test.get('latency_ms', 0):.0f}ms")

            if test.get("error"):
                lines.append(f"- **Error:** {test['error']}")

            if test.get("assertions_failed"):
                lines.append("- **Failed Assertions:**")
                for a in test["assertions_failed"]:
                    lines.append(f"  - {a.get('message', 'Unknown')}")

            lines.append("")

        return "\n".join(lines)

    def _format_comparison_markdown(self, report: ComparisonReport) -> str:
        """Format comparison report as Markdown."""
        lines = [
            f"# Comparison Report: {report.skill_name}",
            "",
            f"**Mode:** {report.mode}  ",
            f"**Timestamp:** {report.timestamp}",
            "",
            "## Configuration Comparison",
            "",
            "| Configuration | Accuracy | Latency (ms) | Tokens | Tests |",
            "|--------------|----------|--------------|--------|-------|",
        ]

        matrix = report.get_comparison_matrix()

        for config_name in report.configurations:
            result = report.get_result(config_name)
            if result is None or result.error:
                lines.append(f"| {config_name} | ERROR | - | - | - |")
                continue

            accuracy = matrix["accuracy"].get(config_name, 0.0)
            latency = matrix["avg_latency_ms"].get(config_name, 0.0)
            tokens = matrix["avg_tokens"].get(config_name, 0.0)
            tests = matrix["tests_passed"].get(config_name, "0/0")

            lines.append(
                f"| {config_name} | {accuracy:.1%} | {latency:.0f} | {tokens:.0f} | {tests} |"
            )

        lines.append("")

        # Rankings
        rankings = report.get_rankings()
        lines.extend(
            [
                "## Rankings",
                "",
                f"- **Best Accuracy:** {rankings.get('accuracy', ['N/A'])[0]}",
                f"- **Fastest:** {rankings.get('latency', ['N/A'])[0]}",
                f"- **Most Efficient:** {rankings.get('tokens', ['N/A'])[0]}",
                "",
            ]
        )

        # Summary
        if report.summary:
            lines.extend(
                [
                    "## Analysis",
                    "",
                    report.summary,
                    "",
                ]
            )

        return "\n".join(lines)

    def _format_error_report(self, result: ConfigurationResult) -> str:
        """Format an error result for CLI display."""
        return f"""
{"=" * 60}
  Evaluation: FAILED
{"=" * 60}

  Error: {result.error}

{"=" * 60}
"""

    async def generate_analysis_summary(
        self,
        report: ComparisonReport,
    ) -> str:
        """
        Generate an LLM-powered analysis summary.

        Uses the framework LLM to analyze the evaluation results and
        provide recommendations.

        Args:
            report: ComparisonReport to analyze

        Returns:
            Analysis summary string
        """
        from kubani.framework.llm import get_llm

        llm = get_llm()

        # Build analysis prompt
        matrix = report.get_comparison_matrix()
        rankings = report.get_rankings()

        prompt = f"""Analyze these skill evaluation results and provide a brief summary with recommendations:

**Skill:** {report.skill_name}

**Configuration Results:**
"""
        for config_name in report.configurations:
            result = report.get_result(config_name)
            if result and not result.error:
                prompt += f"""
- {config_name}:
  - Accuracy: {matrix["accuracy"].get(config_name, 0):.1%}
  - Latency: {matrix["avg_latency_ms"].get(config_name, 0):.0f}ms
  - Tests: {matrix["tests_passed"].get(config_name, "0/0")}
"""

        prompt += f"""
**Rankings:**
- Best Accuracy: {rankings.get("accuracy", ["N/A"])[0]}
- Fastest: {rankings.get("latency", ["N/A"])[0]}
- Most Efficient: {rankings.get("tokens", ["N/A"])[0]}

Provide a 2-3 sentence analysis covering:
1. Which configuration offers the best tradeoff
2. Whether thinking mode significantly helps for this skill
3. Any recommendations for production use
"""

        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful AI assistant analyzing skill evaluation results.",
                },
                {"role": "user", "content": prompt},
            ]

            response = await llm.chat(messages)
            return response.strip()

        except Exception as e:
            logger.error(f"Failed to generate analysis summary: {e}")
            return f"Analysis unavailable: {e}"

    def save_report(
        self,
        result: ConfigurationResult | ComparisonReport,
        output_dir: Path,
        formats: list[str] | None = None,
    ) -> dict[str, Path]:
        """
        Save evaluation report to files.

        Args:
            result: Evaluation result or comparison report
            output_dir: Directory to save reports
            formats: List of formats to save ('json', 'md', 'txt')
                    Defaults to all formats

        Returns:
            Dict mapping format to saved file path
        """
        if formats is None:
            formats = ["json", "md", "txt"]

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

        if isinstance(result, ConfigurationResult):
            base_name = f"eval_{result.config.name}_{timestamp}"
            json_data = {
                "config": {
                    "name": result.config.name,
                    "model": result.config.model,
                    "enable_thinking": result.config.enable_thinking,
                },
                "metrics": result.metrics,
                "test_results": result.test_results,
                "error": result.error,
            }
        else:
            base_name = f"comparison_{result.skill_name}_{timestamp}"
            json_data = result.to_dict()

        saved_files = {}

        if "json" in formats:
            json_path = output_dir / f"{base_name}.json"
            with open(json_path, "w") as f:
                json.dump(json_data, f, indent=2)
            saved_files["json"] = json_path

        if "md" in formats:
            md_path = output_dir / f"{base_name}.md"
            with open(md_path, "w") as f:
                f.write(self.format_markdown_report(result))
            saved_files["md"] = md_path

        if "txt" in formats:
            txt_path = output_dir / f"{base_name}.txt"
            with open(txt_path, "w") as f:
                if isinstance(result, ConfigurationResult):
                    f.write(self.format_quick_report(result))
                else:
                    f.write(self.format_comparison_table(result))
            saved_files["txt"] = txt_path

        return saved_files


# =============================================================================
# Convenience Functions
# =============================================================================


def format_for_cli(result: ConfigurationResult | ComparisonReport) -> str:
    """
    Format evaluation result for CLI display.

    Args:
        result: ConfigurationResult or ComparisonReport

    Returns:
        Formatted string for terminal output
    """
    reporter = EvalReporter()
    if isinstance(result, ConfigurationResult):
        return reporter.format_quick_report(result)
    else:
        return reporter.format_comparison_table(result)


__all__ = [
    "EvalReporter",
    "ReportOutput",
    "format_for_cli",
]
