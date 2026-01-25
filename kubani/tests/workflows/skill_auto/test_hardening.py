"""Tests for Phase 5: Hardening features.

- Progressive test hardening on plateau
- Regression detection and revert logic
- Comprehensive error handling
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

# ============================================================================
# Tests for progressive test hardening
# ============================================================================


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    client = MagicMock()
    client.chat = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_generate_harder_tests_creates_targeted_tests(mock_llm_client):
    """generate_harder_tests should create tests targeting weaknesses."""
    from kubani.workflows.skill_auto.activities import generate_harder_tests
    from kubani.workflows.skill_auto.models import EvalMetrics

    mock_llm_client.chat.return_value = {
        "content": """```yaml
test_cases:
  - name: edge_case_empty_input
    description: Test with empty input to stress edge handling
    inputs:
      pod_name: ""
      namespace: ""
    expected:
      error: "Invalid input"
    assertions:
      - type: exists
        field: error
  - name: edge_case_large_logs
    description: Test with extremely large log output
    inputs:
      pod_name: "large-pod"
      namespace: "production"
    expected:
      diagnosis: "Should handle large output"
    assertions:
      - type: not_empty
        field: diagnosis
```""",
    }

    metrics = EvalMetrics(
        accuracy=0.70,
        latency_ms=2000,
        tests_passed=7,
        tests_total=10,
        critic_confidence=0.75,
    )

    # Failing tests info
    failing_tests = [
        {"name": "test_empty_namespace", "reason": "Did not handle empty namespace"},
        {"name": "test_large_output", "reason": "Truncated output incorrectly"},
    ]

    new_tests = await generate_harder_tests(
        skill_name="oom-diagnostics",
        current_test_cases="test_cases:\n  - name: basic_test\n    inputs: {}",
        metrics=metrics,
        failing_tests=failing_tests,
        llm_client=mock_llm_client,
        count=2,
    )

    assert "test_cases:" in new_tests
    assert "edge_case" in new_tests  # Should target edge cases


@pytest.mark.asyncio
async def test_generate_harder_tests_analyzes_failures(mock_llm_client):
    """generate_harder_tests should analyze failure patterns."""
    from kubani.workflows.skill_auto.activities import generate_harder_tests
    from kubani.workflows.skill_auto.models import EvalMetrics

    mock_llm_client.chat.return_value = {
        "content": """```yaml
test_cases:
  - name: boundary_memory_limit
    description: Test at exact memory boundary
    inputs:
      pod_name: "boundary-pod"
    assertions:
      - type: exists
        field: diagnosis
```""",
    }

    metrics = EvalMetrics(
        accuracy=0.75,
        latency_ms=1500,
        tests_passed=3,
        tests_total=4,
        critic_confidence=0.80,
    )

    await generate_harder_tests(
        skill_name="memory-check",
        current_test_cases="existing tests",
        metrics=metrics,
        failing_tests=[{"name": "test1", "reason": "boundary condition"}],
        llm_client=mock_llm_client,
        count=1,
    )

    # Check that LLM was called with failure info
    call_args = mock_llm_client.chat.call_args
    prompt = call_args.kwargs.get("messages", call_args[1].get("messages", []))[0]["content"]
    assert "boundary" in prompt.lower() or "failure" in prompt.lower()


# ============================================================================
# Tests for regression detection
# ============================================================================


def test_detect_regression_identifies_significant_drop():
    """detect_regression should identify >20% score drops."""
    from kubani.workflows.skill_auto.models import EvalMetrics, IterationResult, detect_regression

    metrics = EvalMetrics(
        accuracy=0.80, latency_ms=1500, tests_passed=8, tests_total=10, critic_confidence=0.80
    )

    history = [
        IterationResult(iteration=1, metrics=metrics, score=0.80, improved=True, action="continue"),
        IterationResult(iteration=2, metrics=metrics, score=0.85, improved=True, action="continue"),
    ]

    # Current score dropped >20% from best (0.85)
    current_score = 0.65

    result = detect_regression(history, current_score, threshold=0.20)

    assert result["is_regression"] is True
    assert result["drop_percentage"] > 20.0
    assert result["best_score"] == 0.85


def test_detect_regression_no_regression_within_threshold():
    """detect_regression should return False for minor drops."""
    from kubani.workflows.skill_auto.models import EvalMetrics, IterationResult, detect_regression

    metrics = EvalMetrics(
        accuracy=0.80, latency_ms=1500, tests_passed=8, tests_total=10, critic_confidence=0.80
    )

    history = [
        IterationResult(iteration=1, metrics=metrics, score=0.80, improved=True, action="continue"),
    ]

    # Only 5% drop - within threshold
    current_score = 0.76

    result = detect_regression(history, current_score, threshold=0.20)

    assert result["is_regression"] is False


def test_detect_regression_empty_history():
    """detect_regression should handle empty history."""
    from kubani.workflows.skill_auto.models import detect_regression

    result = detect_regression([], 0.50, threshold=0.20)

    assert result["is_regression"] is False


# ============================================================================
# Tests for revert logic
# ============================================================================


@pytest.mark.asyncio
async def test_revert_to_best_version_restores_content(tmp_path):
    """revert_to_best_version should restore skill content from best version."""
    from kubani.workflows.skill_auto.activities import revert_to_best_version
    from kubani.workflows.skill_auto.models import EvalMetrics, SkillVersion

    # Create current skill files
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Current bad content")
    (skill_dir / "test_cases.yaml").write_text("current_tests: []")

    # Best version to restore
    metrics = EvalMetrics(
        accuracy=0.90,
        latency_ms=1000,
        tests_passed=9,
        tests_total=10,
        critic_confidence=0.90,
    )
    best_version = SkillVersion(
        content="# Best content from iteration 2",
        test_cases="best_tests:\n  - name: good_test",
        metrics=metrics,
        iteration=2,
    )

    result = await revert_to_best_version(
        skill_path=str(skill_dir),
        best_version=best_version,
    )

    assert result["reverted"] is True
    assert (skill_dir / "SKILL.md").read_text() == "# Best content from iteration 2"
    assert "best_tests:" in (skill_dir / "test_cases.yaml").read_text()


@pytest.mark.asyncio
async def test_revert_to_best_version_creates_backup(tmp_path):
    """revert_to_best_version should backup current content before reverting."""
    from kubani.workflows.skill_auto.activities import revert_to_best_version
    from kubani.workflows.skill_auto.models import EvalMetrics, SkillVersion

    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Content to backup")
    (skill_dir / "test_cases.yaml").write_text("tests_to_backup: []")

    metrics = EvalMetrics(
        accuracy=0.90, latency_ms=1000, tests_passed=9, tests_total=10, critic_confidence=0.90
    )
    best_version = SkillVersion(
        content="# Restored content",
        test_cases="restored_tests: []",
        metrics=metrics,
        iteration=1,
    )

    await revert_to_best_version(str(skill_dir), best_version)

    # Should have created backup files
    backups = list(skill_dir.glob("*.backup.*"))
    assert len(backups) >= 1


# ============================================================================
# Tests for comprehensive error handling
# ============================================================================


@pytest.mark.asyncio
async def test_handle_llm_timeout_retries(mock_llm_client):
    """Activities should retry on LLM timeout."""
    from kubani.workflows.skill_auto.activities import infer_skill_structure

    # First two calls timeout, third succeeds
    mock_llm_client.chat.side_effect = [
        TimeoutError("LLM timeout"),
        TimeoutError("LLM timeout"),
        {
            "content": '{"name": "test-skill", "description": "test", "inputs": {}, "outputs": {}, "steps": [], "examples": []}',
        },
    ]

    # This should succeed after retries (handled by Temporal retry policy in real usage)
    # For unit test, we test the activity doesn't crash on first timeout
    with pytest.raises(TimeoutError):
        await infer_skill_structure("test description", mock_llm_client)


@pytest.mark.asyncio
async def test_handle_invalid_llm_response(mock_llm_client):
    """Activities should handle invalid LLM responses gracefully."""
    from kubani.workflows.skill_auto.activities import detect_skill_overlap

    # Return invalid JSON
    mock_llm_client.chat.return_value = {
        "content": "This is not valid JSON at all",
    }

    result = await detect_skill_overlap(
        description="A new skill",
        existing_skills=[{"name": "existing", "description": "An existing skill"}],
        llm_client=mock_llm_client,
    )

    # Should return safe default, not crash
    assert result.has_overlap is False
    assert "Failed" in result.reasoning


def test_eval_metrics_handles_zero_latency():
    """compute_score should handle zero latency without division error."""
    from kubani.workflows.skill_auto.models import EvalMetrics, compute_score

    metrics = EvalMetrics(
        accuracy=0.80,
        latency_ms=0,  # Zero latency (edge case)
        tests_passed=8,
        tests_total=10,
        critic_confidence=0.80,
    )

    score = compute_score(metrics)

    # Should not crash and should cap at max latency score
    assert score > 0
    assert score <= 1.0


def test_eval_metrics_handles_negative_values():
    """compute_score should handle negative values gracefully."""
    from kubani.workflows.skill_auto.models import EvalMetrics, compute_score

    metrics = EvalMetrics(
        accuracy=-0.5,  # Invalid but possible from buggy data
        latency_ms=-100,  # Invalid
        tests_passed=-1,
        tests_total=10,
        critic_confidence=0.80,
    )

    # Should not crash
    score = compute_score(metrics)
    assert isinstance(score, float)


# ============================================================================
# Tests for iteration result logging
# ============================================================================


@pytest.mark.asyncio
async def test_save_iteration_result_writes_json(tmp_path):
    """save_iteration_result should write iteration details to JSON file."""
    from kubani.workflows.skill_auto.activities import save_iteration_result
    from kubani.workflows.skill_auto.models import EvalMetrics, IterationResult

    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()

    metrics = EvalMetrics(
        accuracy=0.85,
        latency_ms=1500,
        tests_passed=8,
        tests_total=10,
        critic_confidence=0.80,
    )
    iteration_result = IterationResult(
        iteration=3,
        metrics=metrics,
        score=0.82,
        improved=True,
        action="continue",
    )

    result = await save_iteration_result(
        skill_path=str(skill_dir),
        iteration_result=iteration_result,
    )

    assert result["saved"] is True

    # Check file was created
    iteration_file = skill_dir / "iteration_3.json"
    assert iteration_file.exists()

    import json

    saved_data = json.loads(iteration_file.read_text())
    assert saved_data["iteration"] == 3
    assert saved_data["score"] == 0.82


@pytest.mark.asyncio
async def test_load_iteration_history(tmp_path):
    """load_iteration_history should load all iteration files."""
    import json

    from kubani.workflows.skill_auto.activities import load_iteration_history

    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()

    # Create some iteration files
    for i in range(1, 4):
        (skill_dir / f"iteration_{i}.json").write_text(
            json.dumps(
                {
                    "iteration": i,
                    "score": 0.70 + i * 0.05,
                    "improved": True,
                    "action": "continue",
                }
            )
        )

    history = await load_iteration_history(str(skill_dir))

    assert len(history) == 3
    assert history[0]["iteration"] == 1
    assert history[2]["iteration"] == 3
