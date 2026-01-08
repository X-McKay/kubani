"""Tests for the skill validation system."""

import pytest

from core_agents.skills import (
    Skill,
    SkillCategory,
    SkillDomain,
    SkillStatus,
)
from core_agents.skills.validator import (
    SandboxConfig,
    SkillPromoter,
    SkillValidator,
    ValidationResult,
    VerificationResult,
    select_skill_with_confidence,
)


class TestSkillStatus:
    """Tests for SkillStatus enum."""

    def test_all_statuses_exist(self):
        """Test all expected statuses exist."""
        assert SkillStatus.PROPOSED.value == "proposed"
        assert SkillStatus.TESTING.value == "testing"
        assert SkillStatus.EXPERIMENTAL.value == "experimental"
        assert SkillStatus.STABLE.value == "stable"
        assert SkillStatus.DEPRECATED.value == "deprecated"
        assert SkillStatus.FAILED.value == "failed"

    def test_skill_default_status(self):
        """Test skill has default proposed status."""
        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
        )
        assert skill.status == SkillStatus.PROPOSED


class TestSkillLifecycle:
    """Tests for skill lifecycle methods."""

    def test_mark_validated(self):
        """Test marking skill as validated."""
        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
        )

        skill.mark_validated(confidence=0.85)

        assert skill.status == SkillStatus.EXPERIMENTAL
        assert skill.confidence == 0.85
        assert skill.validated_at is not None

    def test_promote_to_stable(self):
        """Test promoting experimental skill to stable."""
        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            status=SkillStatus.EXPERIMENTAL,
        )

        skill.promote_to_stable()

        assert skill.status == SkillStatus.STABLE
        assert skill.promoted_at is not None

    def test_cannot_promote_non_experimental(self):
        """Test that only experimental skills can be promoted."""
        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            status=SkillStatus.PROPOSED,
        )

        with pytest.raises(ValueError, match="Can only promote experimental skills"):
            skill.promote_to_stable()

    def test_deprecate(self):
        """Test deprecating a skill."""
        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            failure_handling="Original handling",
        )

        skill.deprecate(reason="Replaced by better skill")

        assert skill.status == SkillStatus.DEPRECATED
        assert "DEPRECATED" in skill.failure_handling
        assert "Replaced by better skill" in skill.failure_handling

    def test_is_usable(self):
        """Test is_usable check for different statuses."""
        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
        )

        # Proposed - not usable
        skill.status = SkillStatus.PROPOSED
        assert not skill.is_usable()

        # Experimental - usable
        skill.status = SkillStatus.EXPERIMENTAL
        assert skill.is_usable()

        # Stable - usable
        skill.status = SkillStatus.STABLE
        assert skill.is_usable()

        # Deprecated - not usable
        skill.status = SkillStatus.DEPRECATED
        assert not skill.is_usable()

        # Failed - not usable
        skill.status = SkillStatus.FAILED
        assert not skill.is_usable()


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_create_result(self):
        """Test creating a validation result."""
        result = ValidationResult(
            skill_id="test-skill",
            success=True,
            status=SkillStatus.EXPERIMENTAL,
            confidence=0.85,
        )

        assert result.skill_id == "test-skill"
        assert result.success is True
        assert result.confidence == 0.85

    def test_add_verifications(self):
        """Test adding verifications to result."""
        result = ValidationResult(
            skill_id="test-skill",
            success=False,
            status=SkillStatus.TESTING,
            confidence=0.5,
        )

        result.verifications.append(
            VerificationResult(
                criterion="Pod is Running",
                passed=True,
                evidence="Pod test-pod is Running",
            )
        )
        result.verifications.append(
            VerificationResult(
                criterion="No errors in logs",
                passed=False,
                evidence="Found error: OOMKilled",
            )
        )

        assert result.passed_count == 1
        assert result.total_count == 2

    def test_add_log(self):
        """Test adding log entries."""
        result = ValidationResult(
            skill_id="test-skill",
            success=True,
            status=SkillStatus.EXPERIMENTAL,
            confidence=0.85,
        )

        result.add_log("Starting validation")
        result.add_log("Validation complete")

        assert len(result.logs) == 2
        assert "Starting validation" in result.logs[0]


