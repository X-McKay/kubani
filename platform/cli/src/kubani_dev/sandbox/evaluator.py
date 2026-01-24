"""
Skill Evaluator for Kubani.

Orchestrates the evaluation process, managing test execution and result collection.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from kubani_dev.sandbox.microsandbox_runner import MicrosandboxRunner, DockerRunner

logger = logging.getLogger(__name__)


class SkillEvaluator:
    """
    Evaluates skills against their test cases.
    
    Supports multiple sandbox backends and generates comprehensive reports.
    """
    
    def __init__(self, skill_dir: Path, sandbox_type: str = "auto"):
        """
        Initialize the evaluator.
        
        Args:
            skill_dir: Path to the skill directory
            sandbox_type: Sandbox backend to use (auto, microsandbox, docker)
        """
        self.skill_dir = skill_dir
        self.sandbox_type = sandbox_type
        self.runner = self._create_runner()
    
    def _create_runner(self):
        """Create the appropriate sandbox runner."""
        if self.sandbox_type == "microsandbox":
            runner = MicrosandboxRunner(self.skill_dir)
            if not runner.is_available():
                raise RuntimeError("Microsandbox requested but not available")
            return runner
        
        elif self.sandbox_type == "docker":
            runner = DockerRunner(self.skill_dir)
            if not runner.is_available():
                raise RuntimeError("Docker requested but not available")
            return runner
        
        elif self.sandbox_type == "auto":
            # Try microsandbox first, fall back to docker, then subprocess
            runner = MicrosandboxRunner(self.skill_dir)
            if runner.is_available():
                logger.info("Using microsandbox for evaluation")
                return runner
            
            runner = DockerRunner(self.skill_dir)
            if runner.is_available():
                logger.info("Using Docker for evaluation")
                return runner
            
            # Fall back to subprocess-based execution (no isolation)
            logger.warning("No sandbox backend available, using subprocess (no isolation)")
            return MicrosandboxRunner(self.skill_dir)  # Uses subprocess fallback
        
        else:
            raise ValueError(f"Unknown sandbox type: {self.sandbox_type}")
    
    def load_test_cases(self) -> List[Dict[str, Any]]:
        """
        Load test cases from test_cases.yaml.
        
        Returns:
            List of test case configurations
        """
        test_cases_path = self.skill_dir / "test_cases.yaml"
        if not test_cases_path.exists():
            raise FileNotFoundError(f"test_cases.yaml not found in {self.skill_dir}")
        
        with open(test_cases_path, "r") as f:
            data = yaml.safe_load(f)
        
        test_cases = data.get("test_cases", [])
        if not test_cases:
            raise ValueError("No test cases found in test_cases.yaml")
        
        return test_cases
    
    def evaluate(self) -> Dict[str, Any]:
        """
        Run the complete evaluation.
        
        Returns:
            Evaluation results with all metrics and test outcomes
        """
        logger.info(f"Starting evaluation for skill: {self.skill_dir.name}")
        
        # Load test cases
        test_cases = self.load_test_cases()
        logger.info(f"Loaded {len(test_cases)} test cases")
        
        # Run evaluation
        results = self.runner.run_evaluation(test_cases)
        
        # Save results
        self.save_results(results)
        
        return results
    
    def save_results(self, results: Dict[str, Any]) -> None:
        """
        Save evaluation results to latest_eval.json.
        
        Args:
            results: Evaluation results to save
        """
        output_path = self.skill_dir / "latest_eval.json"
        
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Saved evaluation results to {output_path}")
        
        # Also generate a markdown report
        self.generate_report(results)
    
    def generate_report(self, results: Dict[str, Any]) -> None:
        """
        Generate a human-readable markdown report.
        
        Args:
            results: Evaluation results
        """
        report_path = self.skill_dir / "latest_eval_report.md"
        
        report = f"""# Evaluation Report: {results['skill_name']}

**Evaluated:** {results['evaluated_at']}  
**Sandbox:** {results['sandbox_type']}

## Summary

- **Accuracy:** {results['accuracy']:.1%} ({results['tests_passed']}/{results['tests_total']} tests passed)
- **Average Latency:** {results['avg_latency_ms']:.0f}ms
- **Total Duration:** {results['total_duration_ms']:.0f}ms

## Test Results

"""
        
        for test_result in results["test_results"]:
            status = "✓ PASS" if test_result["passed"] else "✗ FAIL"
            report += f"### {status}: {test_result['name']}\n\n"
            report += f"- **Latency:** {test_result['latency_ms']:.0f}ms\n"
            
            if test_result.get("error"):
                report += f"- **Error:** {test_result['error']}\n"
            
            if test_result["assertions_passed"]:
                report += f"- **Assertions Passed:** {len(test_result['assertions_passed'])}\n"
            
            if test_result["assertions_failed"]:
                report += f"- **Assertions Failed:** {len(test_result['assertions_failed'])}\n"
                for assertion in test_result["assertions_failed"]:
                    report += f"  - {assertion.get('description', 'Unknown assertion')}\n"
                    if "expected" in assertion and "actual" in assertion:
                        report += f"    - Expected: `{assertion['expected']}`\n"
                        report += f"    - Actual: `{assertion['actual']}`\n"
            
            report += "\n"
        
        report += "## Conclusion\n\n"
        
        if results["accuracy"] == 1.0:
            report += "✅ All tests passed! The skill is ready for promotion.\n"
        elif results["accuracy"] >= 0.8:
            report += "⚠️ Most tests passed, but some failures need attention.\n"
        else:
            report += "❌ Significant failures detected. Review and fix before promotion.\n"
        
        with open(report_path, "w") as f:
            f.write(report)
        
        logger.info(f"Generated evaluation report: {report_path}")


def format_results_for_cli(results: Dict[str, Any]) -> str:
    """
    Format evaluation results for CLI display.
    
    Args:
        results: Evaluation results
        
    Returns:
        Formatted string for terminal output
    """
    lines = []
    lines.append("")
    lines.append("━" * 60)
    lines.append(f"  Accuracy:           {results['accuracy']:.1%} ({results['tests_passed']}/{results['tests_total']} tests passed)")
    lines.append(f"  Avg Latency:        {results['avg_latency_ms']:.0f}ms")
    lines.append(f"  Total Duration:     {results['total_duration_ms']:.0f}ms")
    lines.append("━" * 60)
    lines.append("")
    
    # Show failed tests
    failed_tests = [t for t in results["test_results"] if not t["passed"]]
    if failed_tests:
        lines.append("❌ Failed Tests:")
        for test in failed_tests:
            lines.append(f"  - {test['name']}")
            if test.get("error"):
                lines.append(f"    Error: {test['error']}")
            for assertion in test.get("assertions_failed", []):
                lines.append(f"    {assertion.get('description', 'Unknown')}")
        lines.append("")
    
    # Overall status
    if results["accuracy"] == 1.0:
        lines.append("✅ All tests passed!")
    elif results["accuracy"] >= 0.8:
        lines.append("⚠️ Most tests passed, but some need attention")
    else:
        lines.append("❌ Significant failures detected")
    
    lines.append("")
    lines.append(f"Results saved to: {results.get('skill_name', 'skill')}/latest_eval.json")
    
    return "\n".join(lines)
