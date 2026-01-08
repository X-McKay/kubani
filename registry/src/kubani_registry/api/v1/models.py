"""LLM model registry API endpoints."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db import Model, ModelEndpoint
from ...db.session import get_session

router = APIRouter()


class ModelCreate(BaseModel):
    """Schema for registering a model."""

    id: str  # e.g., "nvidia/Qwen3-14B-FP4"
    name: str
    model_type: str  # general, coding, embeddings, vision
    provider: str | None = None
    quantization: str | None = None
    context_length: int | None = None
    vram_required_gb: float | None = None
    capabilities: dict = Field(default_factory=dict)
    local_path: str | None = None
    metadata: dict = Field(default_factory=dict)


class ModelResponse(BaseModel):
    """Schema for model response."""

    id: str
    name: str
    model_type: str
    provider: str | None
    quantization: str | None
    context_length: int | None
    vram_required_gb: float | None
    capabilities: dict
    local_path: str | None
    status: str
    created_at: datetime
    metadata: dict

    model_config = {"from_attributes": True}


class ModelEndpointCreate(BaseModel):
    """Schema for associating a model with an endpoint."""

    endpoint_id: str
    is_primary: bool = False


class ModelEndpointResponse(BaseModel):
    """Schema for model endpoint association."""

    endpoint_id: str
    is_primary: bool

    model_config = {"from_attributes": True}


class ModelWithEndpointsResponse(ModelResponse):
    """Model response including endpoint associations."""

    endpoints: list[str]


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
async def register_model(model_data: ModelCreate, session: SessionDep) -> dict:
    """Register a new model."""
    existing = await session.get(Model, model_data.id)
    if existing:
        # Update existing model
        existing.name = model_data.name
        existing.model_type = model_data.model_type
        existing.provider = model_data.provider
        existing.quantization = model_data.quantization
        existing.context_length = model_data.context_length
        existing.vram_required_gb = model_data.vram_required_gb
        existing.capabilities = model_data.capabilities
        existing.local_path = model_data.local_path
        existing.metadata_ = model_data.metadata
        await session.flush()
        return existing.to_dict()

    model = Model(
        id=model_data.id,
        name=model_data.name,
        model_type=model_data.model_type,
        provider=model_data.provider,
        quantization=model_data.quantization,
        context_length=model_data.context_length,
        vram_required_gb=model_data.vram_required_gb,
        capabilities=model_data.capabilities,
        local_path=model_data.local_path,
        metadata_=model_data.metadata,
    )
    session.add(model)
    await session.flush()
    return model.to_dict()


@router.get("", response_model=list[ModelResponse])
async def list_models(
    session: SessionDep,
    model_type: str | None = None,
    status_filter: str | None = None,
) -> list[dict]:
    """List all registered models."""
    query = select(Model)
    if model_type:
        query = query.where(Model.model_type == model_type)
    if status_filter:
        query = query.where(Model.status == status_filter)

    result = await session.execute(query)
    return [m.to_dict() for m in result.scalars().all()]


@router.get("/type/{model_type}", response_model=list[ModelResponse])
async def list_models_by_type(model_type: str, session: SessionDep) -> list[dict]:
    """List models by type (general, coding, embeddings, vision)."""
    result = await session.execute(select(Model).where(Model.model_type == model_type))
    return [m.to_dict() for m in result.scalars().all()]


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(model_id: str, session: SessionDep) -> dict:
    """Get model by ID."""
    model = await session.get(Model, model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return model.to_dict()


@router.put("/{model_id}/status")
async def update_model_status(model_id: str, new_status: str, session: SessionDep) -> dict:
    """Update model availability status."""
    model = await session.get(Model, model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    valid_statuses = ["available", "loading", "unavailable", "error"]
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}",
        )

    model.status = new_status
    await session.flush()
    return model.to_dict()


@router.get("/{model_id}/endpoints", response_model=list[str])
async def get_model_endpoints(model_id: str, session: SessionDep) -> list[str]:
    """Get endpoints serving a model."""
    model = await session.get(Model, model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    result = await session.execute(
        select(Model).where(Model.id == model_id).options(selectinload(Model.model_endpoints))
    )
    model = result.scalar_one()
    return [me.endpoint_id for me in model.model_endpoints]


@router.post("/{model_id}/endpoints", status_code=status.HTTP_201_CREATED)
async def associate_model_endpoint(
    model_id: str,
    endpoint_data: ModelEndpointCreate,
    session: SessionDep,
) -> dict:
    """Associate a model with an endpoint."""
    model = await session.get(Model, model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    # Check if association already exists
    result = await session.execute(
        select(ModelEndpoint)
        .where(ModelEndpoint.model_id == model_id)
        .where(ModelEndpoint.endpoint_id == endpoint_data.endpoint_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.is_primary = endpoint_data.is_primary
        await session.flush()
        return {"message": "Association updated"}

    assoc = ModelEndpoint(
        model_id=model_id,
        endpoint_id=endpoint_data.endpoint_id,
        is_primary=endpoint_data.is_primary,
    )
    session.add(assoc)
    await session.flush()
    return {"message": "Association created"}