class TestVerificationResult:
    """Tests for VerificationResult model."""

    def test_create_verification(self):
        """Test creating a verification result."""
        verification = VerificationResult(
            criterion="Pod reaches Running state",
            passed=True,
            evidence="Pod my-pod is in Running state",
        )

        assert verification.criterion == "Pod reaches Running state"
        assert verification.passed is True
        assert verification.checked_at is not None


class TestSandboxConfig:
    """Tests for SandboxConfig."""

    def test_default_config(self):
        """Test default sandbox configuration."""
        config = SandboxConfig()

        assert config.namespace_prefix == "skill-sandbox"
        assert config.cleanup_on_success is True
        assert config.cleanup_on_failure is False
        assert config.timeout_seconds == 300

    def test_custom_config(self):
        """Test custom sandbox configuration."""
        config = SandboxConfig(
            namespace_prefix="test-sandbox",
            cleanup_on_success=False,
            cleanup_on_failure=True,
            timeout_seconds=600,
        )

        assert config.namespace_prefix == "test-sandbox"
        assert config.cleanup_on_success is False
        assert config.cleanup_on_failure is True
        assert config.timeout_seconds == 600


class TestSkillValidator:
    """Tests for SkillValidator."""

    def test_validator_creation(self):
        """Test creating a validator."""
        validator = SkillValidator()

        assert validator.config is not None
        assert validator._mcp_executor is None

    def test_validator_with_custom_config(self):
        """Test creating validator with custom config."""
        config = SandboxConfig(namespace_prefix="custom")
        validator = SkillValidator(config=config)

        assert validator.config.namespace_prefix == "custom"

    def test_substitute_params(self):
        """Test parameter substitution."""
        validator = SkillValidator()

        params = {
            "name": "$pod_name",
            "namespace": "$namespace",
            "replicas": 3,
        }
        substitutions = {
            "pod_name": "my-pod",
            "namespace": "test-ns",
        }

        result = validator._substitute_params(params, substitutions)

        assert result["name"] == "my-pod"
        assert result["namespace"] == "test-ns"
        assert result["replicas"] == 3

    def test_calculate_confidence(self):
        """Test confidence calculation."""
        validator = SkillValidator()

        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            confidence=0.7,
        )

        # All verifications passed, no errors
        result = ValidationResult(
            skill_id="test",
            success=True,
            status=SkillStatus.TESTING,
            confidence=0.0,
            verifications=[
                VerificationResult(criterion="A", passed=True),
                VerificationResult(criterion="B", passed=True),
            ],
        )

        confidence = validator._calculate_confidence(skill, result)

        # pass_rate = 1.0, execution_success = 1.0, prior = 0.7
        # confidence = 0.6 * 1.0 + 0.2 * 1.0 + 0.2 * 0.7 = 0.94
        assert confidence == 0.94

    def test_calculate_confidence_with_failures(self):
        """Test confidence calculation with failed verifications."""
        validator = SkillValidator()

        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            confidence=0.5,
        )

        # 1 of 2 verifications passed
        result = ValidationResult(
            skill_id="test",
            success=False,
            status=SkillStatus.TESTING,
            confidence=0.0,
            error_message="Test failed",
            verifications=[
                VerificationResult(criterion="A", passed=True),
                VerificationResult(criterion="B", passed=False),
            ],
        )

        confidence = validator._calculate_confidence(skill, result)

        # pass_rate = 0.5, execution_success = 0.0 (has error), prior = 0.5
        # confidence = 0.6 * 0.5 + 0.2 * 0.0 + 0.2 * 0.5 = 0.4
        assert confidence == 0.4


