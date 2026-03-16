"""
Skills MCP Server implementation.

Provides MCP tools for skill execution (execution-only mode).
"""

import asyncio
import contextlib
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from kubani.framework.mcp.server.health import HealthCheckManager
from kubani.framework.mcp.server.metrics import MetricsCollector
from kubani.framework.mcp.server.registry import RegistryClient
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from skills_mcp.executor import get_executor_manager
from skills_mcp.models import (
    ExecutionStatus,
    SkillExecuteResult,
)

logger = logging.getLogger(__name__)

# Default skills path relative to kubani root
DEFAULT_SKILLS_PATH = "kubani/skills"

# Global framework components
_health_manager: HealthCheckManager | None = None
_metrics_collector: MetricsCollector | None = None
_registry_client: RegistryClient | None = None
_heartbeat_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(server: FastMCP):
    """MCP server lifespan - initialize executor (execution-only mode)."""
    global _health_manager, _metrics_collector, _registry_client, _heartbeat_task

    logger.info("Starting Skills MCP Server in execution-only mode")

    # Initialize executor manager
    microsandbox_enabled = os.environ.get("MICROSANDBOX_ENABLED", "true").lower() == "true"
    microsandbox_url = os.environ.get("MICROSANDBOX_URL")
    get_executor_manager(
        microsandbox_enabled=microsandbox_enabled,
        microsandbox_url=microsandbox_url,
    )

    # Initialize framework components
    _health_manager = HealthCheckManager(version="1.0.0")
    _metrics_collector = MetricsCollector(server_name="skills-mcp")

    # Register health checks
    async def check_executor():
        """Check if executor is available."""
        try:
            executor = get_executor_manager()
            return executor is not None
        except Exception:
            return False

    _health_manager.register("executor", check_executor, timeout=5.0)

    # Register with registry if URL provided
    registry_url = os.environ.get("REGISTRY_URL")
    if registry_url:
        _registry_client = RegistryClient(
            registry_url=registry_url,
            server_id="skills-mcp",
        )

        # Get connection config from environment
        external_url = os.environ.get("EXTERNAL_URL", "http://skills-mcp.almckay.io/sse")
        internal_url = os.environ.get(
            "INTERNAL_URL", "http://skills-mcp-server.ai-agents.svc:8080/sse"
        )

        capabilities = ["execute_skill", "get_execution_outcomes"]

        await _registry_client.register(
            name="Skills MCP Server",
            description="Kubani Skills MCP Server for skill execution",
            transport="sse",
            connection_config={
                "url": external_url,
                "internal_url": internal_url,
            },
            capabilities=capabilities,
        )

        # Start heartbeat task
        async def get_backend_status():
            health = await _health_manager.check_all()
            return {name: backend.status.value for name, backend in health.backends.items()}

        _heartbeat_task = asyncio.create_task(
            _registry_client.start_heartbeat(interval=30, get_backend_status=get_backend_status)
        )

    yield

    # Cleanup
    if _heartbeat_task:
        _heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _heartbeat_task

    if _registry_client:
        await _registry_client.unregister()

    logger.info("Skills MCP Server shutting down")


