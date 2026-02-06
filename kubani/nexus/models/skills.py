"""Nexus skill models.

Data models for the Skill Registry, validation pipeline, and
the OCI-native skill management system.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SkillStatus(str, Enum):
    """Lifecycle status of a skill in the registry."""

    PENDING = "pending"
    VALIDATING = "validating"
    VALIDATED = "validated"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class RiskLevel(str, Enum):
    """Risk classification for a skill."""

    LOW = "low"          # score < 4.0 — auto-approve
    MEDIUM = "medium"    # score 4.0-7.0 — requires human approval
    HIGH = "high"        # score > 7.0 — auto-reject


class SkillMetadata(BaseModel):
    """Metadata for a skill in the registry.

    This model represents a row in the `skills` database table and
    is the primary data structure returned by the Skill Registry API.

    Attributes:
        id: Database primary key.
        name: Unique skill name (e.g., 'web/fetch-hackernews').
        version: Semantic version string (e.g., '1.0.0').
        category: Skill category for organization (e.g., 'web', 'text', 'k8s').
        oci_url: Full OCI artifact URL in the registry.
        description: Human-readable description of what the skill does.
        author: Who created this skill (agent or human).
        risk_score: Computed risk score from validation (0.0 - 10.0).
        requires_network: Whether the skill needs network access in the sandbox.
        requires_filesystem: Whether the skill needs write access beyond /workspace.
        status: Current lifecycle status.
        approved_by: Who approved this skill (if applicable).
        approved_at: When the skill was approved.
        rejection_reason: Why the skill was rejected (if applicable).
        created_at: When the skill was first registered.
        updated_at: When the skill record was last modified.
    """

    id: int | None = None
    name: str
    version: str
    category: str = "general"
    oci_url: str = ""
    description: str = ""
    author: str = "nexus-synthesizer"
    risk_score: float = 0.0
    requires_network: bool = False
    requires_filesystem: bool = False
    status: SkillStatus = SkillStatus.PENDING
    approved_by: str | None = None
    approved_at: str | None = None
    rejection_reason: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def risk_level(self) -> RiskLevel:
        """Determine risk level from the numeric score."""
        if self.risk_score < 4.0:
            return RiskLevel.LOW
        elif self.risk_score <= 7.0:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.HIGH


class ValidationStageResult(BaseModel):
    """Result from a single validation stage.

    Attributes:
        stage: Name of the validation stage.
        passed: Whether this stage passed.
        score: Risk contribution from this stage (0.0 - 10.0).
        findings: List of specific findings or issues.
        details: Additional structured details.
    """

    stage: str
    passed: bool
    score: float = 0.0
    findings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    """Complete validation report for a skill.

    Aggregates results from all validation stages into a single report
    with an overall risk score and pass/fail determination.

    Attributes:
        skill_name: Name of the skill being validated.
        skill_version: Version of the skill being validated.
        stages: Results from each validation stage.
        overall_risk_score: Weighted aggregate risk score.
        overall_passed: Whether the skill passed all required stages.
        started_at: When validation began.
        completed_at: When validation finished.
    """

    skill_name: str
    skill_version: str
    stages: list[ValidationStageResult] = Field(default_factory=list)
    overall_risk_score: float = 0.0
    overall_passed: bool = False
    started_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str | None = None

    def compute_overall_score(self) -> float:
        """Compute the weighted overall risk score from stage results.

        Weights:
            - static_analysis: 0.3
            - sandbox_execution: 0.4
            - llm_review: 0.3

        Returns:
            Weighted risk score between 0.0 and 10.0.
        """
        weights = {
            "static_analysis": 0.3,
            "sandbox_execution": 0.4,
            "llm_review": 0.3,
        }
        total_weight = 0.0
        weighted_score = 0.0
        for stage in self.stages:
            weight = weights.get(stage.stage, 0.1)
            weighted_score += stage.score * weight
            total_weight += weight

        if total_weight > 0:
            self.overall_risk_score = weighted_score / total_weight
        else:
            self.overall_risk_score = 0.0

        self.overall_passed = all(s.passed for s in self.stages)
        return self.overall_risk_score


class SkillExecutionRequest(BaseModel):
    """Request to execute a skill in a sandbox.

    Attributes:
        skill_name: Name of the skill to execute.
        skill_version: Version to execute (defaults to 'latest').
        inputs: Input data for the skill.
        timeout_seconds: Maximum execution time.
        conversation_id: Associated conversation for logging.
    """

    skill_name: str
    skill_version: str = "latest"
    inputs: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 60
    conversation_id: str = ""


class SkillExecutionResult(BaseModel):
    """Result from executing a skill in a sandbox.

    Attributes:
        skill_name: Name of the skill that was executed.
        success: Whether the execution completed successfully.
        output: The skill's output (stdout or structured result).
        error: Error message if execution failed.
        exit_code: Process exit code from the sandbox.
        duration_ms: Execution time in milliseconds.
        logs: Captured stderr/logs from the sandbox.
    """

    skill_name: str
    success: bool
    output: str = ""
    error: str | None = None
    exit_code: int = 0
    duration_ms: int = 0
    logs: str = ""
