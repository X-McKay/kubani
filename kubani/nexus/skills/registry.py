"""Nexus Skill Registry.

Manages the lifecycle of skills within the Nexus system:
- Registration of new skills
- Version management
- Risk assessment and validation
- Approval workflow integration
- OCI artifact references

The registry stores metadata in PostgreSQL and references OCI artifacts
in the configured container registry (Harbor in production).

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
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

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
            metadata: Optional additional metadata.

        Returns:
            The database ID of the registered skill.
        """
        content_hash = hashlib.sha256(source_code.encode()).hexdigest()

        # Check for duplicate
        existing = await self._find_by_hash(content_hash)
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
        elif risk_level == "medium":
            status = "pending_review"
        else:
            status = "pending_review"

        # Store in database
        skill_id = await self._insert_skill(
            name=name,
            version=version,
            description=description,
            author=author,
            content_hash=content_hash,
            risk_level=risk_level,
            risk_score=safety["risk_score"],
            risk_findings=safety["findings"],
            status=status,
            metadata=metadata or {},
        )

        # If not auto-approved, create an approval request
        if status == "pending_review":
            await self._create_approval_request(
                skill_id=skill_id,
                skill_name=name,
                version=version,
                risk_level=risk_level,
                risk_score=safety["risk_score"],
                findings=safety["findings"],
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
        async with self.db_pool.acquire() as conn:
            if version:
                row = await conn.fetchrow(
                    "SELECT * FROM skills WHERE name = $1 AND version = $2",
                    name, version,
                )
            else:
                row = await conn.fetchrow(
                    """SELECT * FROM skills
                    WHERE name = $1 AND status = 'approved'
                    ORDER BY created_at DESC LIMIT 1""",
                    name,
                )
            return dict(row) if row else None

    async def list_approved(self) -> list[dict[str, Any]]:
        """List all approved skills (latest version of each).

        Returns:
            List of skill metadata dicts.
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT DISTINCT ON (name) *
                FROM skills
                WHERE status = 'approved'
                ORDER BY name, created_at DESC"""
            )
            return [dict(row) for row in rows]

    async def list_all(self, include_rejected: bool = False) -> list[dict[str, Any]]:
        """List all skills.

        Args:
            include_rejected: Whether to include rejected skills.

        Returns:
            List of skill metadata dicts.
        """
        async with self.db_pool.acquire() as conn:
            if include_rejected:
                rows = await conn.fetch(
                    "SELECT * FROM skills ORDER BY created_at DESC"
                )
            else:
                rows = await conn.fetch(
                    """SELECT * FROM skills
                    WHERE status != 'rejected'
                    ORDER BY created_at DESC"""
                )
            return [dict(row) for row in rows]

    async def approve(self, skill_id: int, approved_by: str = "system") -> None:
        """Approve a skill.

        Args:
            skill_id: The database ID of the skill.
            approved_by: Who approved it.
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """UPDATE skills
                SET status = 'approved', updated_at = NOW()
                WHERE id = $1""",
                skill_id,
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
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """UPDATE skills
                SET status = 'rejected', updated_at = NOW()
                WHERE id = $1""",
                skill_id,
            )
        logger.info(f"Skill {skill_id} rejected by {rejected_by}: {reason}")

    async def deprecate(self, name: str, version: str) -> None:
        """Deprecate a specific skill version.

        Args:
            name: Skill name.
            version: Version to deprecate.
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """UPDATE skills
                SET status = 'deprecated', updated_at = NOW()
                WHERE name = $1 AND version = $2""",
                name, version,
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

    async def _find_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        """Find a skill by content hash.

        Args:
            content_hash: SHA-256 hash of the skill source code.

        Returns:
            Skill metadata dict, or None.
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM skills WHERE content_hash = $1",
                content_hash,
            )
            return dict(row) if row else None

    async def _insert_skill(
        self,
        name: str,
        version: str,
        description: str,
        author: str,
        content_hash: str,
        risk_level: str,
        risk_score: float,
        risk_findings: list[str],
        status: str,
        metadata: dict[str, Any],
    ) -> int:
        """Insert a skill record into the database.

        Returns:
            The database ID of the inserted skill.
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO skills
                (name, version, description, author, content_hash,
                 risk_level, risk_score, risk_findings, status, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id""",
                name,
                version,
                description,
                author,
                content_hash,
                risk_level,
                risk_score,
                json.dumps(risk_findings),
                status,
                json.dumps(metadata),
            )
            return row["id"]

    async def _create_approval_request(
        self,
        skill_id: int,
        skill_name: str,
        version: str,
        risk_level: str,
        risk_score: float,
        findings: list[str],
    ) -> int:
        """Create an approval request for a skill.

        Returns:
            The approval request ID.
        """
        description = (
            f"Skill '{skill_name}@{version}' requires approval.\n"
            f"Risk level: {risk_level} (score: {risk_score:.1f})\n"
            f"Findings:\n" + "\n".join(f"  - {f}" for f in findings[:5])
        )

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO approval_requests
                (request_type, subject, description, risk_level, metadata)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id""",
                "skill_approval",
                f"{skill_name}@{version}",
                description,
                risk_level,
                json.dumps({"skill_id": skill_id}),
            )
            return row["id"]
