"""
Learning Agent Server.

FastAPI server that runs the Voyager-style continuous learning system.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from fastapi import FastAPI
from pydantic import BaseModel

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Global learning manager
_learning_manager = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: str
    version: str = "0.1.0"


class ReadyResponse(BaseModel):
    """Readiness check response."""

    status: str
    learning_enabled: bool
    critic_enabled: bool
    reflection_enabled: bool
    synthesizer_enabled: bool
    passive_monitoring_enabled: bool = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global _learning_manager

    logger.info("Starting Learning Agent...")

    try:
        # Import here to avoid circular imports
        from core_agents.learning.voyager.manager import LearningConfig, LearningManager

        # Build config from environment
        config = LearningConfig(
            llm_api_url=os.environ.get("LLM_API_URL", "http://localhost:8000/v1"),
            llm_model=os.environ.get("LLM_MODEL", "nvidia/Qwen3-14B-FP4"),
            qdrant_host=os.environ.get("QDRANT_HOST", "localhost"),
            qdrant_port=int(os.environ.get("QDRANT_PORT", "6333")),
            neo4j_uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
            neo4j_password=os.environ.get("NEO4J_PASSWORD", ""),
            embeddings_api_url=os.environ.get("EMBEDDINGS_API_URL", "http://localhost:8001/v1"),
            discord_mcp_url=os.environ.get("MCP_DISCORD_URL", "http://localhost:8084"),
            learning_channel=os.environ.get("DISCORD_LEARNING_CHANNEL", ""),
            approvals_channel=os.environ.get("DISCORD_APPROVALS_CHANNEL", ""),
            registry_url=os.environ.get("MCP_REGISTRY_URL", "http://localhost:8000"),
            temporal_host=os.environ.get(
                "TEMPORAL_HOST", "temporal-frontend.temporal.svc.cluster.local:7233"
            ),
            temporal_namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"),
            redis_url=os.environ.get("REDIS_URL", "redis://redis.ai-agents.svc:6379"),
            critic_enabled=os.environ.get("LEARNING_CRITIC_ENABLED", "true").lower() == "true",
            reflection_enabled=os.environ.get("LEARNING_REFLECTION_ENABLED", "true").lower()
            == "true",
            auto_synthesis_enabled=os.environ.get("LEARNING_SYNTHESIZER_ENABLED", "true").lower()
            == "true",
            discord_approvals_enabled=os.environ.get(
                "LEARNING_REQUIRE_DISCORD_APPROVAL", "true"
            ).lower()
            == "true",
            passive_monitoring_enabled=os.environ.get(
                "LEARNING_PASSIVE_MONITORING_ENABLED", "true"
            ).lower()
            == "true",
            workflow_poll_interval_seconds=int(
                os.environ.get("LEARNING_WORKFLOW_POLL_INTERVAL", "60")
            ),
            discord_poll_interval_seconds=int(
                os.environ.get("LEARNING_DISCORD_POLL_INTERVAL", "300")
            ),
            event_subscription_enabled=os.environ.get(
                "LEARNING_EVENT_SUBSCRIPTION_ENABLED", "true"
            ).lower()
            == "true",
        )

        _learning_manager = LearningManager(config)
        await _learning_manager.start()
        logger.info("Learning Agent ready")
        yield

    except ImportError as e:
        logger.warning(
            "Core agents learning module not available, running in stub mode",
            error=str(e),
        )
        yield

    finally:
        logger.info("Shutting down Learning Agent...")
        if _learning_manager:
            await _learning_manager.stop()


# Create FastAPI app
app = FastAPI(
    title="Learning Agent",
    description="Voyager-style continuous learning system for Kubani",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(UTC).isoformat(),
    )


@app.get("/ready", response_model=ReadyResponse)
async def ready():
    """Readiness check endpoint."""
    return ReadyResponse(
        status="ready" if _learning_manager else "initializing",
        learning_enabled=os.environ.get("LEARNING_ENABLED", "true").lower() == "true",
        critic_enabled=os.environ.get("LEARNING_CRITIC_ENABLED", "true").lower() == "true",
        reflection_enabled=os.environ.get("LEARNING_REFLECTION_ENABLED", "true").lower() == "true",
        synthesizer_enabled=os.environ.get("LEARNING_SYNTHESIZER_ENABLED", "true").lower()
        == "true",
        passive_monitoring_enabled=os.environ.get(
            "LEARNING_PASSIVE_MONITORING_ENABLED", "true"
        ).lower()
        == "true",
    )


@app.post("/trigger-cycle")
async def trigger_cycle(hours: int | None = None):
    """Manually trigger a learning cycle."""
    if not _learning_manager:
        return {"status": "error", "message": "Learning manager not initialized"}

    try:
        result = await _learning_manager.run_learning_cycle(hours=hours)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Admin endpoints for managing rejected skills
@app.get("/admin/rejected-skills")
async def list_rejected_skills():
    """List all rejected skills."""
    if not _learning_manager or not _learning_manager.synthesizer:
        return {"status": "error", "message": "Synthesizer not initialized"}

    try:
        skills = await _learning_manager.synthesizer.list_rejected_skills()
        return {"status": "success", "rejected_skills": skills, "count": len(skills)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.delete("/admin/rejected-skills/{skill_name}")
async def clear_rejected_skill(skill_name: str):
    """Clear a rejected skill from Redis to allow re-synthesis."""
    if not _learning_manager or not _learning_manager.synthesizer:
        return {"status": "error", "message": "Synthesizer not initialized"}

    try:
        success = await _learning_manager.synthesizer.clear_rejected_skill(skill_name)
        if success:
            return {"status": "success", "message": f"Cleared rejected skill: {skill_name}"}
        return {"status": "not_found", "message": f"Skill not found: {skill_name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.delete("/admin/rejected-patterns/{pattern_hash}")
async def clear_rejected_pattern(pattern_hash: str):
    """Clear a rejected pattern from Redis to allow re-synthesis."""
    if not _learning_manager or not _learning_manager.synthesizer:
        return {"status": "error", "message": "Synthesizer not initialized"}

    try:
        success = await _learning_manager.synthesizer.clear_rejected_pattern(pattern_hash)
        if success:
            return {"status": "success", "message": f"Cleared rejected pattern: {pattern_hash}"}
        return {"status": "not_found", "message": f"Pattern not found: {pattern_hash}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def main():
    """Entry point for the learning agent."""
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    logging.basicConfig(level=logging.INFO)

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
