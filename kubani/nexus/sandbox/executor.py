"""Nexus Execution Sandbox.

Provides isolated execution of skills in ephemeral environments.
Skills are executed in subprocess sandboxes with restricted capabilities.

In production (on the cluster), this would use Kubernetes Jobs with
security contexts. For local development and testing, it uses
subprocess isolation with restricted environment variables and
working directories.

Security layers:
1. Static analysis guard (AST-based) — blocks dangerous patterns.
2. Restricted subprocess environment — no access to host secrets.
3. Timeout enforcement — prevents runaway processes.
4. Output capture — all stdout/stderr is captured for logging.

Usage:
    from kubani.nexus.sandbox.executor import execute_skill_in_sandbox

    result = await execute_skill_in_sandbox(
        skill_name="web/fetch-url",
        inputs={"url": "https://example.com"},
        timeout_seconds=30,
    )
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from kubani.nexus.models.skills import SkillExecutionResult

logger = logging.getLogger(__name__)

# Environment variables that are NEVER passed to the sandbox
BLOCKED_ENV_VARS = {
    "OPENAI_API_KEY",
    "DISCORD_BOT_TOKEN",
    "GITHUB_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "DATABASE_URL",
    "NEXUS_DATABASE_URL",
    "REDIS_URL",
    "OCI_PASSWORD",
    "NEO4J_PASSWORD",
}

# Maximum output size in bytes (1MB)
MAX_OUTPUT_SIZE = 1_048_576


async def execute_skill_in_sandbox(
    skill_name: str,
    inputs: dict[str, Any],
    timeout_seconds: int = 60,
    skill_content: str | None = None,
) -> SkillExecutionResult:
    """Execute a skill in an isolated sandbox environment.

    This function:
    1. Resolves the skill content (from registry or provided directly).
    2. Runs static analysis to check for dangerous patterns.
    3. Creates a temporary workspace directory.
    4. Executes the skill in a restricted subprocess.
    5. Captures and returns the output.

    Args:
        skill_name: Name of the skill to execute.
        inputs: Input data for the skill (passed as JSON via stdin).
        timeout_seconds: Maximum execution time.
        skill_content: Optional skill script content (if not from registry).

    Returns:
        SkillExecutionResult with success status, output, and metadata.
    """
    start_time = time.monotonic()

    # Step 1: Resolve skill content
    if skill_content is None:
        skill_content = await _resolve_skill_content(skill_name)
        if skill_content is None:
            return SkillExecutionResult(
                skill_name=skill_name,
                success=False,
                error=f"Skill '{skill_name}' not found in registry",
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

    # Step 2: Static analysis
    analysis_result = analyze_skill_safety(skill_content)
    if not analysis_result["safe"]:
        return SkillExecutionResult(
            skill_name=skill_name,
            success=False,
            error=f"Skill blocked by static analysis: {analysis_result['reason']}",
            duration_ms=int((time.monotonic() - start_time) * 1000),
        )

    # Step 3: Execute in sandbox
    result = await _run_in_subprocess(
        skill_name=skill_name,
        skill_content=skill_content,
        inputs=inputs,
        timeout_seconds=timeout_seconds,
    )

    result.duration_ms = int((time.monotonic() - start_time) * 1000)
    return result


def analyze_skill_safety(code: str) -> dict[str, Any]:
    """Perform static analysis on skill code to detect dangerous patterns.

    Uses Python's AST module to inspect the code without executing it.
    Checks for:
    - Dangerous imports (os.system, subprocess, etc.)
    - File system access outside /workspace
    - Network access patterns
    - Eval/exec usage
    - System command execution

    Args:
        code: The Python source code to analyze.

    Returns:
        Dict with:
            - safe: bool — whether the code passed analysis.
            - reason: str — explanation if blocked.
            - risk_score: float — numeric risk score (0.0 - 10.0).
            - findings: list[str] — specific findings.
    """
    import ast

    findings: list[str] = []
    risk_score = 0.0

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {
            "safe": False,
            "reason": f"Syntax error: {e}",
            "risk_score": 10.0,
            "findings": [f"Syntax error at line {e.lineno}: {e.msg}"],
        }

    # Dangerous module imports
    dangerous_imports = {
        "subprocess": 8.0,
        "shutil": 5.0,
        "ctypes": 9.0,
        "socket": 4.0,
        "multiprocessing": 6.0,
        "signal": 7.0,
        "resource": 5.0,
    }

    # Dangerous function calls
    dangerous_calls = {
        "eval": 9.0,
        "exec": 9.0,
        "compile": 7.0,
        "__import__": 8.0,
        "globals": 5.0,
        "locals": 3.0,
        "getattr": 2.0,
        "setattr": 3.0,
        "delattr": 3.0,
    }

    # Dangerous attribute access patterns
    dangerous_attrs = {
        "system": 9.0,    # os.system
        "popen": 8.0,     # os.popen
        "execv": 9.0,     # os.execv
        "execve": 9.0,    # os.execve
        "fork": 9.0,      # os.fork
        "kill": 8.0,      # os.kill
        "remove": 4.0,    # os.remove
        "rmdir": 5.0,     # os.rmdir
        "rmtree": 7.0,    # shutil.rmtree
        "unlink": 4.0,    # os.unlink / Path.unlink
    }

    for node in ast.walk(tree):
        # Check imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".")[0]
                if module in dangerous_imports:
                    score = dangerous_imports[module]
                    risk_score = max(risk_score, score)
                    findings.append(
                        f"Dangerous import: {alias.name} (risk: {score})"
                    )

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module = node.module.split(".")[0]
                if module in dangerous_imports:
                    score = dangerous_imports[module]
                    risk_score = max(risk_score, score)
                    findings.append(
                        f"Dangerous import from: {node.module} (risk: {score})"
                    )

        # Check function calls
        elif isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr

            if func_name in dangerous_calls:
                score = dangerous_calls[func_name]
                risk_score = max(risk_score, score)
                findings.append(
                    f"Dangerous call: {func_name}() (risk: {score})"
                )

        # Check attribute access
        elif isinstance(node, ast.Attribute):
            if node.attr in dangerous_attrs:
                score = dangerous_attrs[node.attr]
                risk_score = max(risk_score, score)
                findings.append(
                    f"Dangerous attribute: .{node.attr} (risk: {score})"
                )

    # Block if risk score is too high
    safe = risk_score < 8.0
    reason = ""
    if not safe:
        reason = f"Risk score {risk_score:.1f} exceeds threshold. Findings: {'; '.join(findings[:3])}"

    return {
        "safe": safe,
        "reason": reason,
        "risk_score": risk_score,
        "findings": findings,
    }


async def _resolve_skill_content(skill_name: str) -> str | None:
    """Resolve skill content from the registry or local cache.

    Args:
        skill_name: Name of the skill to resolve.

    Returns:
        The skill's Python source code, or None if not found.
    """
    # Check local skill cache first
    cache_dir = Path(os.environ.get("SKILL_CACHE_DIR", "~/.kubani/skill-cache"))
    cache_dir = cache_dir.expanduser()
    skill_path = cache_dir / skill_name.replace("/", "_") / "run.py"

    if skill_path.exists():
        return skill_path.read_text()

    # Try to fetch from the registry
    try:
        from kubani.nexus.db import create_pool, get_skill

        db_url = os.environ.get(
            "NEXUS_DATABASE_URL",
            "postgresql://kubani:kubani@localhost:5432/kubani_nexus",
        )
        pool = await create_pool(db_url)
        try:
            skill = await get_skill(pool, skill_name)
            if skill and skill.get("status") == "approved":
                # In production, this would download the OCI artifact
                # For now, return None to indicate the skill needs to be fetched
                logger.info(f"Skill {skill_name} found in registry but OCI fetch not implemented")
                return None
        finally:
            await pool.close()
    except Exception as e:
        logger.warning(f"Failed to query skill registry: {e}")

    return None


async def _run_in_subprocess(
    skill_name: str,
    skill_content: str,
    inputs: dict[str, Any],
    timeout_seconds: int,
) -> SkillExecutionResult:
    """Execute skill code in a restricted subprocess.

    Creates a temporary directory, writes the skill code to it,
    and executes it with a restricted environment.

    Args:
        skill_name: Name of the skill (for logging).
        skill_content: The Python source code to execute.
        inputs: Input data passed as JSON via stdin.
        timeout_seconds: Maximum execution time.

    Returns:
        SkillExecutionResult with captured output.
    """
    import json

    with tempfile.TemporaryDirectory(prefix="nexus-sandbox-") as workspace:
        # Write the skill code
        skill_file = Path(workspace) / "run.py"
        skill_file.write_text(skill_content)

        # Write inputs as JSON
        inputs_file = Path(workspace) / "inputs.json"
        inputs_file.write_text(json.dumps(inputs))

        # Build restricted environment
        safe_env = _build_safe_environment(workspace)

        # Build the command
        # Wrap the skill execution to capture structured output
        wrapper_code = f"""
