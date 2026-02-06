"""MCP server registry API endpoints."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db import MCPPolicy, MCPServer
from ...db.session import get_session

router = APIRouter()


# Pydantic models
class MCPServerCreate(BaseModel):
    """Schema for creating an MCP server."""

    id: str
    name: str
    description: str | None = None
    transport: str  # stdio, sse, streamable-http
    connection_config: dict
    capabilities: list[str] = Field(default_factory=list)
    namespaces: list[str] | None = None
    read_only: bool = False
    health_endpoint: str = "/health"
    metrics_endpoint: str = "/metrics"


class MCPServerResponse(BaseModel):
    """Schema for MCP server response."""

    id: str
    name: str
    description: str | None
    transport: str
    connection_config: dict
    capabilities: list[str]
    namespaces: list[str] | None
    read_only: bool
    status: str
    health_endpoint: str
    metrics_endpoint: str
    last_heartbeat: datetime | None
    backend_status: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MCPHeartbeatRequest(BaseModel):
    """Schema for MCP server heartbeat."""

    status: str = Field(description="Server status: healthy, unhealthy, degraded")
    backend_status: dict = Field(
        default_factory=dict, description="Backend health status keyed by backend name"
    )


class MCPPolicyCreate(BaseModel):
    """Schema for creating an MCP policy."""

    agent_pattern: str  # glob pattern
    server_id: str
    allowed_tools: list[str] | None = None
    require_approval: list[str] = Field(default_factory=list)
    namespace_restrictions: dict | None = None
    priority: int = 0


class MCPPolicyResponse(BaseModel):
    """Schema for MCP policy response."""

    id: int
    agent_pattern: str
    server_id: str
    allowed_tools: list[str] | None
    require_approval: list[str]
    namespace_restrictions: dict | None
    priority: int
    created_at: datetime

    model_config = {"from_attributes": True}


class EffectivePolicyResponse(BaseModel):
    """Effective policy for an agent."""

    agent_id: str
    servers: list[MCPServerResponse]
    policies: list[MCPPolicyResponse]


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/servers", response_model=MCPServerResponse, status_code=status.HTTP_201_CREATED)
async def register_mcp_server(server_data: MCPServerCreate, session: SessionDep) -> MCPServer:
    """Register a new MCP server."""
    existing = await session.get(MCPServer, server_data.id)
    if existing:
        raise HTTPException(status_code=400, detail=f"MCP server {server_data.id} already exists")

    server = MCPServer(
        id=server_data.id,
        name=server_data.name,
        description=server_data.description,
        transport=server_data.transport,
        connection_config=server_data.connection_config,
        capabilities=server_data.capabilities,
        namespaces=server_data.namespaces,
        read_only=server_data.read_only,
        health_endpoint=server_data.health_endpoint,
        metrics_endpoint=server_data.metrics_endpoint,
    )
    session.add(server)
    await session.flush()
    return server


@router.get("/servers", response_model=list[MCPServerResponse])
async def list_mcp_servers(
    session: SessionDep, status_filter: str | None = None
) -> list[MCPServer]:
    """
    List all registered MCP servers.

    Args:
        status_filter: Optional filter by status (healthy, unhealthy, inactive)
    """
    query = select(MCPServer)
    if status_filter:
        query = query.where(MCPServer.status == status_filter)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/servers/{server_id}", response_model=MCPServerResponse)
async def get_mcp_server(server_id: str, session: SessionDep) -> MCPServer:
    """Get an MCP server by ID."""
    server = await session.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail=f"MCP server {server_id} not found")
    return server


@router.put("/servers/{server_id}/heartbeat", response_model=MCPServerResponse)
async def update_mcp_server_heartbeat(
    server_id: str, heartbeat: MCPHeartbeatRequest, session: SessionDep
) -> MCPServer:
    """
    Update MCP server heartbeat.

    Updates the last_heartbeat timestamp and status based on the heartbeat data.
    """
    server = await session.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail=f"MCP server {server_id} not found")

    # Update heartbeat timestamp
    server.last_heartbeat = datetime.now(timezone.utc)

    # Update status
    server.status = heartbeat.status

    # Update backend status
    server.backend_status = heartbeat.backend_status

    await session.flush()
    await session.refresh(server)
    return server


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(server_id: str, session: SessionDep) -> None:
    """Delete an MCP server."""
    server = await session.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail=f"MCP server {server_id} not found")
    await session.delete(server)


class MCPPolicyCreateForServer(BaseModel):
    """Schema for creating an MCP policy under a server."""

    agent_pattern: str  # glob pattern
    allowed_tools: list[str] | None = None
    require_approval: list[str] = Field(default_factory=list)
    namespace_restrictions: dict | None = None
    priority: int = 0


@router.post(
    "/servers/{server_id}/policies",
    response_model=MCPPolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_mcp_policy_for_server(
    server_id: str, policy_data: MCPPolicyCreateForServer, session: SessionDep
) -> MCPPolicy:
    """Create a new MCP policy for a specific server."""
    # Verify server exists
    server = await session.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail=f"MCP server {server_id} not found")

    policy = MCPPolicy(
        agent_pattern=policy_data.agent_pattern,
        server_id=server_id,
        allowed_tools=policy_data.allowed_tools,
        require_approval=policy_data.require_approval,
        namespace_restrictions=policy_data.namespace_restrictions,
        priority=policy_data.priority,
    )
    session.add(policy)
    await session.flush()
    await session.refresh(policy)
    return policy


@router.post("/policies", response_model=MCPPolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_mcp_policy(policy_data: MCPPolicyCreate, session: SessionDep) -> MCPPolicy:
    """Create a new MCP policy."""
    # Verify server exists
    server = await session.get(MCPServer, policy_data.server_id)
    if not server:
        raise HTTPException(status_code=404, detail=f"MCP server {policy_data.server_id} not found")

    policy = MCPPolicy(
        agent_pattern=policy_data.agent_pattern,
        server_id=policy_data.server_id,
        allowed_tools=policy_data.allowed_tools,
        require_approval=policy_data.require_approval,
        namespace_restrictions=policy_data.namespace_restrictions,
        priority=policy_data.priority,
    )
    session.add(policy)
    await session.flush()
    await session.refresh(policy)
    return policy


@router.get("/policy/{agent_id}", response_model=EffectivePolicyResponse)
async def get_effective_policy(agent_id: str, session: SessionDep) -> dict:
    """
    Get the effective MCP policy for an agent.

    Matches policies by agent_pattern (glob) against the agent_id.
    Returns all matching servers and policies ordered by priority.
    """
    import fnmatch

    # Get all policies
    result = await session.execute(
        select(MCPPolicy)
        .options(selectinload(MCPPolicy.server))
        .order_by(MCPPolicy.priority.desc())
    )
    all_policies = result.scalars().all()

    # Filter by pattern match
    matching_policies = []
    matching_servers = []
    seen_servers = set()

    for policy in all_policies:
        if fnmatch.fnmatch(agent_id, policy.agent_pattern):
            matching_policies.append(policy)
            if policy.server_id not in seen_servers:
                matching_servers.append(policy.server)
                seen_servers.add(policy.server_id)

    return {
        "agent_id": agent_id,
        "servers": matching_servers,
        "policies": matching_policies,
    }
