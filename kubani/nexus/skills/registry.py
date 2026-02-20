"""Nexus Skill Registry.

Manages the lifecycle of skills within the Nexus system:
- Registration of new skills
- Version management
- Risk assessment and validation
- Approval workflow integration
- OCI artifact references

The registry delegates all database operations to kubani.nexus.db,
ensuring schema consistency across the system.

Usage:
    from kubani.nexus.skills.registry import SkillRegistry

    registry = SkillRegistry(db_pool)

    # Register a new skill
    skill_id = await registry.register(
        name="web/fetch-url",
        version="0.1.0",
        description="Fetch content from a URL",
        source_code="...",
        author="nexus-synthesizer",
    )

    # Get approved skills
    skills = await registry.list_approved()
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from kubani.nexus import db

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Manages skill registration, validation, and lifecycle.

    Attributes:
        db_pool: asyncpg connection pool for PostgreSQL.
    """

    def __init__(self, db_pool: Any) -> None:
        self.db_pool = db_pool

    async def register(
        self,
        name: str,
        version: str,
        description: str,
        source_code: str,
        author: str = "nexus-synthesizer",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Register a new skill or skill version.

        This method:
        1. Computes a content hash for deduplication.
        2. Runs risk assessment on the source code.
        3. Stores the skill metadata in PostgreSQL.
        4. If risk is LOW, auto-approves. Otherwise, creates an approval request.

        Args:
            name: Skill name (e.g., "web/fetch-url").
            version: Semantic version string.
            description: Human-readable description.
            source_code: The Python source code of the skill.
            author: Who created this skill.
            metadata: Optional additional metadata (used for approval context).

        Returns:
            The database ID of the registered skill.
        """
        content_hash = hashlib.sha256(source_code.encode()).hexdigest()

        # Check for duplicate
        existing = await db.get_skill_by_hash(self.db_pool, content_hash)
        if existing:
            logger.info(f"Skill {name}@{version} already registered (hash match)")
            return existing["id"]

        # Run risk assessment
        from kubani.nexus.sandbox.executor import analyze_skill_safety

        safety = analyze_skill_safety(source_code)
        risk_level = self._classify_risk(safety["risk_score"])

        # Determine initial status based on risk
        if risk_level == "low":
            status = "approved"
        else:
            status = "pending_approval"

        # Store in database
        skill_id = await db.register_skill(
            self.db_pool,
            name=name,
            version=version,
            description=description,
            author=author,
            content_hash=content_hash,
            status=status,
            risk_score=safety["risk_score"],
        )

        # If not auto-approved, create an approval request
        if status == "pending_approval":
            await db.create_approval_request(
                self.db_pool,
                request_type="skill_approval",
                reference_id=skill_id,
                title=f"{name}@{version}",
                description=(
                    f"Skill '{name}@{version}' requires approval.\n"
                    f"Risk level: {risk_level} (score: {safety['risk_score']:.1f})\n"
                    f"Findings:\n"
                    + "\n".join(f"  - {f}" for f in safety["findings"][:5])
                ),
                risk_score=safety["risk_score"],
            )
            logger.info(
                f"Skill {name}@{version} registered with status "
                f"'{status}' (risk: {risk_level}, score: {safety['risk_score']:.1f})"
            )
        else:
            logger.info(
                f"Skill {name}@{version} auto-approved (risk: {risk_level})"
            )

        return skill_id

    async def get(self, name: str, version: str | None = None) -> dict[str, Any] | None:
        """Get a skill by name and optional version.

        If no version is specified, returns the latest approved version.

        Args:
            name: Skill name.
            version: Optional specific version.

        Returns:
            Skill metadata dict, or None if not found.
        """
        return await db.get_skill(
            self.db_pool,
            name=name,
            version=version or "latest",
        )

    async def list_approved(self) -> list[dict[str, Any]]:
        """List all approved skills.

        Returns:
            List of skill metadata dicts.
        """
        return await db.list_skills(self.db_pool, status="approved")

    async def list_all(self, include_rejected: bool = False) -> list[dict[str, Any]]:
        """List all skills.

        Args:
            include_rejected: Whether to include rejected skills.

        Returns:
            List of skill metadata dicts.
        """
        if include_rejected:
            return await db.list_skills(self.db_pool)
        else:
            # Get all non-rejected skills by fetching all and filtering
            all_skills = await db.list_skills(self.db_pool)
            return [s for s in all_skills if s.get("status") != "rejected"]

    async def approve(self, skill_id: int, approved_by: str = "system") -> None:
        """Approve a skill.

        Args:
            skill_id: The database ID of the skill.
            approved_by: Who approved it.
        """
        await db.update_skill_status(
            self.db_pool,
            skill_id=skill_id,
            status="approved",
            approved_by=approved_by,
        )
        logger.info(f"Skill {skill_id} approved by {approved_by}")

    async def reject(
        self, skill_id: int, reason: str, rejected_by: str = "system"
    ) -> None:
        """Reject a skill.

        Args:
            skill_id: The database ID of the skill.
            reason: Why it was rejected.
            rejected_by: Who rejected it.
        """
        await db.update_skill_status(
            self.db_pool,
            skill_id=skill_id,
            status="rejected",
            rejection_reason=reason,
        )
        logger.info(f"Skill {skill_id} rejected by {rejected_by}: {reason}")

    async def deprecate(self, name: str, version: str) -> None:
        """Deprecate a specific skill version.

        Args:
            name: Skill name.
            version: Version to deprecate.
        """
        skill = await db.get_skill(self.db_pool, name=name, version=version)
        if skill:
            await db.update_skill_status(
                self.db_pool,
                skill_id=skill["id"],
                status="deprecated",
            )
            logger.info(f"Skill {name}@{version} deprecated")

    # =================================================================
    # Private Methods
    # =================================================================

    def _classify_risk(self, risk_score: float) -> str:
        """Classify a risk score into a risk level.

        Args:
            risk_score: Numeric risk score (0.0 - 10.0).

        Returns:
            Risk level: 'low', 'medium', or 'high'.
        """
        if risk_score < 3.0:
            return "low"
        elif risk_score < 6.0:
            return "medium"
        else:
            return "high"
