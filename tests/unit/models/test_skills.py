"""Unit tests for Nexus skill models.

This module tests the skill models used in the Nexus Skill Registry:
- SkillMetadata: Metadata for skills in the registry
- ValidationReport: Validation results with weighted scoring
- SkillExecutionRequest: Request to execute a skill
- SkillExecutionResult: Result from skill execution

Tests include:
- Property-based tests for risk level computation
- Property-based tests for validation score weighting
- Validation tests for enum values
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from kubani.nexus.models.skills import (
    RiskLevel,
    SkillMetadata,
    SkillStatus,
    ValidationReport,
    ValidationStageResult,
)


# Hypothesis strategies for generating test data
@st.composite
def skill_metadata_with_risk_score(draw):
    """Generate random SkillMetadata instances with varying risk scores."""
    return SkillMetadata(
        name=draw(st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_characters="\x00/"))),
        version=draw(st.from_regex(r'\d+\.\d+\.\d+', fullmatch=True)),
        category=draw(st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_characters="\x00"))),
        risk_score=draw(st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)),
        description=draw(st.text(max_size=500, alphabet=st.characters(blacklist_characters="\x00"))),
    )


@st.composite
def validation_stage_results(draw):
    """Generate random ValidationStageResult instances."""
    stage_name = draw(st.sampled_from(["static_analysis", "sandbox_execution", "llm_review"]))
    return ValidationStageResult(
        stage=stage_name,
        passed=draw(st.booleans()),
        score=draw(st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)),
        findings=draw(st.lists(st.text(max_size=100), max_size=5)),
    )


@st.composite
def validation_reports(draw):
    """Generate random ValidationReport instances with all three stages."""
    skill_name = draw(st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_characters="\x00/")))
    skill_version = draw(st.from_regex(r'\d+\.\d+\.\d+', fullmatch=True))
    
    # Generate exactly three stages with the expected names
    static_score = draw(st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False))
    sandbox_score = draw(st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False))
    llm_score = draw(st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False))
    
    stages = [
        ValidationStageResult(
            stage="static_analysis",
            passed=draw(st.booleans()),
            score=static_score,
            findings=draw(st.lists(st.text(max_size=100), max_size=3)),
        ),
        ValidationStageResult(
            stage="sandbox_execution",
            passed=draw(st.booleans()),
            score=sandbox_score,
            findings=draw(st.lists(st.text(max_size=100), max_size=3)),
        ),
        ValidationStageResult(
            stage="llm_review",
            passed=draw(st.booleans()),
            score=llm_score,
            findings=draw(st.lists(st.text(max_size=100), max_size=3)),
        ),
    ]
    
    return ValidationReport(
        skill_name=skill_name,
        skill_version=skill_version,
        stages=stages,
    )


class TestSkillMetadata:
    """Tests for SkillMetadata model."""

    @given(skill=skill_metadata_with_risk_score())
    def test_property_3_risk_level_computation(self, skill):
        """
        Feature: nexus-testing, Property 3: Risk level computation
        
        For any SkillMetadata with a risk_score, the computed risk_level property
        should match the expected level based on score ranges:
        - < 4.0 = LOW
        - 4.0-7.0 = MEDIUM
        - > 7.0 = HIGH
        
        Validates: Requirements 1.5
        """
        # Get the computed risk level
        computed_level = skill.risk_level
        
        # Determine expected level based on risk_score
        if skill.risk_score < 4.0:
            expected_level = RiskLevel.LOW
        elif skill.risk_score <= 7.0:
            expected_level = RiskLevel.MEDIUM
        else:
            expected_level = RiskLevel.HIGH
        
        # Verify the computed level matches expected
        assert computed_level == expected_level, (
            f"Risk score {skill.risk_score} should map to {expected_level}, "
            f"but got {computed_level}"
        )

    def test_risk_level_boundary_low_medium(self):
        """Test risk level computation at the LOW/MEDIUM boundary (4.0)."""
        # Just below boundary - should be LOW
        skill_low = SkillMetadata(
            name="test-skill",
            version="1.0.0",
            risk_score=3.99
        )
        assert skill_low.risk_level == RiskLevel.LOW
        
        # At boundary - should be MEDIUM
        skill_medium = SkillMetadata(
            name="test-skill",
            version="1.0.0",
            risk_score=4.0
        )
        assert skill_medium.risk_level == RiskLevel.MEDIUM

    def test_risk_level_boundary_medium_high(self):
        """Test risk level computation at the MEDIUM/HIGH boundary (7.0)."""
        # At boundary - should be MEDIUM
        skill_medium = SkillMetadata(
            name="test-skill",
            version="1.0.0",
            risk_score=7.0
        )
        assert skill_medium.risk_level == RiskLevel.MEDIUM
        
        # Just above boundary - should be HIGH
        skill_high = SkillMetadata(
            name="test-skill",
            version="1.0.0",
            risk_score=7.01
        )
        assert skill_high.risk_level == RiskLevel.HIGH

    def test_risk_level_extremes(self):
        """Test risk level computation at extreme values."""
        # Minimum risk score
        skill_min = SkillMetadata(
            name="test-skill",
            version="1.0.0",
            risk_score=0.0
        )
        assert skill_min.risk_level == RiskLevel.LOW
        
        # Maximum risk score
        skill_max = SkillMetadata(
            name="test-skill",
            version="1.0.0",
            risk_score=10.0
        )
        assert skill_max.risk_level == RiskLevel.HIGH

    def test_skill_metadata_default_values(self):
        """Test that SkillMetadata has correct default values."""
        skill = SkillMetadata(
            name="test-skill",
            version="1.0.0"
        )
        
        assert skill.category == "general"
        assert skill.oci_url == ""
        assert skill.description == ""
        assert skill.author == "nexus-synthesizer"
        assert skill.risk_score == 0.0
        assert skill.requires_network is False
        assert skill.requires_filesystem is False
        assert skill.status == SkillStatus.PENDING
        assert skill.risk_level == RiskLevel.LOW  # 0.0 < 4.0

    def test_skill_metadata_status_enum(self):
        """Test that SkillMetadata accepts valid SkillStatus values."""
        for status in SkillStatus:
            skill = SkillMetadata(
                name="test-skill",
                version="1.0.0",
                status=status
            )
            assert skill.status == status


class TestValidationReport:
    """Tests for ValidationReport model."""

    @given(report=validation_reports())
    def test_property_5_validation_score_weighting(self, report):
        """
        Feature: nexus-testing, Property 5: Validation score weighting
        
        For any ValidationReport with stage results, the overall_risk_score
        should equal the weighted average with weights:
        - static_analysis: 0.3
        - sandbox_execution: 0.4
        - llm_review: 0.3
        
        Validates: Requirements 1.7
        """
        # Compute the overall score
        computed_score = report.compute_overall_score()
        
        # Extract stage scores
        stage_scores = {stage.stage: stage.score for stage in report.stages}
        
        # Calculate expected weighted average
        expected_score = (
            stage_scores.get("static_analysis", 0.0) * 0.3 +
            stage_scores.get("sandbox_execution", 0.0) * 0.4 +
            stage_scores.get("llm_review", 0.0) * 0.3
        )
        
        # Verify the computed score matches expected (with floating point tolerance)
        assert abs(computed_score - expected_score) < 0.0001, (
            f"Expected weighted score {expected_score}, but got {computed_score}. "
            f"Stages: {stage_scores}"
        )
        
        # Verify the score was also set on the report object
        assert abs(report.overall_risk_score - expected_score) < 0.0001

    def test_validation_report_all_stages_passed(self):
        """Test that overall_passed is True when all stages pass."""
        report = ValidationReport(
            skill_name="test-skill",
            skill_version="1.0.0",
            stages=[
                ValidationStageResult(stage="static_analysis", passed=True, score=2.0),
                ValidationStageResult(stage="sandbox_execution", passed=True, score=3.0),
                ValidationStageResult(stage="llm_review", passed=True, score=1.5),
            ]
        )
        
        report.compute_overall_score()
        assert report.overall_passed is True

    def test_validation_report_one_stage_failed(self):
        """Test that overall_passed is False when any stage fails."""
        report = ValidationReport(
            skill_name="test-skill",
            skill_version="1.0.0",
            stages=[
                ValidationStageResult(stage="static_analysis", passed=True, score=2.0),
                ValidationStageResult(stage="sandbox_execution", passed=False, score=8.0),
                ValidationStageResult(stage="llm_review", passed=True, score=1.5),
            ]
        )
        
        report.compute_overall_score()
        assert report.overall_passed is False

    def test_validation_report_weighted_score_calculation(self):
        """Test specific weighted score calculation with known values."""
        report = ValidationReport(
            skill_name="test-skill",
            skill_version="1.0.0",
            stages=[
                ValidationStageResult(stage="static_analysis", passed=True, score=6.0),
                ValidationStageResult(stage="sandbox_execution", passed=True, score=4.0),
                ValidationStageResult(stage="llm_review", passed=True, score=2.0),
            ]
        )
        
        computed_score = report.compute_overall_score()
        
        # Expected: (6.0 * 0.3) + (4.0 * 0.4) + (2.0 * 0.3) = 1.8 + 1.6 + 0.6 = 4.0
        expected_score = 4.0
        
        assert abs(computed_score - expected_score) < 0.0001
        assert abs(report.overall_risk_score - expected_score) < 0.0001

    def test_validation_report_empty_stages(self):
        """Test that compute_overall_score handles empty stages list."""
        report = ValidationReport(
            skill_name="test-skill",
            skill_version="1.0.0",
            stages=[]
        )
        
        computed_score = report.compute_overall_score()
        
        # With no stages, score should be 0.0
        assert computed_score == 0.0
        assert report.overall_risk_score == 0.0
        # overall_passed should be True (vacuous truth - all zero stages passed)
        assert report.overall_passed is True

    def test_validation_report_missing_stage(self):
        """Test that compute_overall_score handles missing stages gracefully."""
        # Only two stages instead of three
        report = ValidationReport(
            skill_name="test-skill",
            skill_version="1.0.0",
            stages=[
                ValidationStageResult(stage="static_analysis", passed=True, score=5.0),
                ValidationStageResult(stage="sandbox_execution", passed=True, score=6.0),
            ]
        )
        
        computed_score = report.compute_overall_score()
        
        # Expected: (5.0 * 0.3) + (6.0 * 0.4) / (0.3 + 0.4)
        # = (1.5 + 2.4) / 0.7 = 3.9 / 0.7 = 5.571428...
        # The implementation normalizes by actual weights present, not total possible weights
        expected_score = 3.9 / 0.7
        
        assert abs(computed_score - expected_score) < 0.0001


class TestSkillEnums:
    """Tests for skill enum types."""

    def test_skill_status_values(self):
        """Test that SkillStatus has expected values."""
        assert SkillStatus.PENDING == "pending"
        assert SkillStatus.VALIDATING == "validating"
        assert SkillStatus.VALIDATED == "validated"
        assert SkillStatus.PENDING_APPROVAL == "pending_approval"
        assert SkillStatus.APPROVED == "approved"
        assert SkillStatus.REJECTED == "rejected"

    def test_risk_level_values(self):
        """Test that RiskLevel has expected values."""
        assert RiskLevel.LOW == "low"
        assert RiskLevel.MEDIUM == "medium"
        assert RiskLevel.HIGH == "high"
