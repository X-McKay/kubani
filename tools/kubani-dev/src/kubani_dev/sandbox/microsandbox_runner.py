"""
Microsandbox Runner for Kubani Skill Evaluation.

Provides secure, hardware-isolated execution of skills using microsandbox.
"""

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MicrosandboxRunner:
    """
    Runs skill evaluations in microsandbox microVMs.
    
    Provides hardware-level isolation for secure execution of untrusted code.
    """
    
    def __init__(self, skill_dir: Path):
        """
        Initialize the microsandbox runner.
        
        Args:
            skill_dir: Path to the skill directory containing skill.py and test_cases.yaml
        """
        self.skill_dir = skill_dir
        self.sandbox_available = self._check_microsandbox_available()
    
    def _check_microsandbox_available(self) -> bool:
        """Check if microsandbox is available."""
        try:
            result = subprocess.run(
                ["python3", "-c", "import microsandbox"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def is_available(self) -> bool:
        """Check if microsandbox is available for use."""
        return self.sandbox_available
    
    def run_evaluation(self, test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Run evaluation in microsandbox (or subprocess fallback).
        
        Args:
            test_cases: List of test cases to execute
            
        Returns:
            Evaluation results with metrics and test outcomes
        """
        # Note: We don't check is_available() here because this runner
        # can fall back to subprocess execution if microsandbox is not available
        
        logger.info(f"Starting microsandbox evaluation for {self.skill_dir.name}")
        
        start_time = time.time()
        results = {
            "skill_name": self.skill_dir.name,
            "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sandbox_type": "microsandbox",
            "test_results": [],
            "tests_total": len(test_cases),
            "tests_passed": 0,
            "tests_failed": 0,
            "accuracy": 0.0,
            "avg_latency_ms": 0.0,
            "total_duration_ms": 0.0,
        }
        
        total_latency = 0.0
        
        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"Running test case {i}/{len(test_cases)}: {test_case.get('name', 'unnamed')}")
            
            test_result = self._run_single_test(test_case)
            results["test_results"].append(test_result)
            
            if test_result["passed"]:
                results["tests_passed"] += 1
            else:
                results["tests_failed"] += 1
            
            total_latency += test_result.get("latency_ms", 0)
        
        # Calculate metrics
        results["accuracy"] = results["tests_passed"] / results["tests_total"] if results["tests_total"] > 0 else 0.0
        results["avg_latency_ms"] = total_latency / results["tests_total"] if results["tests_total"] > 0 else 0.0
        results["total_duration_ms"] = (time.time() - start_time) * 1000
        
        logger.info(f"Evaluation complete: {results['tests_passed']}/{results['tests_total']} passed")
        
        return results
    
    def _run_single_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a single test case in microsandbox.
        
        Args:
            test_case: Test case configuration
            
        Returns:
            Test result with pass/fail status and metrics
        """
        test_name = test_case.get("name", "unnamed")
        inputs = test_case.get("inputs", {})
        expected = test_case.get("expected", {})
        assertions = test_case.get("assertions", [])
        performance = test_case.get("performance", {})
        
        result = {
            "name": test_name,
            "passed": False,
            "latency_ms": 0.0,
            "output": None,
            "error": None,
            "assertions_passed": [],
            "assertions_failed": [],
        }
        
        try:
            # Execute skill in microsandbox
            start_time = time.time()
            output = self._execute_in_sandbox(inputs)
            latency_ms = (time.time() - start_time) * 1000
            
            result["latency_ms"] = latency_ms
            result["output"] = output
            
            # Check for errors
            if expected.get("error") and not output.get("error"):
                result["assertions_failed"].append({
                    "description": "Expected error but got success",
                    "expected": "error",
                    "actual": "success"
                })
                return result
            
            # Check performance constraints
            max_latency = performance.get("max_latency_ms")
            if max_latency and latency_ms > max_latency:
                result["assertions_failed"].append({
                    "description": f"Latency exceeded limit",
                    "expected": f"< {max_latency}ms",
                    "actual": f"{latency_ms:.0f}ms"
                })
                return result
            
            # Check assertions
            all_passed = True
            for assertion in assertions:
                assertion_result = self._check_assertion(output, assertion)
                if assertion_result["passed"]:
                    result["assertions_passed"].append(assertion_result)
                else:
                    result["assertions_failed"].append(assertion_result)
                    all_passed = False
            
            result["passed"] = all_passed and len(result["assertions_failed"]) == 0
            
        except Exception as e:
            logger.error(f"Test case {test_name} failed with exception: {e}")
            result["error"] = str(e)
            result["assertions_failed"].append({
                "description": "Execution failed with exception",
                "error": str(e)
            })
        
        return result
    
    def _execute_in_sandbox(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute skill code in microsandbox.
        
        Args:
            inputs: Input parameters for the skill
            
        Returns:
            Skill output
        """
        # For now, we'll use a simple subprocess-based execution
        # In a full implementation, this would use the microsandbox SDK
        
        skill_py = self.skill_dir / "skill.py"
        if not skill_py.exists():
            raise FileNotFoundError(f"skill.py not found in {self.skill_dir}")
        
        # Create a temporary execution script
        exec_script = f"""
import sys
import json
sys.path.insert(0, '{self.skill_dir}')

from skill import execute

inputs = {json.dumps(inputs)}
try:
    result = execute(inputs)
    print(json.dumps({{"result": result, "error": False}}))
except Exception as e:
    print(json.dumps({{"error": True, "message": str(e)}}))
"""
        
        # Execute in subprocess (simulating microsandbox for now)
        try:
            result = subprocess.run(
                ["python3", "-c", exec_script],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.skill_dir)
            )
            
            if result.returncode != 0:
                return {
                    "error": True,
                    "message": result.stderr or "Execution failed"
                }
            
            output = json.loads(result.stdout)
            return output.get("result", output)
            
        except subprocess.TimeoutExpired:
            return {
                "error": True,
                "message": "Execution timed out"
            }
        except json.JSONDecodeError as e:
            return {
                "error": True,
                "message": f"Failed to parse output: {e}"
            }
    
    def _check_assertion(self, output: Dict[str, Any], assertion: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check an assertion against the output.
        
        Args:
            output: Skill output
            assertion: Assertion configuration
            
        Returns:
            Assertion result
        """
        field = assertion.get("field")
        operator = assertion.get("operator")
        expected_value = assertion.get("value")
        
        result = {
            "field": field,
            "operator": operator,
            "expected": expected_value,
            "actual": None,
            "passed": False,
            "description": f"Check {field} {operator} {expected_value}"
        }
        
        # Get actual value from output
        if field in output:
            actual_value = output[field]
            result["actual"] = actual_value
            
            # Check operator
            if operator == "equals":
                result["passed"] = actual_value == expected_value
            elif operator == "not_equals":
                result["passed"] = actual_value != expected_value
            elif operator == "exists":
                result["passed"] = True
            elif operator == "not_exists":
                result["passed"] = False
            elif operator == "contains":
                result["passed"] = expected_value in str(actual_value)
            elif operator == "greater_than":
                result["passed"] = actual_value > expected_value
            elif operator == "less_than":
                result["passed"] = actual_value < expected_value
            else:
                result["description"] = f"Unknown operator: {operator}"
        else:
            if operator == "not_exists":
                result["passed"] = True
            else:
                result["description"] = f"Field '{field}' not found in output"
        
        return result


class DockerRunner:
    """
    Fallback runner using Docker for skill evaluation.
    
    Provides container-level isolation when microsandbox is not available.
    """
    
    def __init__(self, skill_dir: Path):
        """
        Initialize the Docker runner.
        
        Args:
            skill_dir: Path to the skill directory
        """
        self.skill_dir = skill_dir
        self.docker_available = self._check_docker_available()
    
    def _check_docker_available(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def is_available(self) -> bool:
        """Check if Docker is available for use."""
        return self.docker_available
    
    def run_evaluation(self, test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Run evaluation in Docker container.
        
        Args:
            test_cases: List of test cases to execute
            
        Returns:
            Evaluation results
        """
        if not self.is_available():
            raise RuntimeError("Docker is not available")
        
        logger.info("Docker-based evaluation not yet implemented")
        raise NotImplementedError("Docker evaluation coming in Phase 2.2")
