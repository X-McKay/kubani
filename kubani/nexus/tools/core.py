"""Nexus core tools — the Pi agent primitives.

Four core tools (Read, Write, Edit, Bash) plus a self-extension tool
(register_skill). All tools operate within a sandboxed workspace directory
scoped to a user.

Security layers:
1. Path validation: all file operations restricted to workspace root.
2. Size limits: 1MB max file, 100MB max workspace.
3. Bash security barrier: 3-tier (allow/approve/block) analysis.
4. Restricted subprocess environment for bash execution.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from kubani.nexus.models.tools import ToolResult

logger = logging.getLogger(__name__)

# Limits
MAX_FILE_SIZE = 1_048_576  # 1MB
MAX_WORKSPACE_SIZE = 104_857_600  # 100MB
MAX_OUTPUT_SIZE = 1_048_576  # 1MB
MAX_READ_LINES = 5000

# Workspace root
WORKSPACE_ROOT = Path(
    os.environ.get("NEXUS_WORKSPACE_ROOT", os.path.expanduser("~/.kubani/workspaces"))
)


def get_workspace(user_id: str) -> Path:
    """Get or create the workspace directory for a user."""
    workspace = WORKSPACE_ROOT / user_id
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _validate_path(workspace: Path, path: str) -> Path:
    """Resolve and validate a path is within the workspace.

    Raises:
        ValueError: If path escapes the workspace.
    """
    resolved = (workspace / path).resolve()
    if not str(resolved).startswith(str(workspace.resolve())):
        raise ValueError(f"Path '{path}' escapes workspace boundary")
    return resolved


def _check_workspace_size(workspace: Path) -> int:
    """Get total workspace size in bytes."""
    total = 0
    for f in workspace.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


# =========================================================================
# Read Tool
# =========================================================================


async def read_file(workspace: Path, path: str) -> ToolResult:
    """Read a file from the workspace with line numbers.

    Args:
        workspace: The user's workspace directory.
        path: Relative path within the workspace.

    Returns:
        ToolResult with file contents (line-numbered) or error.
    """
    start = time.monotonic()
    try:
        resolved = _validate_path(workspace, path)

        if not resolved.exists():
            return ToolResult(
                tool_name="read_file",
                success=False,
                error=f"File not found: {path}",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        if not resolved.is_file():
            return ToolResult(
                tool_name="read_file",
                success=False,
                error=f"Not a file: {path}",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        if resolved.stat().st_size > MAX_FILE_SIZE:
            return ToolResult(
                tool_name="read_file",
                success=False,
                error=f"File too large ({resolved.stat().st_size} bytes, max {MAX_FILE_SIZE})",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        content = resolved.read_text(errors="replace")
        lines = content.splitlines()

        if len(lines) > MAX_READ_LINES:
            lines = lines[:MAX_READ_LINES]
            numbered = "\n".join(f"{i+1:>6}\t{line}" for i, line in enumerate(lines))
            numbered += f"\n... (truncated, showing first {MAX_READ_LINES} of {len(content.splitlines())} lines)"
        else:
            numbered = "\n".join(f"{i+1:>6}\t{line}" for i, line in enumerate(lines))

        return ToolResult(
            tool_name="read_file",
            success=True,
            output=numbered,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except ValueError as e:
        return ToolResult(
            tool_name="read_file",
            success=False,
            error=str(e),
            duration_ms=int((time.monotonic() - start) * 1000),
        )


# =========================================================================
# Write Tool
# =========================================================================


async def write_file(workspace: Path, path: str, content: str) -> ToolResult:
    """Write or create a file in the workspace.

    Args:
        workspace: The user's workspace directory.
        path: Relative path within the workspace.
        content: File content to write.

    Returns:
        ToolResult with confirmation or error.
    """
    start = time.monotonic()
    try:
        resolved = _validate_path(workspace, path)

        if len(content.encode()) > MAX_FILE_SIZE:
            return ToolResult(
                tool_name="write_file",
                success=False,
                error=f"Content too large ({len(content.encode())} bytes, max {MAX_FILE_SIZE})",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        # Check workspace size limit
        current_size = _check_workspace_size(workspace)
        if current_size + len(content.encode()) > MAX_WORKSPACE_SIZE:
            return ToolResult(
                tool_name="write_file",
                success=False,
                error=f"Workspace size limit exceeded ({current_size} bytes, max {MAX_WORKSPACE_SIZE})",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)

        return ToolResult(
            tool_name="write_file",
            success=True,
            output=f"Wrote {len(content.encode())} bytes to {path}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except ValueError as e:
        return ToolResult(
            tool_name="write_file",
            success=False,
            error=str(e),
            duration_ms=int((time.monotonic() - start) * 1000),
        )


# =========================================================================
# Edit Tool
# =========================================================================


async def edit_file(
    workspace: Path, path: str, old_text: str, new_text: str
) -> ToolResult:
    """Search-and-replace within a file.

    The old_text must appear exactly once in the file.

    Args:
        workspace: The user's workspace directory.
        path: Relative path within the workspace.
        old_text: Text to find (must be unique).
        new_text: Replacement text.

    Returns:
        ToolResult with confirmation or error.
    """
    start = time.monotonic()
    try:
        resolved = _validate_path(workspace, path)

        if not resolved.exists():
            return ToolResult(
                tool_name="edit_file",
                success=False,
                error=f"File not found: {path}",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        content = resolved.read_text(errors="replace")
        count = content.count(old_text)

        if count == 0:
            return ToolResult(
                tool_name="edit_file",
                success=False,
                error="old_text not found in file",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        if count > 1:
            return ToolResult(
                tool_name="edit_file",
                success=False,
                error=f"old_text found {count} times (must be unique). Provide more surrounding context.",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        new_content = content.replace(old_text, new_text, 1)
        resolved.write_text(new_content)

        return ToolResult(
            tool_name="edit_file",
            success=True,
            output=f"Edited {path}: replaced 1 occurrence",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except ValueError as e:
        return ToolResult(
            tool_name="edit_file",
            success=False,
            error=str(e),
            duration_ms=int((time.monotonic() - start) * 1000),
        )


# =========================================================================
# Bash Tool
# =========================================================================


async def bash(
    workspace: Path,
    command: str,
    timeout: int = 30,
) -> ToolResult:
    """Execute a shell command in a restricted subprocess.

    The command goes through the 3-tier security barrier first:
    - Low risk: auto-execute
    - Medium risk: returns REQUEST_APPROVAL action (handled by caller)
    - High risk: hard-blocked

    Args:
        workspace: The user's workspace directory.
        command: Shell command to execute.
        timeout: Maximum execution time in seconds.

    Returns:
        ToolResult with stdout/stderr or error.
        If the command needs approval, returns with
        error="NEEDS_APPROVAL: {reason}" and success=False.
    """
    from kubani.nexus.tools.security import analyze_bash_command

    start = time.monotonic()

    # Security barrier
    analysis = analyze_bash_command(command)

    if analysis["action"] == "block":
        return ToolResult(
            tool_name="bash",
            success=False,
            error=f"Command blocked: {analysis['reason']}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    if analysis["action"] == "approve":
        return ToolResult(
            tool_name="bash",
            success=False,
            error=f"NEEDS_APPROVAL: {analysis['reason']}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    # Build restricted environment
    from kubani.nexus.sandbox.executor import _build_safe_environment

    safe_env = _build_safe_environment(str(workspace))

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=safe_env,
            cwd=str(workspace),
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )

        stdout_text = stdout.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]
        stderr_text = stderr.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]

        output = stdout_text
        if stderr_text:
            output += f"\n[stderr]\n{stderr_text}"

        return ToolResult(
            tool_name="bash",
            success=process.returncode == 0,
            output=output,
            error=stderr_text if process.returncode != 0 else None,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    except asyncio.TimeoutError:
        process.kill()
        return ToolResult(
            tool_name="bash",
            success=False,
            error=f"Command timed out after {timeout}s",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as e:
        return ToolResult(
            tool_name="bash",
            success=False,
            error=f"Execution error: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


# =========================================================================
# Register Skill Tool
# =========================================================================


async def register_skill(
    workspace: Path,
    name: str,
    file_path: str,
    description: str,
) -> ToolResult:
    """Register a Python skill from the workspace with the Skill Registry.

    Reads the file, runs safety analysis, and registers it. Low-risk
    skills are auto-approved and immediately available. Medium/high-risk
    skills require HITL approval.

    Args:
        workspace: The user's workspace directory.
        name: Skill name (e.g., "web/fetch-url").
        file_path: Relative path to the Python file in the workspace.
        description: Human-readable description of the skill.

    Returns:
        ToolResult with approval status.
    """
    start = time.monotonic()
    try:
        resolved = _validate_path(workspace, file_path)

        if not resolved.exists():
            return ToolResult(
                tool_name="register_skill",
                success=False,
                error=f"File not found: {file_path}",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        source_code = resolved.read_text()

        # Safety analysis
        from kubani.nexus.sandbox.executor import analyze_skill_safety

        safety = analyze_skill_safety(source_code)

        if not safety["safe"]:
            return ToolResult(
                tool_name="register_skill",
                success=False,
                error=f"Skill blocked by safety analysis: {safety['reason']}",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        # Register with the skill registry
        from kubani.nexus.db import create_pool
        from kubani.nexus.skills.registry import SkillRegistry

        db_url = os.environ.get(
            "NEXUS_DATABASE_URL",
            "postgresql://kubani:kubani@localhost:5432/kubani_nexus",
        )
        pool = await create_pool(db_url)
        try:
            registry = SkillRegistry(pool)
            skill_id = await registry.register(
                name=name,
                version="0.1.0",
                description=description,
                source_code=source_code,
                author="nexus-agent",
            )

            skill = await registry.get(name)
            status = skill.get("status", "unknown") if skill else "unknown"

            return ToolResult(
                tool_name="register_skill",
                success=True,
                output=f"Skill '{name}' registered (id={skill_id}, status={status})",
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        finally:
            await pool.close()

    except ValueError as e:
        return ToolResult(
            tool_name="register_skill",
            success=False,
            error=str(e),
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as e:
        logger.error(f"Skill registration failed: {e}")
        return ToolResult(
            tool_name="register_skill",
            success=False,
            error=f"Registration error: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


# =========================================================================
# Tool Dispatcher
# =========================================================================

# Core tool descriptions for the LLM system prompt
CORE_TOOLS_DESCRIPTION = """Available tools:
- read_file(path): Read a file from the workspace. Returns content with line numbers.
- write_file(path, content): Create or overwrite a file in the workspace.
- edit_file(path, old_text, new_text): Replace text in a file. old_text must be unique.
- bash(command, timeout=30): Run a shell command. Some commands may need approval.
- register_skill(name, file_path, description): Register a Python skill for reuse."""


CORE_TOOL_NAMES = {"read_file", "write_file", "edit_file", "bash", "register_skill"}


async def dispatch_tool(
    workspace: Path,
    tool_name: str,
    arguments: dict[str, Any],
) -> ToolResult:
    """Dispatch a tool call to the appropriate handler.

    Args:
        workspace: The user's workspace directory.
        tool_name: Name of the tool to call.
        arguments: Tool arguments.

    Returns:
        ToolResult from the tool execution.
    """
    if tool_name == "read_file":
        return await read_file(workspace, arguments.get("path", ""))
    elif tool_name == "write_file":
        return await write_file(
            workspace, arguments.get("path", ""), arguments.get("content", "")
        )
    elif tool_name == "edit_file":
        return await edit_file(
            workspace,
            arguments.get("path", ""),
            arguments.get("old_text", ""),
            arguments.get("new_text", ""),
        )
    elif tool_name == "bash":
        return await bash(
            workspace,
            arguments.get("command", ""),
            arguments.get("timeout", 30),
        )
    elif tool_name == "register_skill":
        return await register_skill(
            workspace,
            arguments.get("name", ""),
            arguments.get("file_path", ""),
            arguments.get("description", ""),
        )
    else:
        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=f"Unknown tool: {tool_name}",
        )
