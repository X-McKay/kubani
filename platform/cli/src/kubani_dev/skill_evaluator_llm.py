"""LLM-based skill evaluation system."""

import json
import logging
import time
import yaml
from pathlib import Path
from typing import Any, Dict, Optional

from kubani_dev.llm_client import LLMClient

logger = logging.getLogger(__name__)


class SkillEvaluatorLLM:
    """Evaluate skills by having an LLM execute them."""

    def __init__(self, llm_client: LLMClient):
        """
        Initialize evaluator.

        Args:
            llm_client: LLM client for skill execution
        """
        self.llm = llm_client

    def evaluate_skill(self, skill_dir: Path, verbose: bool = False) -> Dict[str, Any]:
        """
        Evaluate a skill using LLM execution.

        Args:
            skill_dir: Path to skill directory
            verbose: Whether to print detailed output

        Returns:
            Evaluation results dict
        """
        # Load skill SOP
        skill_md_path = skill_dir / "SKILL.md"
        if not skill_md_path.exists():
            raise FileNotFoundError(f"SKILL.md not found in {skill_dir}")

        skill_sop = skill_md_path.read_text()

        # Load test cases
        test_cases_path = skill_dir / "test_cases.yaml"
        if not test_cases_path.exists():
            raise FileNotFoundError(f"test_cases.yaml not found in {skill_dir}")

        with open(test_cases_path) as f:
            test_data = yaml.safe_load(f)

        test_cases = test_data.get("test_cases", [])

        if verbose:
            print(f"Evaluating skill with {len(test_cases)} test cases...")

        # Run each test case
        results = []
        total_tokens = {"prompt": 0, "completion": 0, "total": 0}
        total_latency = 0

        for i, test_case in enumerate(test_cases, 1):
            if verbose:
                print(f"\n[{i}/{len(test_cases)}] Running: {test_case['name']}")

            result = self._run_test_case(
                skill_sop, test_case, verbose=verbose, is_first_test=(i == 1)
            )

            results.append(result)

            # Accumulate metrics
            for key in total_tokens:
                total_tokens[key] += result["tokens"][key]
            total_latency += result["latency_ms"]

        # Calculate metrics
        passed = sum(1 for r in results if r["passed"])
        total_assertions = sum(len(r["assertions"]) for r in results)
        passed_assertions = sum(sum(1 for a in r["assertions"] if a["passed"]) for r in results)

        accuracy = (passed_assertions / total_assertions * 100) if total_assertions > 0 else 0
        avg_latency = total_latency / len(results) if results else 0

        # Calculate average critic confidence from test results
        critic_confidences = [
            r["critic"]["confidence"]
            for r in results
            if r.get("critic") and "confidence" in r["critic"]
        ]
        avg_critic_confidence = (
            sum(critic_confidences) / len(critic_confidences) if critic_confidences else 0.0
        )

        evaluation_result = {
            "skill_name": skill_dir.name,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "metrics": {
                "accuracy": accuracy,
                "tests_passed": passed,
                "tests_total": len(results),
                "assertions_passed": passed_assertions,
                "assertions_total": total_assertions,
                "avg_latency_ms": avg_latency,
                "avg_critic_confidence": avg_critic_confidence,
                "total_tokens": total_tokens,
                "avg_tokens_per_test": {
                    "prompt": total_tokens["prompt"] / len(results) if results else 0,
                    "completion": total_tokens["completion"] / len(results) if results else 0,
                    "total": total_tokens["total"] / len(results) if results else 0,
                },
            },
            "test_results": results,
        }

        return evaluation_result

    def _run_test_case(
        self,
        skill_sop: str,
        test_case: Dict[str, Any],
        verbose: bool = False,
        is_first_test: bool = False,
    ) -> Dict[str, Any]:
        """Run a single test case with automatic retry and critic evaluation."""
        start_time = time.time()

        # Execute skill with LLM - with retry loop
        # Use longer timeouts to handle slow LLM endpoints (matches skill.py settings)
        timeout = 300 if is_first_test else 240
        max_retries = 2 if is_first_test else 1
        max_attempts = 3  # Maximum attempts with feedback

        attempts = []
        final_output = {}
        final_tokens = {"prompt": 0, "completion": 0, "total": 0}
        final_latency_ms = 0
        final_error = None

        for attempt_num in range(1, max_attempts + 1):
            attempt_start = time.time()

            if verbose and attempt_num > 1:
                print(f"  Attempt {attempt_num}/{max_attempts}...")

            try:
                execution_result = self.llm.execute_skill(
                    skill_sop, test_case.get("inputs", {}), timeout=timeout, max_retries=max_retries
                )

                output = execution_result["output"]
                tokens = execution_result["tokens"]
                latency_ms = execution_result["latency_ms"]
                error = None

            except Exception as e:
                logger.error(f"Skill execution failed (attempt {attempt_num}): {e}")
                output = {}
                tokens = {"prompt": 0, "completion": 0, "total": 0}
                latency_ms = (time.time() - attempt_start) * 1000
                error = str(e)

            # Run assertions
            assertions = []
            expected_output = test_case.get("expected", {})
            for assertion_spec in test_case.get("assertions", []):
                assertion_result = self._check_assertion(
                    output, assertion_spec, error, expected_output
                )
                assertions.append(assertion_result)

            passed = all(a["passed"] for a in assertions) and error is None

            # Run critic evaluation
            critic_result = None
            if error is None:  # Only run critic if execution succeeded
                try:
                    critic_result = self.llm.critic_evaluate(
                        skill_description=skill_sop[:500],  # First 500 chars
                        test_case_description=test_case.get("description", test_case["name"]),
                        inputs=test_case.get("inputs", {}),
                        expected_output=test_case.get("expected", {}),
                        actual_output=output,
                        assertion_results=assertions,
                    )

                    if verbose:
                        critic_status = "✓" if critic_result["success"] else "✗"
                        print(f"  {critic_status} Critic: {critic_result['critique'][:80]}...")

                except Exception as e:
                    logger.warning(f"Critic evaluation failed: {e}")
                    critic_result = None

            # Store attempt
            attempt_data = {
                "attempt": attempt_num,
                "output": output,
                "error": error,
                "tokens": tokens,
                "latency_ms": latency_ms,
                "assertions": assertions,
                "passed": passed,
                "critic": critic_result,
            }
            attempts.append(attempt_data)

            # Update final results
            final_output = output
            final_tokens = tokens
            final_latency_ms = latency_ms
            final_error = error

            # Check if we should retry
            critic_success = critic_result["success"] if critic_result else passed

            if passed and critic_success:
                # Success! No need to retry
                if verbose and attempt_num > 1:
                    print(f"  ✓ Success on attempt {attempt_num}")
                break
            elif attempt_num < max_attempts:
                # Failed, prepare feedback for next attempt
                if verbose:
                    print("  ✗ Failed, retrying with feedback...")

                # Build feedback for next attempt
                feedback_parts = []
                if error:
                    feedback_parts.append(f"Execution error: {error}")

                failed_assertions = [a for a in assertions if not a["passed"]]
                if failed_assertions:
                    feedback_parts.append("Failed assertions:")
                    for a in failed_assertions[:3]:  # Limit to 3
                        feedback_parts.append(
                            f"  - {a['description']}: expected {a['expected']}, got {a['actual']}"
                        )

                if critic_result and not critic_result["success"]:
                    feedback_parts.append(f"Critic feedback: {critic_result['critique']}")
                    if critic_result.get("suggestions"):
                        feedback_parts.append(f"Suggestions: {critic_result['suggestions']}")

                feedback = "\n".join(feedback_parts)

                # Modify skill_sop to include feedback for next attempt
                skill_sop = f"{skill_sop}\n\n---\nPREVIOUS ATTEMPT FEEDBACK:\n{feedback}\n\nPlease try again, addressing the issues above."

        # Show assertion results
        if verbose:
            for assertion_result in attempts[-1]["assertions"]:
                status = "✓" if assertion_result["passed"] else "✗"
                print(
                    f"  {status} {assertion_result.get('description', assertion_result.get('field', 'assertion'))}"
                )

        # Calculate final passed status
        final_passed = all(a["passed"] for a in attempts[-1]["assertions"]) and final_error is None
        if attempts[-1].get("critic"):
            final_passed = final_passed and attempts[-1]["critic"]["success"]

        return {
            "name": test_case["name"],
            "description": test_case.get("description", ""),
            "passed": final_passed,
            "output": final_output,
            "error": final_error,
            "tokens": final_tokens,
            "latency_ms": final_latency_ms,
            "assertions": attempts[-1]["assertions"],
            "critic": attempts[-1].get("critic"),
            "attempts": len(attempts),
            "attempt_history": attempts,
        }

    def _check_assertion(
        self,
        output: Dict[str, Any],
        assertion_spec: Dict[str, Any],
        error: Optional[str],
        expected_output: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Check a single assertion."""
        assertion_type = assertion_spec.get("type", "equals")
        field = assertion_spec.get("field")
        # Look for expected value in assertion spec, fall back to expected_output
        expected = assertion_spec.get("value")
        if expected is None and expected_output and field:
            expected = expected_output.get(field)

        # Special case: expect_error
        if assertion_type == "expect_error":
            passed = error is not None
            return {
                "type": assertion_type,
                "field": field,
                "expected": "error",
                "actual": "error" if error else "success",
                "passed": passed,
                "description": assertion_spec.get("description", "Expect error"),
            }

        # Get actual value from output
        if field:
            actual = output.get(field)
        else:
            actual = output

        # Check assertion
        passed = False

        if assertion_type == "equals":
            passed = actual == expected
        elif assertion_type == "contains":
            if isinstance(actual, str):
                passed = expected in actual
            elif isinstance(actual, (list, dict)):
                passed = expected in actual
        elif assertion_type == "exists":
            passed = field in output
        elif assertion_type == "not_empty":
            passed = bool(actual)
        elif assertion_type == "type":
            type_map = {
                "string": str,
                "number": (int, float),
                "boolean": bool,
                "list": list,
                "dict": dict,
            }
            expected_type = type_map.get(expected, str)
            passed = isinstance(actual, expected_type)
        elif assertion_type == "length":
            if hasattr(actual, "__len__"):
                passed = len(actual) == expected
        elif assertion_type == "greater_than":
            if isinstance(actual, (int, float)):
                passed = actual > expected
        elif assertion_type == "less_than":
            if isinstance(actual, (int, float)):
                passed = actual < expected

        return {
            "type": assertion_type,
            "field": field,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "description": assertion_spec.get(
                "description", f"{field} {assertion_type} {expected}"
            ),
        }

    def save_evaluation_results(self, results: Dict[str, Any], output_path: Path):
        """Save evaluation results to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        logger.info(f"Saved evaluation results to {output_path}")

    def generate_evaluation_report(self, results: Dict[str, Any]) -> str:
        """Generate a markdown report from evaluation results."""
        metrics = results["metrics"]

        report = f"""# Skill Evaluation Report

**Skill:** {results["skill_name"]}  
**Timestamp:** {results["timestamp"]}

## Summary

| Metric | Value |
|--------|-------|
| Accuracy | {metrics["accuracy"]:.1f}% |
| Tests Passed | {metrics["tests_passed"]}/{metrics["tests_total"]} |
| Assertions Passed | {metrics["assertions_passed"]}/{metrics["assertions_total"]} |
| Avg Latency | {metrics["avg_latency_ms"]:.0f} ms |
| Avg Tokens/Test | {metrics["avg_tokens_per_test"]["total"]:.0f} |
| Total Tokens | {metrics["total_tokens"]["total"]} |

## Test Results

"""

        for i, test_result in enumerate(results["test_results"], 1):
            status = "✅ PASS" if test_result["passed"] else "❌ FAIL"
            report += f"### {i}. {test_result['name']} - {status}\n\n"
            report += f"**Description:** {test_result['description']}\n\n"
            report += f"**Latency:** {test_result['latency_ms']:.0f} ms  \n"
            report += f"**Tokens:** {test_result['tokens']['total']}\n\n"

            if test_result.get("error"):
                report += f"**Error:** `{test_result['error']}`\n\n"

            report += "**Assertions:**\n\n"
            for assertion in test_result["assertions"]:
                status_icon = "✓" if assertion["passed"] else "✗"
                report += f"- {status_icon} {assertion['description']}\n"
                if not assertion["passed"]:
                    report += f"  - Expected: `{assertion['expected']}`\n"
                    report += f"  - Actual: `{assertion['actual']}`\n"

            report += "\n"

        return report
