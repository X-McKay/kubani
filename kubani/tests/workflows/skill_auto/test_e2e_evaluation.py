"""End-to-end evaluation tests for the LLM-based skill evaluation pipeline.

These tests verify the full evaluation pipeline works with real LLM calls.
They require an LLM endpoint to be accessible.

Run with:
    RUN_E2E_TESTS=1 pytest kubani/workflows/skill_auto/tests/test_e2e_evaluation.py -v -s

Or run directly:
    python kubani/workflows/skill_auto/tests/test_e2e_evaluation.py
"""

import asyncio
import logging
import os
from pathlib import Path

import pytest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Skip if not running E2E tests
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_E2E_TESTS"),
    reason="E2E tests require RUN_E2E_TESTS=1 environment variable",
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def complex_skill_dir(tmp_path):
    """Create a complex skill for testing."""
    skill_dir = tmp_path / "json-processor"
    skill_dir.mkdir()

    # Create SKILL.md with complex requirements
    skill_md = """---
category: _development
description: Processes JSON data with validation and transformation
name: json-processor
version: 0.1.0
---

# JSON Processor

A skill that processes JSON data by validating structure and transforming values.

## Purpose

This skill takes JSON input and performs various operations:
- Validates that the input is valid JSON
- Extracts specified fields
- Transforms values according to rules

## Inputs

- **json_data** (string) (required): The JSON string to process
- **operation** (string) (required): The operation to perform (validate, extract, transform)
- **field** (string) (optional): The field to extract (for extract operation)
- **transform_rule** (string) (optional): The transformation rule (for transform operation)

## Outputs

Your response MUST be valid JSON with these fields:
- **success** (boolean): Whether the operation succeeded
- **result** (any): The result of the operation
- **error** (string, optional): Error message if operation failed

## Operations

### validate
Check if the input is valid JSON. Return `{"success": true, "result": "valid"}` if valid.

### extract
Extract a specific field from the JSON. Return `{"success": true, "result": <field_value>}`.
If field doesn't exist, return `{"success": false, "error": "field not found"}`.

### transform
Apply a transformation rule to all string values. Supported rules:
- `uppercase`: Convert all string values to uppercase
- `lowercase`: Convert all string values to lowercase

Return the transformed JSON object.

## Examples

Input:
```
json_data: '{"name": "Alice", "age": 30}'
operation: extract
field: name
```

Output:
```json
{"success": true, "result": "Alice"}
```

## Error Handling

- Invalid JSON input: Return `{"success": false, "error": "invalid JSON"}`
- Unknown operation: Return `{"success": false, "error": "unknown operation"}`
- Missing required field: Return `{"success": false, "error": "missing required field: <field>"}`
"""
    (skill_dir / "SKILL.md").write_text(skill_md)

    # Create test_cases.yaml with various test scenarios
    test_cases = """test_cases:
  - name: validate_valid_json
    description: Validate a valid JSON object
    inputs:
      json_data: '{"name": "Alice", "age": 30}'
      operation: validate
    expected:
      success: true
      result: "valid"
    assertions:
      - type: exists
        field: success
        description: Response should have success field
      - type: equals
        field: success
        value: true
        description: Valid JSON should succeed

  - name: validate_invalid_json
    description: Validate an invalid JSON string
    inputs:
      json_data: '{invalid json}'
      operation: validate
    expected:
      success: false
      error: "invalid JSON"
    assertions:
      - type: equals
        field: success
        value: false
        description: Invalid JSON should fail

  - name: extract_existing_field
    description: Extract an existing field from JSON
    inputs:
      json_data: '{"name": "Bob", "email": "bob@example.com"}'
      operation: extract
      field: email
    expected:
      success: true
      result: "bob@example.com"
    assertions:
      - type: equals
        field: success
        value: true
        description: Extraction should succeed
      - type: equals
        field: result
        value: "bob@example.com"
        description: Should extract correct value

  - name: extract_missing_field
    description: Attempt to extract a non-existent field
    inputs:
      json_data: '{"name": "Charlie"}'
      operation: extract
      field: age
    expected:
      success: false
      error: "field not found"
    assertions:
      - type: equals
        field: success
        value: false
        description: Missing field should fail
      - type: contains
        field: error
        value: "not found"
        description: Error should indicate field not found

  - name: transform_uppercase
    description: Transform string values to uppercase
    inputs:
      json_data: '{"greeting": "hello", "name": "world"}'
      operation: transform
      transform_rule: uppercase
    expected:
      success: true
    assertions:
      - type: equals
        field: success
        value: true
        description: Transform should succeed
      - type: exists
        field: result
        description: Should return transformed result

  - name: unknown_operation
    description: Handle unknown operation gracefully
    inputs:
      json_data: '{"test": true}'
      operation: delete
    expected:
      success: false
      error: "unknown operation"
    assertions:
      - type: equals
        field: success
        value: false
        description: Unknown operation should fail
      - type: contains
        field: error
        value: "unknown"
        description: Error should indicate unknown operation
"""
    (skill_dir / "test_cases.yaml").write_text(test_cases)

    # Create metadata.json
    metadata = """{
  "name": "json-processor",
  "version": "0.1.0",
  "category": "_development",
  "created_at": "2026-01-26T00:00:00Z"
}"""
    (skill_dir / "metadata.json").write_text(metadata)

    return skill_dir


