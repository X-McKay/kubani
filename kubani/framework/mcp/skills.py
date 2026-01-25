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
    client = get_mcp_client()

    # Get skills from MCP server
    response = await client.skills.list_skills(domain=domain, category=category)

    if not response.success:
        logger.error(f"Failed to list skills: {response.error}")
        return []

    # Parse skill data
    skills_data = response.data if isinstance(response.data, list) else []
    skills = [SkillInfo.from_dict(s) for s in skills_data]

    # Apply filters
    return filter_skills(skills, allowed=allowed, denied=denied)


async def get_skill_as_tool(skill: SkillInfo) -> dict[str, Any]:
    """
    Convert a skill to an MCP tool definition.

    This allows skills to be exposed as tools to the LLM agent.

    Args:
        skill: The skill to convert

    Returns:
        Tool definition dict compatible with MCP/Strands
    """
    return {
        "name": f"skill:{skill.path}",
        "description": skill.description,
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "object",
                    "description": "Context for skill execution",
                },
            },
            "required": ["context"],
        },
    }


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
    return [await get_skill_as_tool(s) for s in skills]


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
