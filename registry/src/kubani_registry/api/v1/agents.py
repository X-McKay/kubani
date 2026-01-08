"""Agent registry API endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db import Agent, AgentCapability
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

        # Clear and re-add capabilities
        existing.capabilities.clear()
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
