"""Deployment tracking API endpoints."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import Deployment
from ...db.session import get_session

router = APIRouter()


class DeploymentCreate(BaseModel):
    """Schema for recording a deployment."""

    agent_id: str
    version: str
    image_tag: str | None = None
    git_sha: str | None = None
    deployed_by: str | None = None
    config_snapshot: dict | None = None


class DeploymentResponse(BaseModel):
    """Schema for deployment response."""

    id: int
    agent_id: str
    version: str
    image_tag: str | None
    git_sha: str | None
    deployed_at: datetime
    deployed_by: str | None
    config_snapshot: dict | None
    status: str
    rollback_from: int | None

    model_config = {"from_attributes": True}


class RollbackRequest(BaseModel):
    """Schema for rollback request."""

    reason: str | None = None


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=DeploymentResponse, status_code=status.HTTP_201_CREATED)
async def record_deployment(deploy_data: DeploymentCreate, session: SessionDep) -> Deployment:
    """Record a new deployment."""
    # Mark previous deployments as inactive
    result = await session.execute(
        select(Deployment)
        .where(Deployment.agent_id == deploy_data.agent_id)
        .where(Deployment.status == "active")
    )
    for old_deploy in result.scalars().all():
        old_deploy.status = "superseded"

    deployment = Deployment(
        agent_id=deploy_data.agent_id,
        version=deploy_data.version,
        image_tag=deploy_data.image_tag,
        git_sha=deploy_data.git_sha,
        deployed_by=deploy_data.deployed_by,
        config_snapshot=deploy_data.config_snapshot,
        status="active",
    )
    session.add(deployment)
    await session.flush()
    return deployment


@router.get("", response_model=list[DeploymentResponse])
async def list_deployments(
    session: SessionDep,
    agent_id: str | None = None,
    limit: int = Query(default=50, le=100),
) -> list[Deployment]:
    """List deployments with optional agent filter."""
    query = select(Deployment).order_by(Deployment.deployed_at.desc()).limit(limit)
    if agent_id:
        query = query.where(Deployment.agent_id == agent_id)

    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/agent/{agent_id}", response_model=list[DeploymentResponse])
async def get_agent_deployments(
    agent_id: str,
    session: SessionDep,
    limit: int = Query(default=20, le=100),
) -> list[Deployment]:
    """Get deployment history for an agent."""
    result = await session.execute(
        select(Deployment)
        .where(Deployment.agent_id == agent_id)
        .order_by(Deployment.deployed_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.get("/agent/{agent_id}/latest", response_model=DeploymentResponse)
async def get_latest_deployment(agent_id: str, session: SessionDep) -> Deployment:
    """Get the latest active deployment for an agent."""
    result = await session.execute(
        select(Deployment)
        .where(Deployment.agent_id == agent_id)
        .where(Deployment.status == "active")
        .order_by(Deployment.deployed_at.desc())
        .limit(1)
    )
    deployment = result.scalar_one_or_none()
    if not deployment:
        raise HTTPException(
            status_code=404,
            detail=f"No active deployment found for agent {agent_id}",
        )
    return deployment


@router.post("/{deployment_id}/rollback", response_model=DeploymentResponse)
async def rollback_deployment(
    deployment_id: int,
    session: SessionDep,
    rollback: RollbackRequest | None = None,
) -> Deployment:
    """
    Record a rollback to a previous deployment.

    Creates a new deployment record pointing to the rolled-back version.
    """
    # Get the deployment to roll back to
    target = await session.get(Deployment, deployment_id)
    if not target:
        raise HTTPException(status_code=404, detail=f"Deployment {deployment_id} not found")

    # Get current active deployment
    result = await session.execute(
        select(Deployment)
        .where(Deployment.agent_id == target.agent_id)
        .where(Deployment.status == "active")
        .limit(1)
    )
    current = result.scalar_one_or_none()
    if current:
        current.status = "rolled-back"

    # Create new deployment record for rollback
    reason = rollback.reason if rollback and rollback.reason else None
    rollback_deploy = Deployment(
        agent_id=target.agent_id,
        version=target.version,
        image_tag=target.image_tag,
        git_sha=target.git_sha,
        deployed_by=f"rollback:{reason}" if reason else "rollback",
        config_snapshot=target.config_snapshot,
        status="active",
        rollback_from=deployment_id,
    )
    session.add(rollback_deploy)
    await session.flush()
    return rollback_deploy
