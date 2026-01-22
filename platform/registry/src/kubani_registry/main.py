"""
Kubani Registry Service - Main FastAPI application.

Centralized metadata registry for agents, MCP servers, skills, deployments,
models, and endpoints in the Kubani ecosystem.
"""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from .api.v1 import router as api_router
from .config import get_settings
from .db.session import close_db, create_tables, init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    import asyncio

    from .services.discovery import start_discovery_service

    settings = get_settings()
    discovery_task: asyncio.Task | None = None

    # Configure logging level from settings
    logging.getLogger().setLevel(settings.log_level)

    # Initialize database
    logger.info("Initializing database connection...")
    await init_db(settings.database_url, echo=settings.database_echo)

    # Create tables if they don't exist
    logger.info("Creating database tables...")
    await create_tables()

    # Start service discovery (runs in background)
    try:
        discovery_task = await start_discovery_service()
        if discovery_task:
            logger.info("Service discovery started")
    except Exception as e:
        logger.warning("Failed to start service discovery: %s", e)

    logger.info("Registry service started successfully")

    yield

    # Cleanup
    logger.info("Shutting down registry service...")

    # Stop discovery task
    if discovery_task is not None:
        discovery_task.cancel()
        try:
            await discovery_task
        except asyncio.CancelledError:
            logger.info("Service discovery stopped")

    await close_db()


# Create FastAPI app
app = FastAPI(
    title="Kubani Registry Service",
    description="Centralized metadata registry for the Kubani AI agent ecosystem",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router)


@app.get("/health")
async def health_check() -> dict:
    """Liveness probe - is the service running?"""
    return {"status": "healthy", "service": "kubani-registry"}


@app.get("/ready")
async def readiness_check() -> dict:
    """
    Readiness probe - is the service ready to accept traffic?

    Checks database connectivity.
    """
    from sqlalchemy import text

    from .db.session import get_session_factory

    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        return {"status": "not_ready", "database": "disconnected", "error": str(e)}


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def main() -> None:
    """Entry point for the registry service."""
    settings = get_settings()
    uvicorn.run(
        "kubani_registry.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
