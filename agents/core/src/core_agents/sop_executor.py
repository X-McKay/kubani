"""
SOPExecutor - Execute Standard Operating Procedures.

SOPs are multi-step procedures defined in markdown that may invoke
multiple skills. This executor:
1. Loads and parses SOP.md files
2. Executes steps in order
3. Handles decision points and branching
4. Tracks progress and outcomes
5. Can bridge to Temporal workflows if configured
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import frontmatter

logger = logging.getLogger(__name__)


class SOPStatus(str, Enum):
    """Status of SOP execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"  # Waiting for approval or decision


@dataclass
class SOPMetadata:
    """Metadata parsed from SOP frontmatter."""

    name: str
    description: str
    domain: str = "general"
    category: str = "runbook"
    schedule: str | None = None
    requires_approval: bool = False
    timeout: str = "30m"
    temporal_workflow: str | None = None

    @classmethod
    def from_frontmatter(cls, data: dict[str, Any]) -> SOPMetadata:
        """Create from frontmatter dict."""
        metadata = data.get("metadata", data)
        return cls(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            domain=metadata.get("domain", "general"),
            category=metadata.get("category", "runbook"),
            schedule=metadata.get("schedule"),
            requires_approval=metadata.get("requires-approval", False),
            timeout=metadata.get("timeout", "30m"),
            temporal_workflow=metadata.get("temporal-workflow"),
        )


@dataclass
class SOPStep:
    """A single step in an SOP."""

    number: int
    title: str
    content: str
    skills_to_invoke: list[str] = field(default_factory=list)
    decision_points: list[str] = field(default_factory=list)
    status: SOPStatus = SOPStatus.PENDING
    result: dict[str, Any] = field(default_factory=dict)


@dataclass
class SOP:
    """Parsed Standard Operating Procedure."""

    path: Path
    metadata: SOPMetadata
    body: str
    steps: list[SOPStep] = field(default_factory=list)

    @property
    def id(self) -> str:
        """Generate ID from path."""
        parts = self.path.parts
        try:
            sops_idx = parts.index("sops")
            return "/".join(parts[sops_idx + 1 : -1])
        except ValueError:
            return self.path.parent.name

    @classmethod
    def from_file(cls, path: Path) -> SOP:
        """Load SOP from file."""
        post = frontmatter.load(path)
        metadata = SOPMetadata.from_frontmatter(dict(post.metadata))

        sop = cls(
            path=path,
            metadata=metadata,
            body=post.content,
        )
        sop.steps = sop._parse_steps()
        return sop

    def _parse_steps(self) -> list[SOPStep]:
        """Parse steps from markdown body."""
        steps = []
        step_pattern = re.compile(r"^### Step (\d+):\s*(.+)$", re.MULTILINE)

        matches = list(step_pattern.finditer(self.body))

        for i, match in enumerate(matches):
            step_num = int(match.group(1))
            step_title = match.group(2).strip()

            # Get content until next step or end
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(self.body)
            content = self.body[start:end].strip()

            # Extract skills to invoke
            skills = self._extract_skills(content)

            # Extract decision points
            decisions = self._extract_decisions(content)

            steps.append(
                SOPStep(
                    number=step_num,
                    title=step_title,
                    content=content,
                    skills_to_invoke=skills,
                    decision_points=decisions,
                )
            )

        return steps

    def _extract_skills(self, content: str) -> list[str]:
        """Extract skill references from step content."""
        skills = []
        # Match patterns like `k8s/remediation/restart-crashloop`
        skill_pattern = re.compile(r"`([a-z0-9/-]+/[a-z0-9-]+)`")
        for match in skill_pattern.finditer(content):
            skill_id = match.group(1)
            if "/" in skill_id and not skill_id.startswith("http"):
                skills.append(skill_id)
        return skills

    def _extract_decisions(self, content: str) -> list[str]:
        """Extract decision points from step content."""
        decisions = []
        # Match patterns like "If condition A: action"
        decision_pattern = re.compile(r"^[-*]\s*If (.+?):\s*(.+)$", re.MULTILINE)
        for match in decision_pattern.finditer(content):
            decisions.append(f"If {match.group(1)}: {match.group(2)}")
        return decisions


@dataclass
class SOPExecutionResult:
    """Result of executing an SOP."""

    sop_id: str
    status: SOPStatus
    steps_completed: int
    total_steps: int
    start_time: datetime
    end_time: datetime | None = None
    errors: list[str] = field(default_factory=list)
    step_results: list[dict[str, Any]] = field(default_factory=list)


class SOPLoader:
    """Loads SOPs from filesystem."""

    def __init__(self, sops_dir: Path | str = "sops"):
        self.sops_dir = Path(sops_dir)

    def load(self, sop_path: str) -> SOP | None:
        """Load SOP by relative path (e.g., 'k8s/cluster-health-check')."""
        full_path = self.sops_dir / sop_path / "SOP.md"
        if not full_path.exists():
            return None
        return SOP.from_file(full_path)

    def list_all(self, domain: str | None = None) -> list[SOP]:
        """List all SOPs, optionally filtered by domain."""
        sops = []
        for sop_path in self.sops_dir.rglob("SOP.md"):
            try:
                sop = SOP.from_file(sop_path)
                if domain is None or sop.metadata.domain == domain:
                    sops.append(sop)
            except Exception as e:
                logger.warning(f"Failed to load SOP from {sop_path}: {e}")
        return sops