def create_server() -> FastMCP:
    """Create and configure the Skills MCP server."""
    # Get allowed hosts from environment or use defaults
    allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
    allowed_hosts = ["localhost:*", "127.0.0.1:*"]
    if allowed_hosts_env:
        allowed_hosts.extend(h.strip() for h in allowed_hosts_env.split(",") if h.strip())

    mcp = FastMCP(
        name="Skills MCP Server",
        instructions=(
            "Kubani Skills MCP Server (execution-only mode). Use execute_skill "
            "to run skill scripts in isolated Microsandbox environments. Use "
            "get_execution_outcomes to review recent execution results."
        ),
        lifespan=lifespan,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
        ),
    )

    # =========================================================================
    # Skill Execution Tools
    # =========================================================================

    @mcp.tool()
    async def execute_skill(
        skill_path: str,
        context: dict[str, Any],
        timeout: float | None = None,
        agent_id: str | None = None,
    ) -> SkillExecuteResult:
        """
        Execute a skill with the provided context.

        The skill script receives the context as a JSON-encoded SKILL_CONTEXT
        environment variable. Python scripts can access it via:
            import json, os
            context = json.loads(os.environ['SKILL_CONTEXT'])

        Args:
            skill_path: Path to the skill (e.g., "k8s/remediation/restart-crashloop")
            context: Context/parameters for the skill execution
            timeout: Execution timeout in seconds (default: 60)
            agent_id: ID of the agent executing the skill (for outcome tracking)

        Returns:
            Execution result with status, output, and timing
        """
        # Resolve skill directory from path
        skills_root = Path(os.environ.get("SKILLS_PATH", DEFAULT_SKILLS_PATH))
        # Handle both absolute and relative paths
        if not skills_root.is_absolute():
            # Walk up to find repo root (same strategy as catalog.find_skills_root)
            current = Path(__file__).resolve()
            for parent in current.parents:
                if (parent / "pyproject.toml").exists():
                    skills_root = parent / skills_root
                    break

        skill_dir = skills_root / skill_path
        if not skill_dir.exists():
            return SkillExecuteResult(
                skill_path=skill_path,
                status=ExecutionStatus.FAILED,
                error=f"Skill directory not found: {skill_path}",
            )

        # Check for executable scripts
        scripts_dir = skill_dir / "scripts"
        if not scripts_dir.exists() or not any(scripts_dir.iterdir()):
            # Read SKILL.md content for declarative skills
            skill_md = skill_dir / "SKILL.md"
            content = skill_md.read_text() if skill_md.exists() else ""
            return SkillExecuteResult(
                skill_path=skill_path,
                status=ExecutionStatus.SKIPPED,
                output=content,
                error="Skill has no executable scripts (declarative skill)",
            )

        # Build a minimal SkillInfo for the executor.
        # Note: SkillInfo.scripts is list[str] (filenames), not dict.
        from skills_mcp.models import SkillInfo

        script_names = [f.name for f in scripts_dir.iterdir() if f.is_file()]
        skill = SkillInfo(
            path=skill_path,
            name=skill_path.split("/")[-1],
            scripts=script_names,
            skill_dir=str(skill_dir),
        )

        # Execute the skill
        executor = get_executor_manager()
        result = await executor.execute(
            skill=skill,
            context=context,
            timeout=timeout,
            agent_id=agent_id,
        )

        return SkillExecuteResult(
            skill_path=result.skill_path,
            status=result.status,
            output=result.output,
            error=result.error,
            duration_ms=result.duration_ms,
            sandbox_used=result.sandbox_id is not None,
        )

    @mcp.tool()
    async def get_execution_outcomes(limit: int = 100) -> dict[str, Any]:
        """
        Get recent skill execution outcomes.

        Useful for monitoring and debugging skill executions.

        Args:
            limit: Maximum number of outcomes to return (default: 100)

        Returns:
            List of recent execution outcomes
        """
        executor = get_executor_manager()
        outcomes = executor.get_outcomes(limit=limit)

        return {
            "outcomes": [
                {
                    "skill_path": o.skill_path,
                    "agent_id": o.agent_id,
                    "status": o.status.value,
                    "success": o.success,
                    "duration_ms": o.duration_ms,
                    "error": o.error,
                    "executed_at": o.executed_at.isoformat(),
                }
                for o in outcomes
            ],
            "count": len(outcomes),
            "executor": executor.get_executor_name(),
        }

    # =========================================================================
    # Health Check
    # =========================================================================

    @mcp.tool()
    async def health() -> dict[str, Any]:
        """
        Check the health of the Skills MCP server.

        Returns:
            Health status including executor info and skill count
        """
        if _health_manager:
            health_response = await _health_manager.check_all()
            return health_response.to_dict()

        # Fallback if health manager not initialized
        try:
            executor = get_executor_manager()
            return {
                "status": "healthy",
                "executor": executor.get_executor_name(),
                "microsandbox_enabled": executor.microsandbox_enabled,
                "mode": "execution-only",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }

    @mcp.tool()
    async def metrics() -> dict[str, Any]:
        """
        Get Prometheus metrics for the Skills MCP server.

        Returns:
            Metrics in Prometheus format
        """
        if _metrics_collector:
            metrics_data = _metrics_collector.get_metrics()
            return {
                "content_type": "text/plain; version=0.0.4",
                "body": metrics_data.decode("utf-8"),
            }
        return {
            "error": "Metrics collector not initialized",
        }

    return mcp


def main():
    """Entry point for the Skills MCP server."""
    import argparse

    import anyio
    from kubani.framework.mcp.server.transport import TransportConfig, run_server_async

    # Parse skills-path separately since it's specific to this server
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--skills-path",
        help="Path to skills directory (default: from SKILLS_PATH env or kubani/skills)",
    )
    args, _ = parser.parse_known_args()

    # Set skills path if provided
    if args.skills_path:
        os.environ["SKILLS_PATH"] = args.skills_path

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    # Parse transport config from remaining args
    config = TransportConfig.from_args()

    # Create the server
    mcp = create_server()

    # Run with transport config
    anyio.run(run_server_async, mcp, config)


if __name__ == "__main__":
    main()