@pytest.fixture
def simple_skill_path():
    """Return path to the existing sum-two-numbers skill."""
    return (
        Path(__file__).parent.parent.parent.parent / "skills" / "_development" / "sum-two-numbers"
    )


# =============================================================================
# Quick Mode Tests
# =============================================================================


class TestQuickEvaluation:
    """Tests for quick (single-config) evaluation mode."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_quick_evaluation_simple_skill(self, simple_skill_path):
        """Test quick evaluation on a simple skill."""
        from kubani.workflows.skill_auto.capabilities.evaluate_skill import evaluate_skill

        if not simple_skill_path.exists():
            pytest.skip(f"Skill not found: {simple_skill_path}")

        logger.info(f"Running quick evaluation on: {simple_skill_path}")

        metrics, feedback = await evaluate_skill(
            str(simple_skill_path),
            mode="quick",
            enable_critic=False,  # Disable critic for faster test
        )

        logger.info(
            f"Metrics: accuracy={metrics.accuracy:.1%}, tests={metrics.tests_passed}/{metrics.tests_total}"
        )
        logger.info(f"Feedback:\n{feedback}")

        # Verify we got results
        assert metrics.tests_total > 0, "Should have run at least one test"
        assert metrics.accuracy >= 0.0, "Accuracy should be non-negative"
        assert metrics.latency_ms > 0, "Should have measured latency"

        # The feedback should contain useful information
        assert "Accuracy" in feedback or "accuracy" in feedback.lower()

    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_quick_evaluation_complex_skill(self, complex_skill_dir):
        """Test quick evaluation on a complex skill."""
        from kubani.workflows.skill_auto.capabilities.evaluate_skill import evaluate_skill

        logger.info(f"Running quick evaluation on complex skill: {complex_skill_dir}")

        metrics, feedback = await evaluate_skill(
            str(complex_skill_dir),
            mode="quick",
            enable_critic=False,
        )

        logger.info(
            f"Metrics: accuracy={metrics.accuracy:.1%}, tests={metrics.tests_passed}/{metrics.tests_total}"
        )
        logger.info(f"Feedback:\n{feedback}")

        # Should have run all test cases
        assert metrics.tests_total == 6, f"Expected 6 tests, got {metrics.tests_total}"

        # Even if some fail, we should get valid results
        assert 0.0 <= metrics.accuracy <= 1.0, "Accuracy should be between 0 and 1"


# =============================================================================
# Full Mode Tests
# =============================================================================


class TestFullEvaluation:
    """Tests for full (multi-config matrix) evaluation mode."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(300)
    async def test_full_evaluation_parallel(self, simple_skill_path):
        """Test full evaluation with parallel execution."""
        from kubani.workflows.skill_auto.capabilities.evaluate_skill import evaluate_skill

        if not simple_skill_path.exists():
            pytest.skip(f"Skill not found: {simple_skill_path}")

        logger.info(f"Running full evaluation (parallel) on: {simple_skill_path}")

        metrics, feedback = await evaluate_skill(
            str(simple_skill_path),
            mode="full",
            parallel=True,
            enable_critic=False,
        )

        logger.info(f"Best config metrics: accuracy={metrics.accuracy:.1%}")
        logger.info(f"Comparison table:\n{feedback}")

        # Should have results from multiple configurations
        assert "Configuration" in feedback or "config" in feedback.lower()
        assert metrics.tests_total > 0

    @pytest.mark.asyncio
    @pytest.mark.timeout(600)
    async def test_full_evaluation_sequential(self, simple_skill_path):
        """Test full evaluation with sequential execution."""
        from kubani.workflows.skill_auto.capabilities.evaluate_skill import evaluate_skill

        if not simple_skill_path.exists():
            pytest.skip(f"Skill not found: {simple_skill_path}")

        logger.info(f"Running full evaluation (sequential) on: {simple_skill_path}")

        metrics, feedback = await evaluate_skill(
            str(simple_skill_path),
            mode="full",
            parallel=False,
            enable_critic=False,
        )

        logger.info(f"Best config metrics: accuracy={metrics.accuracy:.1%}")

        assert metrics.tests_total > 0


# =============================================================================
# Critic Evaluation Tests
# =============================================================================


