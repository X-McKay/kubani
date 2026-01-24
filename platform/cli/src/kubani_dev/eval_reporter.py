"""Evaluation reporting for multi-configuration skill evaluation.

This module provides functions for generating comparison tables, markdown reports,
and LLM-generated analysis summaries from multi-configuration evaluation results.
"""

import json
import logging
from typing import Optional

from kubani_dev.eval_config import (
    ComparisonReport,
    DEFAULT_LARGE_MODEL,
    DEFAULT_LARGE_MODEL_URL,
)
from kubani_dev.llm_client import LLMClient

logger = logging.getLogger(__name__)


def generate_comparison_table(report: ComparisonReport) -> str:
    """Generate an ASCII comparison table from evaluation results.

    Args:
        report: The comparison report containing all configuration results.

    Returns:
        Formatted ASCII table string.
    """
    if not report.results:
        return "No results to display."

    # Build header
    lines = []
    lines.append("")
    lines.append("=" * 75)
    lines.append("                    COMPARISON MATRIX")
    lines.append("=" * 75)
    lines.append("")

    # Configuration table
    header = f"{'Configuration':<22} | {'Accuracy':>10} | {'Latency':>12} | {'Tokens/Test':>12}"
    separator = "-" * len(header)

    lines.append(header)
    lines.append(separator)

    # Sort results by accuracy (descending)
    sorted_results = sorted(
        report.results.items(),
        key=lambda x: x[1].accuracy if not x[1].error else -1,
        reverse=True,
    )

    for config_name, result in sorted_results:
        if result.error:
            lines.append(
                f"{result.config.display_name:<22} | {'ERROR':>10} | {'-':>12} | {'-':>12}"
            )
        else:
            accuracy = f"{result.accuracy:.1f}%"
            latency = f"{result.avg_latency_ms:,.0f} ms"
            tokens = f"{result.avg_tokens:,.0f}"
            lines.append(
                f"{result.config.display_name:<22} | {accuracy:>10} | {latency:>12} | {tokens:>12}"
            )

    lines.append(separator)
    lines.append("")

    return "\n".join(lines)


def generate_rankings(report: ComparisonReport) -> str:
    """Generate ranking strings for each metric.

    Args:
        report: The comparison report containing all configuration results.

    Returns:
        Formatted rankings string.
    """
    rankings = report.get_rankings()

    if not rankings:
        return ""

    lines = []
    lines.append("Rankings:")

    # Get display names for configs
    config_display = {name: result.config.display_name for name, result in report.results.items()}

    if rankings.get("accuracy"):
        ranked = " > ".join(config_display.get(n, n) for n in rankings["accuracy"])
        lines.append(f"  Accuracy:  {ranked}")

    if rankings.get("latency"):
        ranked = " > ".join(config_display.get(n, n) for n in rankings["latency"])
        lines.append(f"  Latency:   {ranked} (faster is better)")

    if rankings.get("tokens"):
        ranked = " > ".join(config_display.get(n, n) for n in rankings["tokens"])
        lines.append(f"  Tokens:    {ranked} (fewer is better)")

    lines.append("")

    return "\n".join(lines)


def generate_summary(
    report: ComparisonReport,
    llm_url: Optional[str] = None,
    llm_model: Optional[str] = None,
) -> str:
    """Generate an LLM-powered analysis summary of the evaluation results.

    Uses the large model with thinking disabled for efficient summary generation.

    Args:
        report: The comparison report to summarize.
        llm_url: Optional custom LLM endpoint URL.
        llm_model: Optional custom model name.

    Returns:
        Generated summary text.
    """
    # Create LLM client for summary generation
    # Use large model with thinking disabled for efficient analysis
    llm = LLMClient(
        base_url=llm_url or DEFAULT_LARGE_MODEL_URL,
        model=llm_model or DEFAULT_LARGE_MODEL,
        timeout=120,
        enable_thinking=False,  # Faster, more concise summaries
    )

    # Build context for the LLM
    comparison_data = report.get_comparison_matrix()
    rankings = report.get_rankings()

    # Build results summary
    results_text = []
    for config_name, result in report.results.items():
        if result.error:
            results_text.append(f"- {result.config.display_name}: FAILED ({result.error})")
        else:
            results_text.append(
                f"- {result.config.display_name}: "
                f"Accuracy={result.accuracy:.1f}%, "
                f"Latency={result.avg_latency_ms:,.0f}ms, "
                f"Tokens={result.avg_tokens:,.0f}/test"
            )

    # Build prompt
    system_prompt = """You are an expert AI/ML engineer analyzing skill evaluation results.
Provide a concise, actionable analysis of the multi-configuration evaluation.

Focus on:
1. Which configuration achieved the best accuracy and why that matters
2. The accuracy vs latency vs cost trade-offs
3. A clear recommendation for which configuration to use and when
4. Any surprising or notable findings

Keep the analysis to 3-4 short paragraphs. Be direct and practical."""

    user_prompt = f"""Analyze these skill evaluation results:

**Skill:** {report.skill_name}

**Results by Configuration:**
{chr(10).join(results_text)}

**Rankings:**
- Best Accuracy: {" > ".join(rankings.get("accuracy", ["N/A"]))}
- Best Latency: {" > ".join(rankings.get("latency", ["N/A"]))}
- Best Token Efficiency: {" > ".join(rankings.get("tokens", ["N/A"]))}

Provide a brief analysis and recommendation."""

    try:
        response = llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )

        # Strip any thinking tags and clean up
        summary = llm._strip_thinking_tags(response["content"])
        return summary.strip()

    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        return f"Summary generation failed: {e}"