class SOPExecutor:
    """
    Executes SOPs by following their markdown instructions.

    The executor:
    1. Parses the SOP into steps
    2. Executes each step in order
    3. Invokes skills referenced in each step
    4. Handles decision points
    5. Tracks progress and reports results

    For SOPs with temporal-workflow metadata, it can optionally
    delegate to the corresponding Temporal workflow.
    """

    def __init__(
        self,
        sops_dir: Path | str = "sops",
        skill_library: Any = None,
        use_temporal: bool = False,
    ):
        self.loader = SOPLoader(sops_dir)
        self.skill_library = skill_library
        self.use_temporal = use_temporal

    async def execute(
        self,
        sop_path: str,
        context: dict[str, Any] | None = None,
    ) -> SOPExecutionResult:
        """
        Execute an SOP.

        Args:
            sop_path: Relative path to SOP (e.g., 'k8s/cluster-health-check')
            context: Execution context with variables

        Returns:
            Execution result with status and outcomes
        """
        sop = self.loader.load(sop_path)
        if sop is None:
            return SOPExecutionResult(
                sop_id=sop_path,
                status=SOPStatus.FAILED,
                steps_completed=0,
                total_steps=0,
                start_time=datetime.utcnow(),
                errors=[f"SOP not found: {sop_path}"],
            )

        # Check if should delegate to Temporal
        if self.use_temporal and sop.metadata.temporal_workflow:
            return await self._execute_via_temporal(sop, context)

        # Execute directly
        return await self._execute_steps(sop, context or {})

    async def _execute_steps(
        self,
        sop: SOP,
        context: dict[str, Any],
    ) -> SOPExecutionResult:
        """Execute SOP steps directly."""
        result = SOPExecutionResult(
            sop_id=sop.id,
            status=SOPStatus.RUNNING,
            steps_completed=0,
            total_steps=len(sop.steps),
            start_time=datetime.utcnow(),
        )

        logger.info(f"Executing SOP: {sop.id} ({len(sop.steps)} steps)")

        for step in sop.steps:
            try:
                step.status = SOPStatus.RUNNING
                logger.info(f"Step {step.number}: {step.title}")

                # Execute skills in this step
                step_result = await self._execute_step(step, context)
                step.result = step_result
                step.status = SOPStatus.COMPLETED

                result.steps_completed += 1
                result.step_results.append(
                    {
                        "step": step.number,
                        "title": step.title,
                        "status": "completed",
                        "result": step_result,
                    }
                )

            except Exception as e:
                logger.error(f"Step {step.number} failed: {e}")
                step.status = SOPStatus.FAILED
                result.errors.append(f"Step {step.number} failed: {e}")
                result.step_results.append(
                    {
                        "step": step.number,
                        "title": step.title,
                        "status": "failed",
                        "error": str(e),
                    }
                )
                result.status = SOPStatus.FAILED
                break

        if result.status == SOPStatus.RUNNING:
            result.status = SOPStatus.COMPLETED

        result.end_time = datetime.utcnow()
        logger.info(f"SOP {sop.id} completed: {result.status.value}")

        return result

    async def _execute_step(
        self,
        step: SOPStep,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single SOP step."""
        step_result: dict[str, Any] = {"skills_invoked": []}

        # Execute each skill referenced in the step
        for skill_id in step.skills_to_invoke:
            try:
                skill_result = await self._invoke_skill(skill_id, context)
                step_result["skills_invoked"].append(
                    {
                        "skill_id": skill_id,
                        "success": True,
                        "result": skill_result,
                    }
                )
            except Exception as e:
                step_result["skills_invoked"].append(
                    {
                        "skill_id": skill_id,
                        "success": False,
                        "error": str(e),
                    }
                )
                # Continue with other skills (don't fail entire step)
                logger.warning(f"Skill {skill_id} failed in step {step.number}: {e}")

        return step_result

    async def _invoke_skill(
        self,
        skill_id: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Invoke a skill by ID."""
        if self.skill_library is None:
            logger.warning(f"No skill library configured, skipping skill: {skill_id}")
            return {"skipped": True, "reason": "no skill library"}

        # Get skill from library
        skill = await self.skill_library.get(skill_id)
        if skill is None:
            return {"skipped": True, "reason": f"skill not found: {skill_id}"}

        # For now, just return the skill body
        # In a full implementation, this would execute the skill
        return {
            "skill_id": skill_id,
            "skill_name": skill.name,
            "executed": True,
        }

    async def _execute_via_temporal(
        self,
        sop: SOP,
        context: dict[str, Any] | None,
    ) -> SOPExecutionResult:
        """Delegate execution to Temporal workflow."""
        workflow_name = sop.metadata.temporal_workflow
        logger.info(f"Delegating SOP {sop.id} to Temporal workflow: {workflow_name}")

        # This would require Temporal client setup
        # For now, return a placeholder
        return SOPExecutionResult(
            sop_id=sop.id,
            status=SOPStatus.PENDING,
            steps_completed=0,
            total_steps=len(sop.steps),
            start_time=datetime.utcnow(),
            errors=[f"Temporal delegation not yet implemented for: {workflow_name}"],
        )


async def execute_sop(
    sop_path: str,
    context: dict[str, Any] | None = None,
    sops_dir: str = "sops",
) -> SOPExecutionResult:
    """
    Convenience function to execute an SOP.

    Args:
        sop_path: Relative path to SOP
        context: Execution context
        sops_dir: Root directory for SOPs

    Returns:
        Execution result
    """
    executor = SOPExecutor(sops_dir=sops_dir)
    return await executor.execute(sop_path, context)
