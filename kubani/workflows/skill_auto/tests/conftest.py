"""Shared test fixtures for skill_auto tests."""

import pytest

from kubani.workflows.skill_auto.models import EvalMetrics, IterationResult


@pytest.fixture
def sample_metrics() -> EvalMetrics:
    """Sample evaluation metrics for testing."""
    return EvalMetrics(
        accuracy=0.8,
        latency_ms=1500.0,
        tests_passed=4,
        tests_total=5,
        critic_confidence=0.85,
        tokens_prompt=1000,
        tokens_completion=500,
    )


@pytest.fixture
def perfect_metrics() -> EvalMetrics:
    """Perfect evaluation metrics."""
    return EvalMetrics(
        accuracy=1.0,
        latency_ms=100.0,
        tests_passed=5,
        tests_total=5,
        critic_confidence=1.0,
        tokens_prompt=800,
        tokens_completion=400,
    )


@pytest.fixture
def poor_metrics() -> EvalMetrics:
    """Poor evaluation metrics."""
    return EvalMetrics(
        accuracy=0.2,
        latency_ms=5000.0,
        tests_passed=1,
        tests_total=5,
        critic_confidence=0.3,
        tokens_prompt=2000,
        tokens_completion=1000,
    )


@pytest.fixture
def iteration_history() -> list[IterationResult]:
    """Sample iteration history for plateau/regression testing."""
    return [
        IterationResult(
            iteration=1,
            metrics=EvalMetrics(
                accuracy=0.6,
                latency_ms=2000.0,
                tests_passed=3,
                tests_total=5,
                critic_confidence=0.7,
            ),
            score=0.6,
            improved=True,
            action="continue",
        ),
        IterationResult(
            iteration=2,
            metrics=EvalMetrics(
                accuracy=0.7,
                latency_ms=1800.0,
                tests_passed=3,
                tests_total=5,
                critic_confidence=0.75,
            ),
            score=0.7,
            improved=True,
            action="continue",
        ),
        IterationResult(
            iteration=3,
            metrics=EvalMetrics(
                accuracy=0.75,
                latency_ms=1600.0,
                tests_passed=4,
                tests_total=5,
                critic_confidence=0.8,
            ),
            score=0.75,
            improved=True,
            action="continue",
        ),
    ]


@pytest.fixture
def plateau_history() -> list[IterationResult]:
    """History showing plateau (minimal improvement)."""
    return [
        IterationResult(
            iteration=1,
            metrics=EvalMetrics(
                accuracy=0.8,
                latency_ms=1500.0,
                tests_passed=4,
                tests_total=5,
                critic_confidence=0.8,
            ),
            score=0.80,
            improved=True,
            action="continue",
        ),
        IterationResult(
            iteration=2,
            metrics=EvalMetrics(
                accuracy=0.805,
                latency_ms=1490.0,
                tests_passed=4,
                tests_total=5,
                critic_confidence=0.8,
            ),
            score=0.805,
            improved=True,
            action="continue",
        ),
        IterationResult(
            iteration=3,
            metrics=EvalMetrics(
                accuracy=0.808,
                latency_ms=1485.0,
                tests_passed=4,
                tests_total=5,
                critic_confidence=0.8,
            ),
            score=0.808,
            improved=True,
            action="continue",
        ),
    ]


@pytest.fixture
def sample_skill_spec() -> dict:
    """Sample skill specification for testing."""
    return {
        "name": "diagnose-oom",
        "description": "Diagnose OOMKilled pod issues in Kubernetes",
        "inputs": {
            "pod_name": {
                "type": "string",
                "description": "Name of the pod",
                "required": True,
            },
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace",
                "required": False,
            },
        },
        "outputs": {
            "diagnosis": {
                "type": "string",
                "description": "Diagnosis of the OOM issue",
            },
            "recommendations": {
                "type": "array",
                "description": "List of recommendations",
            },
        },
        "steps": [
            "Check pod events for OOMKilled status",
            "Analyze container memory limits",
            "Review application memory usage patterns",
            "Provide recommendations for fixing",
        ],
        "error_handling": [
            "Handle case when pod not found",
            "Handle permission errors",
        ],
        "triggers": ["oom_killed", "memory_pressure"],
    }


@pytest.fixture
def valid_test_cases_yaml() -> str:
    """Valid test cases YAML for testing."""
    return """test_cases:
  - name: basic_oom_diagnosis
    description: Test basic OOM diagnosis
    inputs:
      pod_name: my-pod
      namespace: default
    expected:
      diagnosis: contains memory limit exceeded
    assertions:
      - type: exists
        field: diagnosis
      - type: not_empty
        field: recommendations

  - name: missing_pod
    description: Test handling of missing pod
    inputs:
      pod_name: nonexistent-pod
    expected:
      error: true
    assertions:
      - type: exists
        field: error
"""


@pytest.fixture
def invalid_test_cases_yaml() -> str:
    """Invalid test cases YAML (missing name field)."""
    return """test_cases:
  - description: Test without name
    inputs:
      pod_name: my-pod
"""
