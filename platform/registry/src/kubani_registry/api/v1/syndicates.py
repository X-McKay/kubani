"""Syndicate registry API endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...constants import ResourceStatus
from ...db import Syndicate, SyndicateVersion
from ...db.session import get_session

router = APIRouter()


# Pydantic models for API
class SyndicateCreate(BaseModel):
    """Schema for creating a syndicate."""

    id: str
    name: str
    description: str | None = None
    oci_repository: str | None = None
    created_by: str | None = None
    metadata: dict = Field(default_factory=dict)


class SyndicateResponse(BaseModel):
    """Schema for syndicate response."""

    id: str
    name: str
    description: str | None
    current_version: str | None
    oci_repository: str | None
    status: str
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    metadata: dict

    model_config = {"from_attributes": True}


class SyndicateVersionCreate(BaseModel):
    """Schema for creating a syndicate version."""

    version: str
    oci_tag: str | None = None
    oci_digest: str | None = None
    agent_refs: list[dict] = Field(default_factory=list)  # [{agent: str, version: str}]
    created_by: str | None = None
    changelog: str | None = None
    metadata: dict = Field(default_factory=dict)


class SyndicateVersionResponse(BaseModel):
    """Schema for syndicate version response."""

    id: int
    syndicate_id: str
    version: str
    oci_tag: str | None
    oci_digest: str | None
    status: str
    agent_refs: list[dict]
    created_at: datetime
    created_by: str | None
    changelog: str | None
    promoted_at: datetime | None
    promoted_by: str | None
    metadata: dict

    model_config = {"from_attributes": True}


class PromoteRequest(BaseModel):
    """Schema for promotion request."""

    promoted_by: str


# Dependencies
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=SyndicateResponse, status_code=status.HTTP_201_CREATED)
async def create_syndicate(syndicate_data: SyndicateCreate, session: SessionDep) -> dict:
    """Create a new syndicate."""
    # Check if syndicate exists
    existing = await session.get(Syndicate, syndicate_data.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Syndicate {syndicate_data.id} already exists",
        )

    syndicate = Syndicate(
        id=syndicate_data.id,
        name=syndicate_data.name,
        description=syndicate_data.description,
        oci_repository=syndicate_data.oci_repository,
        created_by=syndicate_data.created_by,
        status=ResourceStatus.DRAFT.value,
        metadata_=syndicate_data.metadata,
    )
    session.add(syndicate)
    await session.flush()
    await session.refresh(syndicate)
    return syndicate.to_dict()


@router.get("", response_model=list[SyndicateResponse])
async def list_syndicates(
    session: SessionDep,
    status_filter: str | None = None,
) -> list[dict]:
    """List all syndicates."""
    query = select(Syndicate)
    if status_filter:
        query = query.where(Syndicate.status == status_filter)
    result = await session.execute(query)
    return [s.to_dict() for s in result.scalars().all()]


@router.get("/{syndicate_id}", response_model=SyndicateResponse)
async def get_syndicate(syndicate_id: str, session: SessionDep) -> dict:
    """Get a syndicate by ID."""
    query = (
        select(Syndicate)
        .where(Syndicate.id == syndicate_id)
        .options(selectinload(Syndicate.versions))
    )
    result = await session.execute(query)
    syndicate = result.scalar_one_or_none()
    if not syndicate:
        raise HTTPException(status_code=404, detail=f"Syndicate {syndicate_id} not found")
    return syndicate.to_dict()


@router.delete("/{syndicate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_syndicate(syndicate_id: str, session: SessionDep) -> None:
    """Delete a syndicate."""
    syndicate = await session.get(Syndicate, syndicate_id)
    if not syndicate:
        raise HTTPException(status_code=404, detail=f"Syndicate {syndicate_id} not found")
    await session.delete(syndicate)


# Version endpoints
@router.post(
    "/{syndicate_id}/versions",
    response_model=SyndicateVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_syndicate_version(
    syndicate_id: str, version_data: SyndicateVersionCreate, session: SessionDep
) -> dict:
    """Create a new version of a syndicate."""
    syndicate = await session.get(Syndicate, syndicate_id)
    if not syndicate:
        raise HTTPException(status_code=404, detail=f"Syndicate {syndicate_id} not found")

    # Check if version already exists
    query = select(SyndicateVersion).where(
        SyndicateVersion.syndicate_id == syndicate_id,
        SyndicateVersion.version == version_data.version,
    )
    result = await session.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version {version_data.version} already exists for syndicate {syndicate_id}",
        )

    version = SyndicateVersion(
        syndicate_id=syndicate_id,
        version=version_data.version,
        oci_tag=version_data.oci_tag,
        oci_digest=version_data.oci_digest,
        agent_refs=version_data.agent_refs,
        status=ResourceStatus.DRAFT.value,
        created_by=version_data.created_by,
        changelog=version_data.changelog,
        metadata_=version_data.metadata,
    )
    session.add(version)
    await session.flush()
    await session.refresh(version)

    return {
        "id": version.id,
        "syndicate_id": version.syndicate_id,
        "version": version.version,
        "oci_tag": version.oci_tag,
        "oci_digest": version.oci_digest,
        "status": version.status,
        "agent_refs": version.agent_refs or [],
        "created_at": version.created_at,
        "created_by": version.created_by,
        "changelog": version.changelog,
        "promoted_at": version.promoted_at,
        "promoted_by": version.promoted_by,
        "metadata": version.metadata_ or {},
    }


@router.get("/{syndicate_id}/versions", response_model=list[SyndicateVersionResponse])
async def list_syndicate_versions(syndicate_id: str, session: SessionDep) -> list[dict]:
    """List all versions of a syndicate."""
    syndicate = await session.get(Syndicate, syndicate_id)
    if not syndicate:
        raise HTTPException(status_code=404, detail=f"Syndicate {syndicate_id} not found")

    query = (
        select(SyndicateVersion)
        .where(SyndicateVersion.syndicate_id == syndicate_id)
        .order_by(SyndicateVersion.created_at.desc())
    )
    result = await session.execute(query)
    return [
        {
            "id": v.id,
            "syndicate_id": v.syndicate_id,
            "version": v.version,
            "oci_tag": v.oci_tag,
            "oci_digest": v.oci_digest,
            "status": v.status,
            "agent_refs": v.agent_refs or [],
            "created_at": v.created_at,
            "created_by": v.created_by,
            "changelog": v.changelog,
            "promoted_at": v.promoted_at,
            "promoted_by": v.promoted_by,
            "metadata": v.metadata_ or {},
        }
        for v in result.scalars().all()
    ]


@router.get("/{syndicate_id}/versions/latest", response_model=SyndicateVersionResponse)
async def get_latest_syndicate_version(syndicate_id: str, session: SessionDep) -> dict:
    """Get the latest version of a syndicate."""
    syndicate = await session.get(Syndicate, syndicate_id)
    if not syndicate:
        raise HTTPException(status_code=404, detail=f"Syndicate {syndicate_id} not found")

    query = (
        select(SyndicateVersion)
        .where(SyndicateVersion.syndicate_id == syndicate_id)
        .order_by(SyndicateVersion.created_at.desc())
        .limit(1)
    )
    result = await session.execute(query)
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(
            status_code=404, detail=f"No versions found for syndicate {syndicate_id}"
        )

    return {
        "id": version.id,
        "syndicate_id": version.syndicate_id,
        "version": version.version,
        "oci_tag": version.oci_tag,
        "oci_digest": version.oci_digest,
        "status": version.status,
        "agent_refs": version.agent_refs or [],
        "created_at": version.created_at,
        "created_by": version.created_by,
        "changelog": version.changelog,
        "promoted_at": version.promoted_at,
        "promoted_by": version.promoted_by,
        "metadata": version.metadata_ or {},
    }


@router.get("/{syndicate_id}/versions/{version}", response_model=SyndicateVersionResponse)
async def get_syndicate_version(syndicate_id: str, version: str, session: SessionDep) -> dict:
    """Get a specific version of a syndicate."""
    query = select(SyndicateVersion).where(
        SyndicateVersion.syndicate_id == syndicate_id,
        SyndicateVersion.version == version,
    )
    result = await session.execute(query)
    version_obj = result.scalar_one_or_none()
    if not version_obj:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} not found for syndicate {syndicate_id}",
        )

    return {
        "id": version_obj.id,
        "syndicate_id": version_obj.syndicate_id,
        "version": version_obj.version,
        "oci_tag": version_obj.oci_tag,
        "oci_digest": version_obj.oci_digest,
        "status": version_obj.status,
        "agent_refs": version_obj.agent_refs or [],
        "created_at": version_obj.created_at,
        "created_by": version_obj.created_by,
        "changelog": version_obj.changelog,
        "promoted_at": version_obj.promoted_at,
        "promoted_by": version_obj.promoted_by,
        "metadata": version_obj.metadata_ or {},
    }


@router.post(
    "/{syndicate_id}/versions/{version}/promote",
    response_model=SyndicateVersionResponse,
)
async def promote_syndicate_version(
    syndicate_id: str, version: str, promote_data: PromoteRequest, session: SessionDep
) -> dict:
    """Promote a syndicate version to the next status in the lifecycle."""
    query = select(SyndicateVersion).where(
        SyndicateVersion.syndicate_id == syndicate_id,
        SyndicateVersion.version == version,
    )
    result = await session.execute(query)
    version_obj = result.scalar_one_or_none()
    if not version_obj:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} not found for syndicate {syndicate_id}",
        )

    current_status = ResourceStatus(version_obj.status)
    promotion_order = ResourceStatus.promotion_order()

    if current_status not in promotion_order:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot promote from status {current_status.value}",
        )

    current_index = promotion_order.index(current_status)
    if current_index >= len(promotion_order) - 1:
        raise HTTPException(
            status_code=400,
            detail=f"Already at highest status: {current_status.value}",
        )

    new_status = promotion_order[current_index + 1]
    version_obj.status = new_status.value
    version_obj.promoted_at = datetime.now(UTC)
    version_obj.promoted_by = promote_data.promoted_by

    # Update syndicate's current_version if promoted to production
    if new_status == ResourceStatus.PRODUCTION:
        syndicate = await session.get(Syndicate, syndicate_id)
        if syndicate:
            syndicate.current_version = version_obj.version
            syndicate.status = ResourceStatus.PRODUCTION.value

    await session.flush()
    await session.refresh(version_obj)

    return {
        "id": version_obj.id,
        "syndicate_id": version_obj.syndicate_id,
        "version": version_obj.version,
        "oci_tag": version_obj.oci_tag,
        "oci_digest": version_obj.oci_digest,
        "status": version_obj.status,
        "agent_refs": version_obj.agent_refs or [],
        "created_at": version_obj.created_at,
        "created_by": version_obj.created_by,
        "changelog": version_obj.changelog,
        "promoted_at": version_obj.promoted_at,
        "promoted_by": version_obj.promoted_by,
        "metadata": version_obj.metadata_ or {},
    }