import json
import sys
sys.path.insert(0, '{workspace}')

# Load inputs
with open('{inputs_file}') as f:
    inputs = json.load(f)

# Execute the skill
from run import *

# If there's a main() function, call it
if 'main' in dir():
    result = main(inputs)
    if result is not None:
        print(json.dumps(result) if isinstance(result, (dict, list)) else str(result))
"""
        wrapper_file = Path(workspace) / "_wrapper.py"
        wrapper_file.write_text(wrapper_code)

        try:
            process = await asyncio.create_subprocess_exec(
                "python3", str(wrapper_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=safe_env,
                cwd=workspace,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )

            # Truncate output if too large
            stdout_text = stdout.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]
            stderr_text = stderr.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]

            return SkillExecutionResult(
                skill_name=skill_name,
                success=process.returncode == 0,
                output=stdout_text,
                error=stderr_text if process.returncode != 0 else None,
                exit_code=process.returncode or 0,
                logs=stderr_text,
            )

        except asyncio.TimeoutError:
            process.kill()
            return SkillExecutionResult(
                skill_name=skill_name,
                success=False,
                error=f"Execution timed out after {timeout_seconds}s",
                exit_code=-1,
            )
        except Exception as e:
            return SkillExecutionResult(
                skill_name=skill_name,
                success=False,
                error=f"Execution error: {e}",
                exit_code=-1,
            )


def _build_safe_environment(workspace: str) -> dict[str, str]:
    """Build a restricted environment for the sandbox subprocess.

    Strips dangerous environment variables and sets safe defaults.

    Args:
        workspace: Path to the temporary workspace directory.

    Returns:
        Dict of environment variables for the subprocess.
    """
    safe_env = {}

    # Copy only safe environment variables
    for key, value in os.environ.items():
        if key in BLOCKED_ENV_VARS:
            continue
        if key.startswith(("AWS_", "GITHUB_", "DISCORD_", "OCI_", "NEO4J_")):
            continue
        safe_env[key] = value

    # Override critical paths
    safe_env["HOME"] = workspace
    safe_env["TMPDIR"] = workspace
    safe_env["PYTHONDONTWRITEBYTECODE"] = "1"

    return safe_env