def generate_markdown_report(report: ComparisonReport) -> str:
    """Generate a complete markdown report from evaluation results.

    Args:
        report: The comparison report to format.

    Returns:
        Complete markdown report string.
    """
    lines = []

    # Header
    lines.append("# Multi-Configuration Skill Evaluation Report")
    lines.append("")
    lines.append(f"**Skill:** {report.skill_name}")
    lines.append(f"**Mode:** {report.mode}")
    lines.append(f"**Timestamp:** {report.timestamp}")
    lines.append("")

    # Comparison table
    lines.append("## Comparison Matrix")
    lines.append("")
    lines.append("| Configuration | Accuracy | Avg Latency | Avg Tokens/Test | Total Tokens |")
    lines.append("|---------------|----------|-------------|-----------------|--------------|")

    # Sort by accuracy
    sorted_results = sorted(
        report.results.items(),
        key=lambda x: x[1].accuracy if not x[1].error else -1,
        reverse=True,
    )

    for config_name, result in sorted_results:
        if result.error:
            lines.append(f"| {result.config.display_name} | ERROR | - | - | - |")
        else:
            lines.append(
                f"| {result.config.display_name} | "
                f"**{result.accuracy:.1f}%** | "
                f"{result.avg_latency_ms:,.0f} ms | "
                f"{result.avg_tokens:,.0f} | "
                f"{result.total_tokens:,} |"
            )

    lines.append("")

    # Rankings
    rankings = report.get_rankings()
    if rankings:
        lines.append("## Rankings")
        lines.append("")

        config_display = {
            name: result.config.display_name for name, result in report.results.items()
        }

        if rankings.get("accuracy"):
            ranked = " > ".join(config_display.get(n, n) for n in rankings["accuracy"])
            lines.append(f"- **Accuracy:** {ranked}")

        if rankings.get("latency"):
            ranked = " > ".join(config_display.get(n, n) for n in rankings["latency"])
            lines.append(f"- **Latency (fastest first):** {ranked}")

        if rankings.get("tokens"):
            ranked = " > ".join(config_display.get(n, n) for n in rankings["tokens"])
            lines.append(f"- **Token Efficiency (fewest first):** {ranked}")

        lines.append("")

    # Summary
    if report.summary:
        lines.append("## Analysis Summary")
        lines.append("")
        lines.append(report.summary)
        lines.append("")

    # Detailed results per configuration
    lines.append("## Detailed Results by Configuration")
    lines.append("")

    for config_name, result in sorted_results:
        lines.append(f"### {result.config.display_name}")
        lines.append("")
        lines.append(f"**Model:** `{result.config.model}`")
        lines.append(f"**Endpoint:** `{result.config.base_url}`")
        lines.append(
            f"**Thinking Mode:** {'Enabled' if result.config.enable_thinking else 'Disabled'}"
        )
        lines.append("")

        if result.error:
            lines.append(f"> **Error:** {result.error}")
            lines.append("")
            continue

        # Metrics summary
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Accuracy | {result.accuracy:.1f}% |")
        lines.append(f"| Tests Passed | {result.tests_passed}/{result.tests_total} |")
        lines.append(f"| Avg Latency | {result.avg_latency_ms:,.0f} ms |")
        lines.append(f"| Avg Tokens/Test | {result.avg_tokens:,.0f} |")
        lines.append(f"| Total Tokens | {result.total_tokens:,} |")
        lines.append("")

        # Test results
        if result.test_results:
            lines.append("**Test Results:**")
            lines.append("")
            for i, test in enumerate(result.test_results, 1):
                status = "PASS" if test.get("passed") else "FAIL"
                status_icon = "+" if test.get("passed") else "-"
                lines.append(f"{i}. [{status_icon}] {test.get('name', 'Unknown')} - {status}")

                # Show critic feedback for failed tests
                if not test.get("passed") and test.get("critic"):
                    critic = test["critic"]
                    if critic.get("critique"):
                        lines.append(f"   - Critique: {critic['critique'][:100]}...")

            lines.append("")

    # Footer
    lines.append("---")
    lines.append("*Generated by kubani-dev skill evaluation*")

    return "\n".join(lines)


def save_comparison_report(report: ComparisonReport, output_dir, generate_llm_summary: bool = True):
    """Save the comparison report to files.

    Saves both JSON (for programmatic access) and Markdown (for human reading).

    Args:
        report: The comparison report to save.
        output_dir: Directory to save the report files.
        generate_llm_summary: Whether to generate an LLM analysis summary.

    Returns:
        Tuple of (json_path, md_path) where files were saved.
    """
    from pathlib import Path

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate summary if requested and not already present
    if generate_llm_summary and not report.summary:
        logger.info("Generating LLM analysis summary...")
        report.summary = generate_summary(report)

    # Save JSON
    json_path = output_dir / "full_eval.json"
    with open(json_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    logger.info(f"Saved JSON report to {json_path}")

    # Save Markdown
    md_path = output_dir / "full_eval.md"
    md_content = generate_markdown_report(report)
    md_path.write_text(md_content)

    logger.info(f"Saved Markdown report to {md_path}")

    return json_path, md_path
