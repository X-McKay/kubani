"""
Skills MCP Server implementation.

Provides MCP tools for skill discovery and execution.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from skills_mcp.discovery import get_discovery
from skills_mcp.executor import get_executor_manager
from skills_mcp.models import (
    ExecutionStatus,
    SkillDetailResult,
    SkillExecuteResult,
    SkillInfo,
    SkillListResult,
)

logger = logging.getLogger(__name__)

# Default skills path relative to kubani root
DEFAULT_SKILLS_PATH = "kubani/skills"


def _skill_to_dict(skill: SkillInfo) -> dict[str, Any]:
    """Convert SkillInfo to dict for MCP response."""
    return {
        "path": skill.path,
        "name": skill.name,
        "version": skill.version,
        "description": skill.description,
        "metadata": {
            "domain": skill.metadata.domain,
            "category": skill.metadata.category,
            "requires-approval": skill.metadata.requires_approval,
            "confidence": skill.metadata.confidence,
            "mcp-servers": skill.metadata.mcp_servers,
        },
        "scripts": skill.scripts,
        "has_tests": skill.has_tests,
    }


@asynccontextmanager
async def lifespan(server: FastMCP):
    """MCP server lifespan - initialize discovery and executor."""
    # Get skills path from environment
    skills_path = os.environ.get("SKILLS_PATH", DEFAULT_SKILLS_PATH)

    # If relative path, resolve from current directory or kubani root
    if not Path(skills_path).is_absolute():
        # Try to find kubani root by looking for pyproject.toml
        current = Path.cwd()
        while current != current.parent:
            if (current / "kubani" / "skills").exists():
                skills_path = str(current / "kubani" / "skills")
                break
            current = current.parent
        else:
            # Fall back to relative path from cwd
            skills_path = str(Path.cwd() / skills_path)

    logger.info(f"Skills path: {skills_path}")

    # Initialize discovery
    discovery = get_discovery(skills_path)
    skills = discovery.discover_all()
    logger.info(f"Discovered {len(skills)} skills")

    # Initialize executor manager
    microsandbox_enabled = os.environ.get("MICROSANDBOX_ENABLED", "true").lower() == "true"
    microsandbox_url = os.environ.get("MICROSANDBOX_URL")
    get_executor_manager(
        microsandbox_enabled=microsandbox_enabled,
        microsandbox_url=microsandbox_url,
    )

    yield

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
            "Kubani Skills MCP Server. Use these tools to discover, filter, and "
            "execute skills from the kubani/skills directory. Skills are executed "
            "in isolated Microsandbox environments for security."
        ),
        lifespan=lifespan,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
        ),
    )

    # =========================================================================
    # Skill Discovery Tools
    # =========================================================================

    @mcp.tool()
    async def list_skills(
        domain: str | None = None,
        category: str | None = None,
        allowed: list[str] | None = None,
        denied: list[str] | None = None,
    ) -> SkillListResult:
        """
        List available skills with optional filtering.

        Args:
            domain: Filter by domain (e.g., "k8s", "news", "general")
            category: Filter by category (e.g., "diagnostic", "remediation")
            allowed: Glob patterns for allowed skills (e.g., ["k8s/*", "general/notifications/*"])
            denied: Glob patterns for denied skills (e.g., ["k8s/remediation/*"])

        Returns:
            List of skills matching the filters
        """
        discovery = get_discovery()
        skills = discovery.filter_skills(
            domain=domain,
            category=category,
            allowed=allowed,
            denied=denied,
        )

        return SkillListResult(
            skills=skills,
            count=len(skills),
            domain=domain,
            category=category,
        )

    @mcp.tool()
    async def get_skill(skill_path: str) -> SkillDetailResult:
        """
        Get detailed information about a specific skill.

        Args:
            skill_path: Full path to the skill (e.g., "k8s/diagnostic/check-pod-health")

        Returns:
            Detailed skill information including content and scripts
        """
        discovery = get_discovery()
        skill = discovery.get_skill(skill_path)

        if skill is None:
            # Return empty result with found=False
            return SkillDetailResult(
                skill=SkillInfo(path=skill_path, name=skill_path.split("/")[-1]),
                found=False,
            )

        return SkillDetailResult(skill=skill, found=True)

    @mcp.tool()
    async def refresh_skills() -> dict[str, Any]:
        """
        Refresh the skills cache by re-scanning the filesystem.

        Use this after adding or modifying skills to pick up changes
        without restarting the server.

        Returns:
            Summary of discovered skills
        """
        discovery = get_discovery()
        skills = discovery.refresh()

        # Group by domain for summary
        by_domain: dict[str, int] = {}
        for skill in skills:
            domain = skill.metadata.domain or "unknown"
            by_domain[domain] = by_domain.get(domain, 0) + 1

        return {
            "total": len(skills),
            "by_domain": by_domain,
            "message": f"Refreshed skill cache, found {len(skills)} skills",
        }

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
        discovery = get_discovery()
        skill = discovery.get_skill(skill_path)

        if skill is None:
            return SkillExecuteResult(
                skill_path=skill_path,
                status=ExecutionStatus.FAILED,
                error=f"Skill not found: {skill_path}",
            )

        # Check if skill has executable scripts
        if not skill.scripts:
            return SkillExecuteResult(
                skill_path=skill_path,
                status=ExecutionStatus.SKIPPED,
                output=skill.content,  # Return skill content for declarative skills
                error="Skill has no executable scripts (declarative skill)",
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
        try:
            discovery = get_discovery()
            skills = discovery.discover_all()
            executor = get_executor_manager()

            return {
                "status": "healthy",
                "skills_count": len(skills),
                "executor": executor.get_executor_name(),
                "microsandbox_enabled": executor.microsandbox_enabled,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
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
