"""Tests for skill auto workflow data models."""



def test_skill_auto_input_defaults():
    """SkillAutoInput should have sensible defaults."""
    from kubani.workflows.skill_auto.models import SkillAutoInput

    input = SkillAutoInput(description="A skill that diagnoses OOM pods")

    assert input.description == "A skill that diagnoses OOM pods"
    assert input.mode == "create"
    assert input.max_iterations == 5
    assert input.target_accuracy == 0.80
    assert input.notify_channel == "skill-notifications"
    assert input.allow_overlap is False


def test_skill_auto_input_improve_mode():
    """SkillAutoInput should support improve mode with skill_path."""
    from kubani.workflows.skill_auto.models import SkillAutoInput

    input = SkillAutoInput(
        description="Improve existing skill",
        mode="improve",
        skill_path="kubani/skills/_development/oom-diagnostics",
    )

    assert input.mode == "improve"
    assert input.skill_path == "kubani/skills/_development/oom-diagnostics"


def test_skill_version_stores_content_and_metrics():
    """SkillVersion should store skill content and evaluation metrics."""
    from kubani.workflows.skill_auto.models import EvalMetrics, SkillVersion

    metrics = EvalMetrics(
        accuracy=0.85,
        latency_ms=2100.0,
        tests_passed=4,
        tests_total=5,
        critic_confidence=0.78,
    )
    version = SkillVersion(
        content="# Skill content",
        test_cases="test_cases:\n  - name: test1",
        metrics=metrics,
        iteration=1,
    )

    assert version.content == "# Skill content"
    assert version.metrics.accuracy == 0.85
    assert version.iteration == 1


def test_skill_auto_state_tracks_best_version():
    """SkillAutoState should track best version separately from current."""
    from kubani.workflows.skill_auto.models import SkillAutoState

    state = SkillAutoState(skill_path="kubani/skills/_development/test-skill")

    assert state.iteration == 0
    assert state.best_version is None
    assert state.best_score == 0.0
    assert state.status == "running"


def test_overlap_result_model():
    """OverlapResult should capture overlap detection results."""
    from kubani.workflows.skill_auto.models import OverlapResult

    result = OverlapResult(
        has_overlap=True,
        confidence=0.78,
        overlapping_skills=["memory-troubleshooting"],
        reasoning="Both diagnose memory-related failures",
        recommendation="merge",
    )

    assert result.has_overlap is True
    assert "memory-troubleshooting" in result.overlapping_skills


def test_iteration_result_model():
    """IterationResult should capture a single iteration's outcome."""
    from kubani.workflows.skill_auto.models import EvalMetrics, IterationResult

    metrics = EvalMetrics(
        accuracy=0.80,
        latency_ms=1500.0,
        tests_passed=4,
        tests_total=5,
        critic_confidence=0.85,
    )
    result = IterationResult(
        iteration=1,
        metrics=metrics,
        score=0.76,
        improved=True,
        action="continue",
    )

    assert result.iteration == 1
    assert result.improved is True
