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


def test_compute_score_weights_accuracy_and_latency():
    """Score should weight accuracy (70%) and latency (30%)."""
    from kubani.workflows.skill_auto.models import EvalMetrics, compute_score

    # High accuracy, medium latency
    metrics1 = EvalMetrics(
        accuracy=0.90, latency_ms=2000, tests_passed=9, tests_total=10, critic_confidence=0.85
    )
    score1 = compute_score(metrics1)

    # Medium accuracy, low latency
    metrics2 = EvalMetrics(
        accuracy=0.70, latency_ms=500, tests_passed=7, tests_total=10, critic_confidence=0.75
    )
    score2 = compute_score(metrics2)

    # High accuracy should win despite slower latency
    assert score1 > score2


def test_compute_score_normalized_latency():
    """Latency should be normalized - faster is better."""
    from kubani.workflows.skill_auto.models import EvalMetrics, compute_score

    fast = EvalMetrics(
        accuracy=0.80, latency_ms=500, tests_passed=8, tests_total=10, critic_confidence=0.80
    )
    slow = EvalMetrics(
        accuracy=0.80, latency_ms=5000, tests_passed=8, tests_total=10, critic_confidence=0.80
    )

    assert compute_score(fast) > compute_score(slow)


def test_is_plateau_detects_stagnation():
    """is_plateau should detect when score improvement is < 2% for 2 iterations."""
    from kubani.workflows.skill_auto.models import EvalMetrics, IterationResult, is_plateau

    metrics = EvalMetrics(
        accuracy=0.80, latency_ms=1500, tests_passed=8, tests_total=10, critic_confidence=0.80
    )

    history = [
        IterationResult(iteration=1, metrics=metrics, score=0.75, improved=True, action="continue"),
        IterationResult(
            iteration=2, metrics=metrics, score=0.76, improved=True, action="continue"
        ),  # +1.3%
        IterationResult(
            iteration=3, metrics=metrics, score=0.765, improved=True, action="continue"
        ),  # +0.7%
    ]

    assert is_plateau(history) is True


def test_is_plateau_false_when_improving():
    """is_plateau should return False when recent improvements are significant."""
    from kubani.workflows.skill_auto.models import EvalMetrics, IterationResult, is_plateau

    metrics = EvalMetrics(
        accuracy=0.80, latency_ms=1500, tests_passed=8, tests_total=10, critic_confidence=0.80
    )

    history = [
        IterationResult(iteration=1, metrics=metrics, score=0.70, improved=True, action="continue"),
        IterationResult(
            iteration=2, metrics=metrics, score=0.75, improved=True, action="continue"
        ),  # +7%
        IterationResult(
            iteration=3, metrics=metrics, score=0.80, improved=True, action="continue"
        ),  # +6.7%
    ]

    assert is_plateau(history) is False
