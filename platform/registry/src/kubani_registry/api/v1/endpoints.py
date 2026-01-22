"""Service endpoint registry API endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import Endpoint, EndpointDependency
from ...db.session import get_session

router = APIRouter()


class EndpointCreate(BaseModel):
    """Schema for registering an endpoint."""

    id: str  # e.g., "vllm-general", "temporal-frontend"
    name: str
    service_type: str  # llm, embeddings, mcp, temporal, database
    internal_url: str | None = None
    external_url: str | None = None
    health_check_path: str = "/health"
    namespace: str | None = None
    environment: str = "production"
    metadata: dict = Field(default_factory=dict)


class EndpointResponse(BaseModel):
    """Schema for endpoint response."""

    id: str
    name: str
    service_type: str
    internal_url: str | None
    external_url: str | None
    health_check_path: str
    status: str
    last_health_check: datetime | None
    namespace: str | None
    environment: str
    metadata: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HealthUpdateRequest(BaseModel):
    """Schema for health status update."""

    status: str  # healthy, unhealthy, unknown
    details: dict | None = None


class DependencyCreate(BaseModel):
    """Schema for registering a dependency."""

    dependent_id: str
    dependent_type: str  # agent, service
    is_required: bool = True


class DependencyResponse(BaseModel):
    """Schema for dependency response."""

    dependent_id: str
    dependent_type: str
    endpoint_id: str
    is_required: bool

    model_config = {"from_attributes": True}


class ResolvedEndpoint(BaseModel):
    """Resolved endpoint URL."""

    endpoint_id: str
    url: str
    is_internal: bool
    status: str


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=EndpointResponse, status_code=status.HTTP_201_CREATED)
async def register_endpoint(endpoint_data: EndpointCreate, session: SessionDep) -> dict:
    """Register a new endpoint."""
    existing = await session.get(Endpoint, endpoint_data.id)
    if existing:
        # Update existing endpoint
        existing.name = endpoint_data.name
        existing.service_type = endpoint_data.service_type
        existing.internal_url = endpoint_data.internal_url
        existing.external_url = endpoint_data.external_url
        existing.health_check_path = endpoint_data.health_check_path
        existing.namespace = endpoint_data.namespace
        existing.environment = endpoint_data.environment
        existing.metadata_ = endpoint_data.metadata
        await session.flush()
        return existing.to_dict()

    endpoint = Endpoint(
        id=endpoint_data.id,
        name=endpoint_data.name,
        service_type=endpoint_data.service_type,
        internal_url=endpoint_data.internal_url,
        external_url=endpoint_data.external_url,
        health_check_path=endpoint_data.health_check_path,
        namespace=endpoint_data.namespace,
        environment=endpoint_data.environment,
        metadata_=endpoint_data.metadata,
    )
    session.add(endpoint)
    await session.flush()
    return endpoint.to_dict()


@router.get("", response_model=list[EndpointResponse])
async def list_endpoints(
    session: SessionDep,
    service_type: str | None = None,
    status_filter: str | None = None,
    environment: str | None = None,
) -> list[dict]:
    """List all registered endpoints."""
    query = select(Endpoint)
    if service_type:
        query = query.where(Endpoint.service_type == service_type)
    if status_filter:
        query = query.where(Endpoint.status == status_filter)
    if environment:
        query = query.where(Endpoint.environment == environment)

    result = await session.execute(query)
    return [e.to_dict() for e in result.scalars().all()]


@router.get("/type/{service_type}", response_model=list[EndpointResponse])
async def list_endpoints_by_type(service_type: str, session: SessionDep) -> list[dict]:
    """List endpoints by service type."""
    result = await session.execute(select(Endpoint).where(Endpoint.service_type == service_type))
    return [e.to_dict() for e in result.scalars().all()]


@router.get("/{endpoint_id}", response_model=EndpointResponse)
async def get_endpoint(endpoint_id: str, session: SessionDep) -> dict:
    """Get endpoint by ID."""
    endpoint = await session.get(Endpoint, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail=f"Endpoint {endpoint_id} not found")
    return endpoint.to_dict()


@router.put("/{endpoint_id}/health")
async def update_health_status(
    endpoint_id: str, health: HealthUpdateRequest, session: SessionDep
) -> dict:
    """Update endpoint health status."""
    endpoint = await session.get(Endpoint, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail=f"Endpoint {endpoint_id} not found")

    valid_statuses = ["healthy", "unhealthy", "unknown", "degraded"]
    if health.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}",
        )

    endpoint.status = health.status
    endpoint.last_health_check = datetime.now(UTC)
    if health.details:
        # Create a new dict to ensure change detection
        new_metadata = dict(endpoint.metadata_ or {})
        new_metadata["last_health_details"] = health.details
        endpoint.metadata_ = new_metadata

    await session.flush()
    await session.refresh(endpoint)
    return endpoint.to_dict()


@router.get("/resolve/{endpoint_id}", response_model=ResolvedEndpoint)
async def resolve_endpoint(
    endpoint_id: str,
    session: SessionDep,
    prefer_internal: bool = Query(default=True),
) -> dict:
    """
    Resolve endpoint to best available URL.

    If prefer_internal is True, returns internal_url if available,
    otherwise external_url. Returns the healthy option if only one is healthy.
    """
    endpoint = await session.get(Endpoint, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail=f"Endpoint {endpoint_id} not found")

    # Prefer internal URL for in-cluster access
    if prefer_internal and endpoint.internal_url:
        return {
            "endpoint_id": endpoint_id,
            "url": endpoint.internal_url,
            "is_internal": True,
            "status": endpoint.status,
        }
    elif endpoint.external_url:
        return {
            "endpoint_id": endpoint_id,
            "url": endpoint.external_url,
            "is_internal": False,
            "status": endpoint.status,
        }
    elif endpoint.internal_url:
        return {
            "endpoint_id": endpoint_id,
            "url": endpoint.internal_url,
            "is_internal": True,
            "status": endpoint.status,
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"No URL available for endpoint {endpoint_id}",
        )


@router.post("/{endpoint_id}/dependencies", status_code=status.HTTP_201_CREATED)
async def register_dependency(
    endpoint_id: str, dep_data: DependencyCreate, session: SessionDep
) -> dict:
    """Register a dependency on an endpoint."""
    endpoint = await session.get(Endpoint, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail=f"Endpoint {endpoint_id} not found")

    # Check if dependency exists
    result = await session.execute(
        select(EndpointDependency)
        .where(EndpointDependency.endpoint_id == endpoint_id)
        .where(EndpointDependency.dependent_id == dep_data.dependent_id)
        .where(EndpointDependency.dependent_type == dep_data.dependent_type)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.is_required = dep_data.is_required
        await session.flush()
        return {"message": "Dependency updated"}

    dep = EndpointDependency(
        dependent_id=dep_data.dependent_id,
        dependent_type=dep_data.dependent_type,
        endpoint_id=endpoint_id,
        is_required=dep_data.is_required,
    )
    session.add(dep)
    await session.flush()
    return {"message": "Dependency registered"}


@router.get("/dependencies/{agent_id}", response_model=list[EndpointResponse])
async def get_agent_dependencies(agent_id: str, session: SessionDep) -> list[dict]:
    """Get all endpoints an agent depends on."""
    result = await session.execute(
        select(Endpoint)
        .join(EndpointDependency)
        .where(EndpointDependency.dependent_id == agent_id)
        .where(EndpointDependency.dependent_type == "agent")
    )
    return [e.to_dict() for e in result.scalars().all()]