class TestSkillPromoter:
    """Tests for SkillPromoter."""

    def test_promoter_defaults(self):
        """Test default promoter settings."""
        promoter = SkillPromoter()

        assert promoter.promotion_threshold == 5
        assert promoter.demotion_failure_rate == 0.3

    def test_should_promote(self):
        """Test skill promotion logic."""
        promoter = SkillPromoter(promotion_threshold=3)

        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            success_count=5,
            failure_count=0,
        )

        assert promoter.should_promote(skill)

    def test_should_not_promote_insufficient_usage(self):
        """Test skill not promoted with insufficient usage."""
        promoter = SkillPromoter(promotion_threshold=5)

        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            success_count=3,
            failure_count=0,
        )

        assert not promoter.should_promote(skill)

    def test_should_demote(self):
        """Test skill demotion logic."""
        promoter = SkillPromoter(demotion_failure_rate=0.3)

        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            success_count=2,
            failure_count=3,  # 60% failure rate
        )

        assert promoter.should_demote(skill)

    def test_should_not_demote_insufficient_sample(self):
        """Test skill not demoted with insufficient sample size."""
        promoter = SkillPromoter()

        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            success_count=0,
            failure_count=2,  # Only 2 samples
        )

        assert not promoter.should_demote(skill)

    def test_get_recommended_status_promote(self):
        """Test recommended status when skill should be promoted."""
        promoter = SkillPromoter(promotion_threshold=3)

        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            success_count=5,
            failure_count=0,
        )

        assert promoter.get_recommended_status(skill) == SkillStatus.STABLE

    def test_get_recommended_status_demote(self):
        """Test recommended status when skill should be demoted."""
        promoter = SkillPromoter()

        skill = Skill(
            id="test",
            name="Test",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Test",
            preconditions=[],
            actions=[],
            success_criteria=[],
            success_count=2,
            failure_count=5,
        )

        assert promoter.get_recommended_status(skill) == SkillStatus.DEPRECATED


class TestSelectSkillWithConfidence:
    """Tests for confidence-weighted skill selection."""

    def test_select_best_skill(self):
        """Test selecting skill with highest combined score."""
        skill1 = Skill(
            id="skill1",
            name="Skill 1",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="Low confidence",
            preconditions=[],
            actions=[],
            success_criteria=[],
            confidence=0.3,
        )
        skill2 = Skill(
            id="skill2",
            name="Skill 2",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="High confidence",
            preconditions=[],
            actions=[],
            success_criteria=[],
            confidence=0.9,
        )

        # skill1 has higher similarity (0.9) but lower confidence (0.3)
        # skill2 has lower similarity (0.7) but higher confidence (0.9)
        query_results = [
            (skill1, 0.9),  # similarity
            (skill2, 0.7),  # similarity
        ]

        # Default weights: 0.6 similarity, 0.4 confidence
        # skill1: 0.6 * 0.9 + 0.4 * 0.3 = 0.54 + 0.12 = 0.66
        # skill2: 0.6 * 0.7 + 0.4 * 0.9 = 0.42 + 0.36 = 0.78
        selected = select_skill_with_confidence(query_results)

        assert selected is not None
        assert selected.id == "skill2"

    def test_select_empty_results(self):
        """Test selecting from empty results."""
        selected = select_skill_with_confidence([])

        assert selected is None

    def test_custom_weights(self):
        """Test selection with custom weights."""
        skill1 = Skill(
            id="skill1",
            name="Skill 1",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="High similarity",
            preconditions=[],
            actions=[],
            success_criteria=[],
            confidence=0.3,
        )
        skill2 = Skill(
            id="skill2",
            name="Skill 2",
            domain=SkillDomain.K8S,
            category=SkillCategory.DIAGNOSTIC,
            description="High confidence",
            preconditions=[],
            actions=[],
            success_criteria=[],
            confidence=0.9,
        )

        query_results = [
            (skill1, 0.95),
            (skill2, 0.6),
        ]

        # With 0.9 similarity weight, skill1 should win
        selected = select_skill_with_confidence(
            query_results,
            similarity_weight=0.9,
            confidence_weight=0.1,
        )

        assert selected is not None
        assert selected.id == "skill1"
