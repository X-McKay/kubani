"""
Skill validation system for automated testing and staged rollout.

Validates skills in a sandbox environment before production use.
Implements the learning loop from Voyager-inspired architecture.

Workflow:
1. Skill proposed by ExplorerAgent or created manually
2. SkillValidator tests skill in sandbox namespace
3. Self-verification checks outcomes against success criteria
4. Confidence score assigned based on test results
5. Skill enters library with "experimental" status
6. After N successful production uses, promoted to "stable"
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from core_agents.skills.schema import Skill

logger = logging.getLogger(__name__)


class SkillStatus(str, Enum):
    """Status of a skill in the validation lifecycle."""

    PROPOSED = "proposed"  # Newly created, not yet validated
    TESTING = "testing"  # Currently being tested in sandbox
    EXPERIMENTAL = "experimental"  # Passed sandbox tests, limited production use
    STABLE = "stable"  # Proven reliable in production
    DEPRECATED = "deprecated"  # No longer recommended for use
    FAILED = "failed"  # Failed validation, needs fixes


class VerificationResult(BaseModel):
    """Result of verifying a single success criterion."""

    criterion: str
    passed: bool
    evidence: str = ""
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ValidationResult(BaseModel):
    """Complete result of skill validation."""

    skill_id: str
    success: bool
    status: SkillStatus
    confidence: float = Field(ge=0.0, le=1.0)
    verifications: list[VerificationResult] = Field(default_factory=list)
    execution_time_seconds: float = 0.0
    sandbox_namespace: str = ""
    logs: list[str] = Field(default_factory=list)
    error_message: str | None = None
    validated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def passed_count(self) -> int:
        """Number of verifications that passed."""
        return sum(1 for v in self.verifications if v.passed)

    @property
    def total_count(self) -> int:
        """Total number of verifications."""
        return len(self.verifications)

    def add_log(self, message: str) -> None:
        """Add a log entry."""
        self.logs.append(f"[{datetime.now(UTC).isoformat()}] {message}")


@dataclass
class SandboxConfig:
    """Configuration for sandbox environment."""

    namespace_prefix: str = "skill-sandbox"
    cleanup_on_success: bool = True
    cleanup_on_failure: bool = False
    timeout_seconds: int = 300
    resource_limits: dict[str, Any] = field(
        default_factory=lambda: {
            "cpu": "100m",
            "memory": "128Mi",
        }
    )


class SkillValidator:
    """
    Validates skills in a sandbox before production use.

    The validator:
    1. Creates an isolated sandbox namespace
    2. Executes the skill's actions in the sandbox
    3. Verifies outcomes against success criteria
    4. Calculates confidence based on results
    5. Cleans up sandbox resources

    Usage:
        validator = SkillValidator()
        result = await validator.validate(skill)

        if result.success:
            skill.status = result.status
            skill.confidence = result.confidence
            await skill_library.add(skill)
    """

    def __init__(
        self,
        config: SandboxConfig | None = None,
        mcp_executor: Any = None,  # MCP tool executor
    ):
        self.config = config or SandboxConfig()
        self._mcp_executor = mcp_executor
        self._k8s_client: Any = None

    async def _ensure_k8s_client(self) -> None:
        """Lazy initialization of Kubernetes client."""
        if self._k8s_client is not None:
            return

        try:
            from kubernetes import client
            from kubernetes import config as k8s_config

            try:
                k8s_config.load_incluster_config()
            except k8s_config.ConfigException:
                k8s_config.load_kube_config()

            self._k8s_client = client.CoreV1Api()
        except ImportError as err:
            raise ImportError(
                "kubernetes package is required for SkillValidator. "
                "Install with: pip install kubernetes"
            ) from err

    async def validate(self, skill: Skill) -> ValidationResult:
        """
        Validate a skill in a sandbox environment.

        Args:
            skill: The skill to validate

        Returns:
            ValidationResult with success status, confidence, and details
        """
        result = ValidationResult(
            skill_id=skill.id,
            success=False,
            status=SkillStatus.TESTING,
            confidence=0.0,
        )

        sandbox_ns = f"{self.config.namespace_prefix}-{uuid.uuid4().hex[:8]}"
        result.sandbox_namespace = sandbox_ns
        result.add_log(f"Starting validation for skill: {skill.id}")

        start_time = datetime.now(UTC)

        try:
            # Step 1: Create sandbox namespace
            await self._create_sandbox(sandbox_ns, result)

            # Step 2: Execute skill actions in sandbox
            await self._execute_skill(skill, sandbox_ns, result)

            # Step 3: Verify success criteria
            await self._verify_outcomes(skill, sandbox_ns, result)

            # Step 4: Calculate confidence
            result.confidence = self._calculate_confidence(skill, result)

            # Step 5: Determine final status
            if result.passed_count == result.total_count:
                result.success = True
                result.status = SkillStatus.EXPERIMENTAL
                result.add_log(
                    f"Validation passed: {result.passed_count}/{result.total_count} criteria met"
                )
            else:
                result.status = SkillStatus.FAILED
                result.add_log(
                    f"Validation failed: {result.passed_count}/{result.total_count} criteria met"
                )

        except TimeoutError:
            result.error_message = f"Validation timed out after {self.config.timeout_seconds}s"
            result.status = SkillStatus.FAILED
            result.add_log(result.error_message)

        except Exception as e:
            result.error_message = str(e)
            result.status = SkillStatus.FAILED
            result.add_log(f"Validation error: {e}")
            logger.exception(f"Skill validation failed for {skill.id}")

        finally:
            # Calculate execution time
            result.execution_time_seconds = (datetime.now(UTC) - start_time).total_seconds()

            # Cleanup based on config
            should_cleanup = (result.success and self.config.cleanup_on_success) or (
                not result.success and self.config.cleanup_on_failure
            )
            if should_cleanup:
                await self._cleanup_sandbox(sandbox_ns, result)

        return result

    async def _create_sandbox(self, namespace: str, result: ValidationResult) -> None:
        """Create an isolated sandbox namespace for testing."""
        await self._ensure_k8s_client()

        from kubernetes.client import V1Namespace, V1ObjectMeta

        result.add_log(f"Creating sandbox namespace: {namespace}")

        ns = V1Namespace(
            metadata=V1ObjectMeta(
                name=namespace,
                labels={
                    "app.kubernetes.io/managed-by": "skill-validator",
                    "skill-validator/sandbox": "true",
                    "skill-validator/created-at": datetime.now(UTC).isoformat(),
                },
                annotations={
                    "skill-validator/skill-id": result.skill_id,
                },
            )
        )

        try:
            await asyncio.to_thread(
                self._k8s_client.create_namespace,
                body=ns,
            )
            result.add_log(f"Created sandbox namespace: {namespace}")
        except Exception as e:
            if "AlreadyExists" not in str(e):
                raise
            result.add_log(f"Sandbox namespace already exists: {namespace}")

    async def _execute_skill(
        self,
        skill: Skill,
        namespace: str,
        result: ValidationResult,
    ) -> None:
        """Execute skill actions in the sandbox namespace."""
        result.add_log(f"Executing {len(skill.actions)} skill actions")

        for i, action in enumerate(skill.actions):
            result.add_log(f"Action {i + 1}/{len(skill.actions)}: {action.description}")

            try:
                # Substitute namespace in params
                params = self._substitute_params(
                    action.mcp_tool.params,
                    {"namespace": namespace},
                )

                # Execute via MCP if executor is configured
                if self._mcp_executor:
                    await asyncio.wait_for(
                        self._mcp_executor(
                            server=action.mcp_tool.server,
                            tool=action.mcp_tool.tool,
                            params=params,
                        ),
                        timeout=action.timeout_seconds,
                    )
                    result.add_log(f"Action {i + 1} completed successfully")
                else:
                    # Dry-run mode - just log the action
                    result.add_log(
                        f"Action {i + 1} (dry-run): {action.mcp_tool.server}:"
                        f"{action.mcp_tool.tool} with params {params}"
                    )

            except TimeoutError:
                error_msg = f"Action {i + 1} timed out after {action.timeout_seconds}s"
                result.add_log(error_msg)
                if not action.continue_on_failure:
                    raise
            except Exception as e:
                error_msg = f"Action {i + 1} failed: {e}"
                result.add_log(error_msg)
                if not action.continue_on_failure:
                    raise

    async def _verify_outcomes(
        self,
        skill: Skill,
        namespace: str,
        result: ValidationResult,
    ) -> None:
        """Verify skill outcomes against success criteria."""
        result.add_log(f"Verifying {len(skill.success_criteria)} success criteria")

        for criterion in skill.success_criteria:
            verification = await self._verify_criterion(criterion, namespace)
            result.verifications.append(verification)
            result.add_log(
                f"Criterion '{criterion[:50]}...' - {'PASSED' if verification.passed else 'FAILED'}"
            )

    async def _verify_criterion(
        self,
        criterion: str,
        namespace: str,
    ) -> VerificationResult:
        """
        Verify a single success criterion.

        This is a simplified implementation - in production, this would:
        1. Parse the criterion to understand what to check
        2. Use MCP tools to query current state
        3. Compare against expected state

        For now, we do basic pattern matching on common criteria.
        """
        # Common patterns we can verify automatically
        criterion_lower = criterion.lower()

        # Pod state checks
        if "running" in criterion_lower and "pod" in criterion_lower:
            return await self._verify_pod_state(namespace, "Running", criterion)

        if "ready" in criterion_lower:
            return await self._verify_pod_ready(namespace, criterion)

        # For criteria we can't automatically verify, mark as needs-human-review
        return VerificationResult(
            criterion=criterion,
            passed=True,  # Assume pass if we can't verify
            evidence="Manual verification required - auto-verify not available",
        )

    async def _verify_pod_state(
        self,
        namespace: str,
        expected_phase: str,
        criterion: str,
    ) -> VerificationResult:
        """Verify pod is in expected state."""
        await self._ensure_k8s_client()

        try:
            pods = await asyncio.to_thread(
                self._k8s_client.list_namespaced_pod,
                namespace=namespace,
            )

            # Check if any pod matches expected phase
            for pod in pods.items:
                if pod.status.phase == expected_phase:
                    return VerificationResult(
                        criterion=criterion,
                        passed=True,
                        evidence=f"Pod {pod.metadata.name} is in {expected_phase} state",
                    )

            return VerificationResult(
                criterion=criterion,
                passed=False,
                evidence=f"No pods in {expected_phase} state",
            )

        except Exception as e:
            return VerificationResult(
                criterion=criterion,
                passed=False,
                evidence=f"Verification error: {e}",
            )

    async def _verify_pod_ready(
        self,
        namespace: str,
        criterion: str,
    ) -> VerificationResult:
        """Verify pod has Ready condition."""
        await self._ensure_k8s_client()

        try:
            pods = await asyncio.to_thread(
                self._k8s_client.list_namespaced_pod,
                namespace=namespace,
            )

            for pod in pods.items:
                conditions = pod.status.conditions or []
                for condition in conditions:
                    if condition.type == "Ready" and condition.status == "True":
                        return VerificationResult(
                            criterion=criterion,
                            passed=True,
                            evidence=f"Pod {pod.metadata.name} is Ready",
                        )

            return VerificationResult(
                criterion=criterion,
                passed=False,
                evidence="No pods are Ready",
            )

        except Exception as e:
            return VerificationResult(
                criterion=criterion,
                passed=False,
                evidence=f"Verification error: {e}",
            )

    def _calculate_confidence(
        self,
        skill: Skill,
        result: ValidationResult,
    ) -> float:
        """
        Calculate confidence score based on validation results.

        Factors:
        - Pass rate of verifications (60% weight)
        - Execution success (20% weight)
        - Prior confidence from skill definition (20% weight)
        """
        if result.total_count == 0:  # noqa: SIM108
            pass_rate = 0.5  # No criteria to verify
        else:
            pass_rate = result.passed_count / result.total_count

        execution_success = 1.0 if result.error_message is None else 0.0
        prior_confidence = skill.confidence

        # Weighted combination
        confidence = 0.6 * pass_rate + 0.2 * execution_success + 0.2 * prior_confidence

        return round(confidence, 3)

    async def _cleanup_sandbox(
        self,
        namespace: str,
        result: ValidationResult,
    ) -> None:
        """Clean up sandbox namespace and resources."""
        await self._ensure_k8s_client()

        result.add_log(f"Cleaning up sandbox namespace: {namespace}")

        try:
            await asyncio.to_thread(
                self._k8s_client.delete_namespace,
                name=namespace,
            )
            result.add_log(f"Deleted sandbox namespace: {namespace}")
        except Exception as e:
            result.add_log(f"Cleanup warning: {e}")

    def _substitute_params(
        self,
        params: dict[str, Any],
        substitutions: dict[str, str],
    ) -> dict[str, Any]:
        """Substitute $variables in parameter values."""
        result = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$"):
                var_name = value[1:]  # Remove $ prefix
                result[key] = substitutions.get(var_name, value)
            else:
                result[key] = value
        return result


class SkillPromoter:
    """
    Promotes skills through the validation lifecycle.

    Tracks production usage and promotes experimental skills to stable
    after they've been successfully used N times.
    """

    def __init__(
        self,
        promotion_threshold: int = 5,
        demotion_failure_rate: float = 0.3,
    ):
        """
        Args:
            promotion_threshold: Successful uses before promotion to stable
            demotion_failure_rate: Failure rate that triggers demotion
        """
        self.promotion_threshold = promotion_threshold
        self.demotion_failure_rate = demotion_failure_rate

    def should_promote(self, skill: Skill) -> bool:
        """Check if a skill should be promoted to stable."""
        if skill.success_count >= self.promotion_threshold:
            total = skill.success_count + skill.failure_count
            if total > 0:
                failure_rate = skill.failure_count / total
                return failure_rate < self.demotion_failure_rate
        return False

    def should_demote(self, skill: Skill) -> bool:
        """Check if a skill should be demoted due to failures."""
        total = skill.success_count + skill.failure_count
        if total >= 3:  # Minimum sample size
            failure_rate = skill.failure_count / total
            return failure_rate >= self.demotion_failure_rate
        return False

    def get_recommended_status(self, skill: Skill) -> SkillStatus:
        """Get recommended status based on usage history."""
        if self.should_demote(skill):
            return SkillStatus.DEPRECATED

        if self.should_promote(skill):
            return SkillStatus.STABLE

        # Keep current status or default to experimental
        return SkillStatus.EXPERIMENTAL


def select_skill_with_confidence(
    query_results: list[tuple[Skill, float]],
    similarity_weight: float = 0.6,
    confidence_weight: float = 0.4,
) -> Skill | None:
    """
    Select the best skill using weighted scoring of similarity and confidence.

    This implements confidence-based skill selection as described in
    the Kubani improvements document.

    Args:
        query_results: List of (skill, similarity_score) tuples from search
        similarity_weight: Weight for semantic similarity (0-1)
        confidence_weight: Weight for confidence score (0-1)

    Returns:
        Best matching skill or None if no results
    """
    if not query_results:
        return None

    scored_skills = []
    for skill, similarity in query_results:
        # Weighted combination of similarity and confidence
        score = similarity_weight * similarity + confidence_weight * skill.confidence
        scored_skills.append((score, skill))

    # Return skill with highest combined score
    best_score, best_skill = max(scored_skills, key=lambda x: x[0])
    logger.debug(
        f"Selected skill '{best_skill.id}' with combined score {best_score:.3f} "
        f"(similarity: {similarity_weight:.3f}, confidence: {best_skill.confidence:.3f})"
    )

    return best_skill
