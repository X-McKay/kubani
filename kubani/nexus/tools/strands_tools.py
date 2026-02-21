"""Strands @tool wrappers for the Nexus core tools.

Creates Strands-compatible tool functions that close over a workspace path.
These are used by the Strands Agent in the agentic loop activity.

Usage:
    from kubani.nexus.tools.strands_tools import create_tools

    tools = create_tools(workspace_path)
    agent = Agent(model=model, tools=tools, system_prompt=prompt)
    result = await agent.invoke_async(user_message)
"""

from __future__ import annotations

import logging
from pathlib import Path

from strands import tool

logger = logging.getLogger(__name__)


def create_tools(workspace: Path, include_extras: bool = True) -> list:
    """Create Strands tool instances bound to a specific workspace.

    Each tool wraps the async core tool functions from core.py,
    running them via asyncio within the Strands tool executor.

    Args:
        workspace: The user's workspace directory.
        include_extras: If True, include extra tools (web_search, etc.).

    Returns:
        List of Strands tool instances for use with Agent().
    """
    from kubani.nexus.tools import core

    @tool
    async def read_file(path: str) -> str:
        """Read a file from the workspace. Returns content with line numbers.

        Args:
            path: Relative path within the workspace.
        """
        result = await core.read_file(workspace, path)
        if result.success:
            return result.output
        return f"Error: {result.error}"

    @tool
    async def write_file(path: str, content: str) -> str:
        """Create or overwrite a file in the workspace.

        Args:
            path: Relative path within the workspace.
            content: File content to write.
        """
        result = await core.write_file(workspace, path, content)
        if result.success:
            return result.output
        return f"Error: {result.error}"

    @tool
    async def edit_file(path: str, old_text: str, new_text: str) -> str:
        """Search-and-replace within a file. old_text must appear exactly once.

        Args:
            path: Relative path within the workspace.
            old_text: Text to find (must be unique in the file).
            new_text: Replacement text.
        """
        result = await core.edit_file(workspace, path, old_text, new_text)
        if result.success:
            return result.output
        return f"Error: {result.error}"

    @tool
    async def bash(command: str, timeout: int = 30) -> str:
        """Run a shell command in the workspace.

        Some commands may be blocked for security reasons.
        Medium-risk commands will return an error indicating they need approval.

        Args:
            command: Shell command to execute.
            timeout: Maximum execution time in seconds.
        """
        result = await core.bash(workspace, command, timeout)
        if result.success:
            return result.output
        # Pass through NEEDS_APPROVAL and block errors as-is
        return f"Error: {result.error}"

    @tool
    async def register_skill(name: str, file_path: str, description: str) -> str:
        """Register a Python skill from the workspace for reuse.

        Reads the file, runs safety analysis, and registers it.
        Low-risk skills are auto-approved.

        Args:
            name: Skill name (e.g., "web/fetch-url").
            file_path: Relative path to the Python file in the workspace.
            description: Human-readable description of the skill.
        """
        result = await core.register_skill(workspace, name, file_path, description)
        if result.success:
            return result.output
        return f"Error: {result.error}"

    tools = [read_file, write_file, edit_file, bash, register_skill]

    if include_extras:
        try:
            from kubani.nexus.tools.extra_tools import create_extra_tools

            extras = create_extra_tools()
            tools.extend(extras)
            logger.info(f"Loaded {len(extras)} extra tools")
        except Exception as e:
            logger.warning(f"Failed to load extra tools: {e}")

    return tools
