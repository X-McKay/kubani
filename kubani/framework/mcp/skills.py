"""
Skills MCP Client Integration.

Provides skill filtering and access control for agents. Each agent can specify
which skills it's allowed to use via glob patterns in its config.yaml.

Usage:
    from framework.mcp.skills import get_filtered_skills

    # Get skills filtered by agent's allowed/denied patterns
    skills = await get_filtered_skills(
        allowed=["k8s/diagnostic/*", "k8s/collection/*"],
        denied=["k8s/remediation/*"],
    )
"""

import fnmatch
import logging
from dataclasses import dataclass
from typing import Any

from kubani.framework.mcp.client import MCPResponse, get_mcp_client

logger = logging.getLogger(__name__)


@dataclass
class SkillInfo:
    """Information about a skill."""

    path: str  # e.g., "k8s/diagnostic/check-pod-health"
    name: str
    description: str
    version: str
    domain: str
    category: str
    requires_approval: bool = False
    confidence: float = 0.5
    mcp_servers: list[str] | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillInfo":
        """Create from dictionary."""
        metadata = data.get("metadata", {})
        return cls(
            path=data.get("path", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            domain=metadata.get("domain", ""),
            category=metadata.get("category", ""),
            requires_approval=metadata.get("requires-approval", False),
            confidence=metadata.get("confidence", 0.5),
            mcp_servers=metadata.get("mcp-servers"),
            metadata=metadata,
        )


def filter_skills(
    skills: list[SkillInfo],
    allowed: list[str] | None = None,
    denied: list[str] | None = None,
) -> list[SkillInfo]:
    """
    Filter skills based on allowed/denied patterns.

    Args:
        skills: List of skills to filter
        allowed: Glob patterns for allowed skills (None = allow all)
        denied: Glob patterns for denied skills (None = deny none)

    Returns:
        Filtered list of skills

    Example:
        # Allow only diagnostic and collection skills, deny remediation
        filtered = filter_skills(
            skills,
            allowed=["k8s/diagnostic/*", "k8s/collection/*"],
            denied=["k8s/remediation/*"],
        )
    """
    filtered = []

    for skill in skills:
        skill_path = skill.path

        # Check denied patterns first
        if denied:
            if any(fnmatch.fnmatch(skill_path, pattern) for pattern in denied):
                logger.debug(f"Skill {skill_path} denied by pattern")
                continue

        # Check allowed patterns
        if allowed:
            if not any(fnmatch.fnmatch(skill_path, pattern) for pattern in allowed):
                logger.debug(f"Skill {skill_path} not in allowed patterns")
                continue

        filtered.append(skill)

    return filtered


async def get_filtered_skills(
    allowed: list[str] | None = None,
    denied: list[str] | None = None,
    domain: str | None = None,
    category: str | None = None,
) -> list[SkillInfo]:
    """
    Get skills from the Skills MCP server, filtered by patterns.

    Args:
        allowed: Glob patterns for allowed skills
        denied: Glob patterns for denied skills
        domain: Filter by domain (e.g., "k8s")
        category: Filter by category (e.g., "diagnostic")

    Returns:
        List of filtered SkillInfo objects
    """
    from kubani.framework.config import get_config

    config = get_config()
    if not config.mcp.skills_enabled:
        return []

    client = get_mcp_client()

    # Get skills from MCP server
    response = await client.skills.list_skills(domain=domain, category=category)

    if not response.success:
        logger.warning(f"Failed to list skills: {response.error}")
        return []

    # Parse skill data — response may be a list or a dict with a "skills" key
    if isinstance(response.data, list):
        skills_data = response.data
    elif isinstance(response.data, dict):
        skills_data = response.data.get("skills", [])
    else:
        skills_data = []
    skills = [SkillInfo.from_dict(s) for s in skills_data]

    # Apply filters
    return filter_skills(skills, allowed=allowed, denied=denied)


def get_skill_as_tool(skill: SkillInfo) -> Any:
    """Convert a skill to a callable Strands tool.

    Creates a @tool-decorated function that executes the skill via the
    Skills MCP server when invoked by the agent.

    Args:
        skill: The skill to convert

    Returns:
        Callable tool function compatible with Strands Agent
    """
    import asyncio

    from strands import tool

    # Sanitize skill path to a valid Python identifier for the tool name
    tool_name = skill.path.replace("/", "_").replace("-", "_")

    @tool(name=tool_name, description=skill.description)
    def skill_tool(context: dict[str, Any] | None = None) -> str:
        """Execute a skill with the given context."""
        ctx = context or {}
        try:
            response = asyncio.get_event_loop().run_until_complete(execute_skill(skill.path, ctx))
            if response.success:
                return str(response.data)
            return f"Skill execution failed: {response.error}"
        except Exception as e:
            return f"Skill execution error: {e}"

    return skill_tool


async def get_skills_as_tools(
    allowed: list[str] | None = None,
    denied: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Get filtered skills as MCP tool definitions.

    Args:
        allowed: Glob patterns for allowed skills
        denied: Glob patterns for denied skills

    Returns:
        List of tool definitions
    """
    skills = await get_filtered_skills(allowed=allowed, denied=denied)
    return [get_skill_as_tool(s) for s in skills]


async def execute_skill(
    skill_path: str,
    context: dict[str, Any],
    timeout: float | None = None,
) -> MCPResponse:
    """
    Execute a skill via the Skills MCP server.

    Args:
        skill_path: Path to the skill (e.g., "k8s/diagnostic/check-pod-health")
        context: Context for skill execution
        timeout: Execution timeout in seconds

    Returns:
        MCPResponse with execution result
    """
    client = get_mcp_client()
    return await client.skills.execute_skill(
        skill_path=skill_path,
        context=context,
        timeout=timeout,
    )
