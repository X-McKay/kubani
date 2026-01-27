"""API v1 routes."""

from fastapi import APIRouter

from . import agents, deployments, endpoints, mcp, models, skills, syndicates

router = APIRouter(prefix="/api/v1")

router.include_router(agents.router, prefix="/agents", tags=["agents"])
router.include_router(mcp.router, prefix="/mcp", tags=["mcp"])
router.include_router(skills.router, prefix="/skills", tags=["skills"])
router.include_router(syndicates.router, prefix="/syndicates", tags=["syndicates"])
router.include_router(deployments.router, prefix="/deployments", tags=["deployments"])
router.include_router(models.router, prefix="/models", tags=["models"])
router.include_router(endpoints.router, prefix="/endpoints", tags=["endpoints"])