class TestCriticEvaluation:
    """Tests for LLM-as-judge critic evaluation."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_evaluation_with_critic(self, simple_skill_path):
        """Test evaluation with critic enabled."""
        from kubani.workflows.skill_auto.capabilities.evaluate_skill import evaluate_skill

        if not simple_skill_path.exists():
            pytest.skip(f"Skill not found: {simple_skill_path}")

        logger.info(f"Running evaluation with critic on: {simple_skill_path}")

        metrics, feedback = await evaluate_skill(
            str(simple_skill_path),
            mode="quick",
            enable_critic=True,
        )

        logger.info(
            f"Metrics with critic: accuracy={metrics.accuracy:.1%}, critic_confidence={metrics.critic_confidence:.1%}"
        )
        logger.info(f"Feedback:\n{feedback}")

        # Critic confidence should be set when critic is enabled
        # Note: It might be 0.0 if all tests pass without needing critic
        assert metrics.critic_confidence >= 0.0


# =============================================================================
# Orchestrator Tests
# =============================================================================


class TestEvalOrchestrator:
    """Tests for the evaluation orchestrator."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_orchestrator_quick_mode(self, simple_skill_path):
        """Test orchestrator in quick mode directly."""
        from kubani.workflows.skill_auto.capabilities.eval_orchestrator import EvalOrchestrator

        if not simple_skill_path.exists():
            pytest.skip(f"Skill not found: {simple_skill_path}")

        orchestrator = EvalOrchestrator(enable_critic=False)

        result = await orchestrator.run_quick(simple_skill_path)

        logger.info(f"Config: {result.config.display_name}")
        logger.info(f"Accuracy: {result.accuracy:.1%}")
        logger.info(f"Tests: {result.tests_passed}/{result.tests_total}")

        assert result.error is None, f"Evaluation failed: {result.error}"
        assert result.tests_total > 0

    @pytest.mark.asyncio
    @pytest.mark.timeout(300)
    async def test_orchestrator_full_mode(self, simple_skill_path):
        """Test orchestrator in full mode directly."""
        from kubani.workflows.skill_auto.capabilities.eval_orchestrator import EvalOrchestrator

        if not simple_skill_path.exists():
            pytest.skip(f"Skill not found: {simple_skill_path}")

        orchestrator = EvalOrchestrator(enable_critic=False)

        report = await orchestrator.run_full(simple_skill_path, parallel=True)

        logger.info(f"Skill: {report.skill_name}")
        logger.info(f"Configurations tested: {len(report.configurations)}")

        for config_name in report.configurations:
            result = report.get_result(config_name)
            if result and not result.error:
                logger.info(f"  {config_name}: {result.accuracy:.1%}")
            else:
                logger.info(f"  {config_name}: ERROR")

        rankings = report.get_rankings()
        logger.info(f"Best accuracy: {rankings.get('accuracy', ['N/A'])[0]}")

        # Should have tested multiple configurations
        assert len(report.configurations) >= 2


# =============================================================================
# Reporter Tests
# =============================================================================


class TestEvalReporter:
    """Tests for report generation with real data."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_save_evaluation_report(self, simple_skill_path, tmp_path):
        """Test saving evaluation results to files."""
        from kubani.workflows.skill_auto.capabilities.eval_orchestrator import EvalOrchestrator
        from kubani.workflows.skill_auto.capabilities.eval_reporter import EvalReporter

        if not simple_skill_path.exists():
            pytest.skip(f"Skill not found: {simple_skill_path}")

        orchestrator = EvalOrchestrator(enable_critic=False)
        reporter = EvalReporter()

        result = await orchestrator.run_quick(simple_skill_path)

        # Save report
        saved_files = reporter.save_report(result, tmp_path)

        # Verify all formats were saved
        assert "json" in saved_files
        assert "md" in saved_files
        assert "txt" in saved_files

        # Verify JSON content
        import json

        with open(saved_files["json"]) as f:
            data = json.load(f)

        assert "metrics" in data
        assert "config" in data
        logger.info(f"Saved reports to: {tmp_path}")


# =============================================================================
# Direct Execution
# =============================================================================


async def run_manual_test():
    """Run a manual test for quick verification."""
    from kubani.workflows.skill_auto.capabilities.evaluate_skill import evaluate_skill

    skill_path = (
        Path(__file__).parent.parent.parent.parent / "skills" / "_development" / "sum-two-numbers"
    )

    if not skill_path.exists():
        logger.error(f"Skill not found: {skill_path}")
        return

    logger.info("=" * 60)
    logger.info("Running manual E2E evaluation test")
    logger.info("=" * 60)

    # Quick mode
    logger.info("\n--- Quick Mode (single config) ---")
    metrics, feedback = await evaluate_skill(str(skill_path), mode="quick", enable_critic=False)
    logger.info(f"Accuracy: {metrics.accuracy:.1%}")
    logger.info(f"Tests: {metrics.tests_passed}/{metrics.tests_total}")
    logger.info(f"Latency: {metrics.latency_ms:.0f}ms")
    logger.info(f"\nFeedback:\n{feedback}")

    # Full mode
    logger.info("\n--- Full Mode (4-config matrix) ---")
    metrics, feedback = await evaluate_skill(
        str(skill_path), mode="full", parallel=True, enable_critic=False
    )
    logger.info(f"Best accuracy: {metrics.accuracy:.1%}")
    logger.info(f"\nComparison:\n{feedback}")

    logger.info("\n" + "=" * 60)
    logger.info("E2E test completed successfully!")
    logger.info("=" * 60)


if __name__ == "__main__":
    os.environ["RUN_E2E_TESTS"] = "1"
    asyncio.run(run_manual_test())
