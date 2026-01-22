"""Skill metadata API endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import SkillMetadata
from ...db.session import get_session

router = APIRouter()


class SkillMetadataCreate(BaseModel):
    """Schema for creating skill metadata."""

    id: str
    name: str
    domain: str
    category: str
    status: str = "proposed"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    success_count: int = 0
    failure_count: int = 0
    requires_approval: bool = False


class SkillMetadataResponse(BaseModel):
    """Schema for skill metadata response."""

    id: str
    name: str
    domain: str
    category: str
    status: str
    confidence: float
    success_count: int
    failure_count: int
    requires_approval: bool
    created_at: datetime
    validated_at: datetime | None
    last_used: datetime | None

    model_config = {"from_attributes": True}


class SkillOutcomeRequest(BaseModel):
    """Schema for recording skill outcome."""

    success: bool
    context: dict | None = None


class SkillOutcomeResponse(BaseModel):
    """Response for skill outcome recording."""

    skill_id: str
    new_confidence: float
    confidence: float  # Alias for new_confidence
    success_count: int
    failure_count: int


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=SkillMetadataResponse, status_code=status.HTTP_201_CREATED)
async def create_skill_metadata(
    skill_data: SkillMetadataCreate, session: SessionDep
) -> SkillMetadata:
    """Create or update skill metadata."""
    existing = await session.get(SkillMetadata, skill_data.id)
    if existing:
        # Update existing
        existing.name = skill_data.name
        existing.domain = skill_data.domain
        existing.category = skill_data.category
        existing.status = skill_data.status
        existing.confidence = skill_data.confidence
        existing.requires_approval = skill_data.requires_approval
        await session.flush()
        return existing

    skill = SkillMetadata(
        id=skill_data.id,
        name=skill_data.name,
        domain=skill_data.domain,
        category=skill_data.category,
        status=skill_data.status,
        confidence=skill_data.confidence,
        success_count=skill_data.success_count,
        failure_count=skill_data.failure_count,
        requires_approval=skill_data.requires_approval,
    )
    session.add(skill)
    await session.flush()
    return skill


@router.get("", response_model=list[SkillMetadataResponse])
async def list_skills(
    session: SessionDep,
    domain: str | None = None,
    category: str | None = None,
    status_filter: str | None = None,
    min_confidence: float | None = None,
) -> list[SkillMetadata]:
    """List skill metadata with optional filters."""
    query = select(SkillMetadata)
    if domain:
        query = query.where(SkillMetadata.domain == domain)
    if category:
        query = query.where(SkillMetadata.category == category)
    if status_filter:
        query = query.where(SkillMetadata.status == status_filter)
    if min_confidence is not None:
        query = query.where(SkillMetadata.confidence >= min_confidence)

    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/{skill_id}", response_model=SkillMetadataResponse)
async def get_skill(skill_id: str, session: SessionDep) -> SkillMetadata:
    """Get skill metadata by ID."""
    skill = await session.get(SkillMetadata, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return skill


@router.put("/{skill_id}/outcome", response_model=SkillOutcomeResponse)
async def record_outcome(skill_id: str, outcome: SkillOutcomeRequest, session: SessionDep) -> dict:
    """
    Record skill execution outcome and update confidence.

    Uses simple weighted average for confidence updates.
    """
    skill = await session.get(SkillMetadata, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    # Update counts
    if outcome.success:
        skill.success_count += 1
    else:
        skill.failure_count += 1

    # Update confidence: weighted average
    total = skill.success_count + skill.failure_count
    if total > 0:
        success_rate = skill.success_count / total
        # Blend current confidence with success rate
        skill.confidence = 0.7 * success_rate + 0.3 * skill.confidence

    # Update last_used
    skill.last_used = datetime.now(UTC)

    await session.flush()

    return {
        "skill_id": skill_id,
        "new_confidence": skill.confidence,
        "confidence": skill.confidence,  # Alias for convenience
        "success_count": skill.success_count,
        "failure_count": skill.failure_count,
    }


@router.put("/{skill_id}/status")
async def update_skill_status(
    skill_id: str, new_status: str, session: SessionDep
) -> SkillMetadataResponse:
    """Update skill validation status."""
    skill = await session.get(SkillMetadata, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    valid_statuses = ["proposed", "testing", "experimental", "stable", "deprecated", "failed"]
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}",
        )

    old_status = skill.status
    skill.status = new_status

    # Track validation timestamp
    if new_status == "stable" and old_status != "stable":
        skill.validated_at = datetime.now(UTC)

    await session.flush()
    return skill
