"""Agent registry API endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...constants import ResourceStatus
from ...db import Agent, AgentCapability, AgentVersion
from ...db.session import get_session

router = APIRouter()


# Pydantic models for API
class CapabilityCreate(BaseModel):
    """Schema for creating a capability."""

    name: str
    description: str | None = None
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class AgentCreate(BaseModel):
    """Schema for registering an agent."""

    id: str
    name: str
    description: str | None = None
    version: str | None = None
    endpoint: str | None = None
    task_queue: str | None = None
    metadata: dict = Field(default_factory=dict)
    capabilities: list[CapabilityCreate] = Field(default_factory=list)


class CapabilityResponse(BaseModel):
    """Schema for capability response."""

    name: str
    description: str | None
    input_schema: dict
    output_schema: dict
    tags: list[str]

    model_config = {"from_attributes": True}


class AgentResponse(BaseModel):
    """Schema for agent response."""

    id: str
    name: str
    description: str | None
    version: str | None
    endpoint: str | None
    task_queue: str | None
    status: str
    last_heartbeat: datetime | None
    metadata: dict
    capabilities: list[CapabilityResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HeartbeatResponse(BaseModel):
    """Response for heartbeat update."""

    success: bool
    status: str
    last_heartbeat: datetime


class AgentVersionCreate(BaseModel):
    """Schema for creating an agent version."""

    version: str
    oci_tag: str | None = None
    oci_digest: str | None = None
    created_by: str | None = None
    changelog: str | None = None
    metadata: dict = Field(default_factory=dict)


class AgentVersionResponse(BaseModel):
    """Schema for agent version response."""

    id: int
    agent_id: str
    version: str
    oci_tag: str | None
    oci_digest: str | None
    status: str
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


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def register_agent(agent_data: AgentCreate, session: SessionDep) -> dict:
    """Register a new agent or update an existing one."""
    # Check if agent exists with eager loading
    query = select(Agent).where(Agent.id == agent_data.id).options(selectinload(Agent.capabilities))
    result = await session.execute(query)
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing agent
        existing.name = agent_data.name
        existing.description = agent_data.description
        existing.version = agent_data.version
        existing.endpoint = agent_data.endpoint
        existing.task_queue = agent_data.task_queue
        existing.metadata_ = agent_data.metadata
        existing.status = "healthy"
        existing.last_heartbeat = datetime.now(UTC)

        # Delete existing capabilities explicitly
        for cap in list(existing.capabilities):
            await session.delete(cap)
        await session.flush()

        # Add new capabilities
        for cap in agent_data.capabilities:
            existing.capabilities.append(
                AgentCapability(
                    name=cap.name,
                    description=cap.description,
                    input_schema=cap.input_schema,
                    output_schema=cap.output_schema,
                    tags=cap.tags,
                )
            )
        await session.flush()
        # Re-fetch to ensure all fields and relationships are loaded
        await session.refresh(existing)
        return existing.to_dict()
    else:
        # Create new agent
        agent = Agent(
            id=agent_data.id,
            name=agent_data.name,
            description=agent_data.description,
            version=agent_data.version,
            endpoint=agent_data.endpoint,
            task_queue=agent_data.task_queue,
            metadata_=agent_data.metadata,
            status="healthy",
            last_heartbeat=datetime.now(UTC),
        )
        for cap in agent_data.capabilities:
            agent.capabilities.append(
                AgentCapability(
                    name=cap.name,
                    description=cap.description,
                    input_schema=cap.input_schema,
                    output_schema=cap.output_schema,
                    tags=cap.tags,
                )
            )
        session.add(agent)
        await session.flush()
        # Refresh to ensure capabilities are loaded
        await session.refresh(agent, ["capabilities"])
        return agent.to_dict()


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    session: SessionDep,
    status_filter: str | None = None,
) -> list[dict]:
    """List all registered agents."""
    query = select(Agent).options(selectinload(Agent.capabilities))
    if status_filter:
        query = query.where(Agent.status == status_filter)
    result = await session.execute(query)
    return [a.to_dict() for a in result.scalars().all()]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, session: SessionDep) -> dict:
    """Get an agent by ID."""
    query = select(Agent).where(Agent.id == agent_id).options(selectinload(Agent.capabilities))
    result = await session.execute(query)
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return agent.to_dict()


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_agent(agent_id: str, session: SessionDep) -> None:
    """Unregister an agent."""
    agent = await session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    await session.delete(agent)


@router.put("/{agent_id}/heartbeat", response_model=HeartbeatResponse)
async def update_heartbeat(agent_id: str, session: SessionDep) -> dict:
    """Update agent heartbeat."""
    agent = await session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    now = datetime.now(UTC)
    agent.last_heartbeat = now
    agent.status = "healthy"

    return {
        "success": True,
        "status": "healthy",
        "last_heartbeat": now,
    }


@router.get("/capability/{capability_name}", response_model=list[AgentResponse])
async def find_agents_by_capability(capability_name: str, session: SessionDep) -> list[dict]:
    """Find agents that provide a specific capability."""
    query = (
        select(Agent)
        .join(AgentCapability)
        .where(AgentCapability.name == capability_name)
        .options(selectinload(Agent.capabilities))
    )
    result = await session.execute(query)
    return [a.to_dict() for a in result.scalars().all()]


# Version endpoints
@router.post(
    "/{agent_id}/versions",
    response_model=AgentVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_version(
    agent_id: str, version_data: AgentVersionCreate, session: SessionDep
) -> dict:
    """Create a new version of an agent."""
    agent = await session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # Check if version already exists
    query = select(AgentVersion).where(
        AgentVersion.agent_id == agent_id,
        AgentVersion.version == version_data.version,
    )
    result = await session.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version {version_data.version} already exists for agent {agent_id}",
        )

    version = AgentVersion(
        agent_id=agent_id,
        version=version_data.version,
        oci_tag=version_data.oci_tag,
        oci_digest=version_data.oci_digest,
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
        "agent_id": version.agent_id,
        "version": version.version,
        "oci_tag": version.oci_tag,
        "oci_digest": version.oci_digest,
        "status": version.status,
        "created_at": version.created_at,
        "created_by": version.created_by,
        "changelog": version.changelog,
        "promoted_at": version.promoted_at,
        "promoted_by": version.promoted_by,
        "metadata": version.metadata_ or {},
    }


@router.get("/{agent_id}/versions", response_model=list[AgentVersionResponse])
async def list_agent_versions(agent_id: str, session: SessionDep) -> list[dict]:
    """List all versions of an agent."""
    agent = await session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    query = (
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.created_at.desc())
    )
    result = await session.execute(query)
    return [
        {
            "id": v.id,
            "agent_id": v.agent_id,
            "version": v.version,
            "oci_tag": v.oci_tag,
            "oci_digest": v.oci_digest,
            "status": v.status,
            "created_at": v.created_at,
            "created_by": v.created_by,
            "changelog": v.changelog,
            "promoted_at": v.promoted_at,
            "promoted_by": v.promoted_by,
            "metadata": v.metadata_ or {},
        }
        for v in result.scalars().all()
    ]


@router.get("/{agent_id}/versions/latest", response_model=AgentVersionResponse)
async def get_latest_agent_version(agent_id: str, session: SessionDep) -> dict:
    """Get the latest version of an agent."""
    agent = await session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    query = (
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.created_at.desc())
        .limit(1)
    )
    result = await session.execute(query)
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail=f"No versions found for agent {agent_id}")

    return {
        "id": version.id,
        "agent_id": version.agent_id,
        "version": version.version,
        "oci_tag": version.oci_tag,
        "oci_digest": version.oci_digest,
        "status": version.status,
        "created_at": version.created_at,
        "created_by": version.created_by,
        "changelog": version.changelog,
        "promoted_at": version.promoted_at,
        "promoted_by": version.promoted_by,
        "metadata": version.metadata_ or {},
    }


@router.get("/{agent_id}/versions/{version}", response_model=AgentVersionResponse)
async def get_agent_version(agent_id: str, version: str, session: SessionDep) -> dict:
    """Get a specific version of an agent."""
    query = select(AgentVersion).where(
        AgentVersion.agent_id == agent_id,
        AgentVersion.version == version,
    )
    result = await session.execute(query)
    version_obj = result.scalar_one_or_none()
    if not version_obj:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} not found for agent {agent_id}",
        )

    return {
        "id": version_obj.id,
        "agent_id": version_obj.agent_id,
        "version": version_obj.version,
        "oci_tag": version_obj.oci_tag,
        "oci_digest": version_obj.oci_digest,
        "status": version_obj.status,
        "created_at": version_obj.created_at,
        "created_by": version_obj.created_by,
        "changelog": version_obj.changelog,
        "promoted_at": version_obj.promoted_at,
        "promoted_by": version_obj.promoted_by,
        "metadata": version_obj.metadata_ or {},
    }


@router.post(
    "/{agent_id}/versions/{version}/promote",
    response_model=AgentVersionResponse,
)
async def promote_agent_version(
    agent_id: str, version: str, promote_data: PromoteRequest, session: SessionDep
) -> dict:
    """Promote an agent version to the next status in the lifecycle."""
    query = select(AgentVersion).where(
        AgentVersion.agent_id == agent_id,
        AgentVersion.version == version,
    )
    result = await session.execute(query)
    version_obj = result.scalar_one_or_none()
    if not version_obj:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} not found for agent {agent_id}",
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

    # Update agent's current_version if promoted to production
    if new_status == ResourceStatus.PRODUCTION:
        agent = await session.get(Agent, agent_id)
        if agent:
            agent.current_version = version_obj.version

    await session.flush()
    await session.refresh(version_obj)

    return {
        "id": version_obj.id,
        "agent_id": version_obj.agent_id,
        "version": version_obj.version,
        "oci_tag": version_obj.oci_tag,
        "oci_digest": version_obj.oci_digest,
        "status": version_obj.status,
        "created_at": version_obj.created_at,
        "created_by": version_obj.created_by,
        "changelog": version_obj.changelog,
        "promoted_at": version_obj.promoted_at,
        "promoted_by": version_obj.promoted_by,
        "metadata": version_obj.metadata_ or {},
    }
