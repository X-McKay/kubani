"""LLM-based skill evaluation system."""

import json
import logging
import time
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    
    def evaluate_skill(
        self,
        skill_dir: Path,
        verbose: bool = False
    ) -> Dict[str, Any]:
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
                skill_sop,
                test_case,
                verbose=verbose
            )
            
            results.append(result)
            
            # Accumulate metrics
            for key in total_tokens:
                total_tokens[key] += result["tokens"][key]
            total_latency += result["latency_ms"]
        
        # Calculate metrics
        passed = sum(1 for r in results if r["passed"])
        total_assertions = sum(len(r["assertions"]) for r in results)
        passed_assertions = sum(
            sum(1 for a in r["assertions"] if a["passed"])
            for r in results
        )
        
        accuracy = (passed_assertions / total_assertions * 100) if total_assertions > 0 else 0
        avg_latency = total_latency / len(results) if results else 0
        
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
                "total_tokens": total_tokens,
                "avg_tokens_per_test": {
                    "prompt": total_tokens["prompt"] / len(results) if results else 0,
                    "completion": total_tokens["completion"] / len(results) if results else 0,
                    "total": total_tokens["total"] / len(results) if results else 0
                }
            },
            "test_results": results
        }
        
        return evaluation_result
    
    def _run_test_case(
        self,
        skill_sop: str,
        test_case: Dict[str, Any],
        verbose: bool = False
    ) -> Dict[str, Any]:
        """Run a single test case."""
        start_time = time.time()
        
        # Execute skill with LLM
        try:
            execution_result = self.llm.execute_skill(
                skill_sop,
                test_case.get("inputs", {})
            )
            
            output = execution_result["output"]
            tokens = execution_result["tokens"]
            latency_ms = execution_result["latency_ms"]
            error = None
            
        except Exception as e:
            logger.error(f"Skill execution failed: {e}")
            output = {}
            tokens = {"prompt": 0, "completion": 0, "total": 0}
            latency_ms = (time.time() - start_time) * 1000
            error = str(e)
        
        # Run assertions
        assertions = []
        for assertion_spec in test_case.get("assertions", []):
            assertion_result = self._check_assertion(
                output,
                assertion_spec,
                error
            )
            assertions.append(assertion_result)
            
            if verbose:
                status = "✓" if assertion_result["passed"] else "✗"
                print(f"  {status} {assertion_spec.get('description', assertion_spec.get('field', 'assertion'))}")
        
        passed = all(a["passed"] for a in assertions) and error is None
        
        return {
            "name": test_case["name"],
            "description": test_case.get("description", ""),
            "passed": passed,
            "output": output,
            "error": error,
            "tokens": tokens,
            "latency_ms": latency_ms,
            "assertions": assertions
        }
    
    def _check_assertion(
        self,
        output: Dict[str, Any],
        assertion_spec: Dict[str, Any],
        error: Optional[str]
    ) -> Dict[str, Any]:
        """Check a single assertion."""
        assertion_type = assertion_spec.get("type", "equals")
        field = assertion_spec.get("field")
        expected = assertion_spec.get("value")
        
        # Special case: expect_error
        if assertion_type == "expect_error":
            passed = error is not None
            return {
                "type": assertion_type,
                "field": field,
                "expected": "error",
                "actual": "error" if error else "success",
                "passed": passed,
                "description": assertion_spec.get("description", "Expect error")
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
                "dict": dict
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
            "description": assertion_spec.get("description", f"{field} {assertion_type} {expected}")
        }
    
    def save_evaluation_results(
        self,
        results: Dict[str, Any],
        output_path: Path
    ):
        """Save evaluation results to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Saved evaluation results to {output_path}")
    
    def generate_evaluation_report(
        self,
        results: Dict[str, Any]
    ) -> str:
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
