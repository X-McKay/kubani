"""
Skill execution module.

Provides sandboxed execution of skill scripts using Microsandbox (primary)
or subprocess (fallback).
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from skills_mcp.models import ExecutionOutcome, ExecutionResult, ExecutionStatus, SkillInfo

logger = logging.getLogger(__name__)

# Default timeout for skill execution (seconds)
DEFAULT_TIMEOUT = 60.0

# Maximum output size (characters)
MAX_OUTPUT_SIZE = 100_000


class SkillExecutor(ABC):
    """Abstract base class for skill executors."""

    @abstractmethod
    async def execute(
        self,
        skill: SkillInfo,
        context: dict[str, Any],
        timeout: float | None = None,
    ) -> ExecutionResult:
        """
        Execute a skill with the given context.

        Args:
            skill: The skill to execute
            context: Context/parameters for the skill
            timeout: Execution timeout in seconds

        Returns:
            ExecutionResult with status and output
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of this executor."""
        pass


class MicrosandboxExecutor(SkillExecutor):
    """
    Execute skills in Microsandbox microVM environments.

    Provides hardware-level isolation with fast startup times (<200ms).
    """

    def __init__(self, server_url: str | None = None, api_key: str | None = None):
        """
        Initialize Microsandbox executor.

        Args:
            server_url: Microsandbox server URL (default: from env or localhost:5555)
            api_key: API key for authentication (default: from env)
        """
        self.server_url = server_url or os.environ.get("MSB_SERVER_URL", "http://127.0.0.1:5555")
        self.api_key = api_key or os.environ.get("MSB_API_KEY")
        self._available: bool | None = None

    @property
    def name(self) -> str:
        return "microsandbox"

    async def is_available(self) -> bool:
        """Check if Microsandbox is available."""
        if self._available is not None:
            return self._available

        try:
            from microsandbox import PythonSandbox

            # Quick health check - try to import and check server
            async with PythonSandbox.create() as sandbox:
                execution = await sandbox.run("print('health')")
                output = await execution.output()
                self._available = "health" in output
        except Exception as e:
            logger.warning(f"Microsandbox not available: {e}")
            self._available = False

        return self._available

    async def execute(
        self,
        skill: SkillInfo,
        context: dict[str, Any],
        timeout: float | None = None,
    ) -> ExecutionResult:
        """Execute skill in Microsandbox."""
        from microsandbox import PythonSandbox

        timeout = timeout or DEFAULT_TIMEOUT
        start_time = time.monotonic()
        sandbox_id = None

        try:
            # Find the script to execute
            script_path = self._find_script(skill)
            if not script_path:
                return ExecutionResult(
                    skill_path=skill.path,
                    status=ExecutionStatus.FAILED,
                    error=f"No executable script found for skill {skill.path}",
                    context=context,
                )

            async with PythonSandbox.create() as sandbox:
                sandbox_id = getattr(sandbox, "id", None)

                # Prepare the execution environment
                # Pass context as JSON environment variable
                context_json = json.dumps(context)

                # Execute the script
                if script_path.suffix == ".py":
                    # For Python scripts, run them with context
                    script_content = script_path.read_text()

                    # Inject context into the script environment
                    setup_code = f"""
import json
import os
os.environ['SKILL_CONTEXT'] = '''{context_json}'''
CONTEXT = json.loads(os.environ['SKILL_CONTEXT'])
"""
                    full_code = setup_code + "\n" + script_content

                    execution = await sandbox.run(full_code)
                else:
                    # For shell scripts, run via command
                    execution = await sandbox.command.run(
                        str(script_path),
                        [],
                        timeout=int(timeout),
                    )

                output = await execution.output()
                error_output = await execution.error() if hasattr(execution, "error") else ""
                exit_code = getattr(execution, "exit_code", 0)
                success = getattr(execution, "success", exit_code == 0)

                # Truncate output if too large
                if len(output) > MAX_OUTPUT_SIZE:
                    output = output[:MAX_OUTPUT_SIZE] + "\n... (truncated)"

                duration_ms = (time.monotonic() - start_time) * 1000

                return ExecutionResult(
                    skill_path=skill.path,
                    status=ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED,
                    output=output,
                    error=error_output if error_output else None,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    context=context,
                    sandbox_id=str(sandbox_id) if sandbox_id else None,
                )

        except TimeoutError:
            duration_ms = (time.monotonic() - start_time) * 1000
            return ExecutionResult(
                skill_path=skill.path,
                status=ExecutionStatus.TIMEOUT,
                error=f"Execution timed out after {timeout}s",
                duration_ms=duration_ms,
                context=context,
                sandbox_id=str(sandbox_id) if sandbox_id else None,
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error(f"Microsandbox execution failed for {skill.path}: {e}")
            return ExecutionResult(
                skill_path=skill.path,
                status=ExecutionStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
                context=context,
                sandbox_id=str(sandbox_id) if sandbox_id else None,
            )

    def _find_script(self, skill: SkillInfo) -> Path | None:
        """Find the main executable script for a skill."""
        skill_dir = Path(skill.skill_dir)
        scripts_dir = skill_dir / "scripts"

        # Priority order for script discovery
        candidates = [
            scripts_dir / "main.py",
            scripts_dir / "run.py",
            scripts_dir / "execute.py",
            scripts_dir / "main.sh",
            scripts_dir / "run.sh",
        ]

        # Check priority candidates first
        for candidate in candidates:
            if candidate.exists():
                return candidate

        # Fall back to first available script
        if skill.scripts:
            first_script = scripts_dir / skill.scripts[0]
            if first_script.exists():
                return first_script

        return None


class SubprocessExecutor(SkillExecutor):
    """
    Execute skills using subprocess.

    Fallback executor when Microsandbox is not available.
    Provides basic isolation through process separation.
    """

    @property
    def name(self) -> str:
        return "subprocess"

    async def execute(
        self,
        skill: SkillInfo,
        context: dict[str, Any],
        timeout: float | None = None,
    ) -> ExecutionResult:
        """Execute skill in subprocess."""
        timeout = timeout or DEFAULT_TIMEOUT
        start_time = time.monotonic()

        try:
            # Find the script to execute
            script_path = self._find_script(skill)
            if not script_path:
                return ExecutionResult(
                    skill_path=skill.path,
                    status=ExecutionStatus.FAILED,
                    error=f"No executable script found for skill {skill.path}",
                    context=context,
                )

            # Prepare environment with context
            env = os.environ.copy()
            env["SKILL_CONTEXT"] = json.dumps(context)
            env["SKILL_PATH"] = skill.path
            env["SKILL_DIR"] = skill.skill_dir

            # Build command based on script type
            if script_path.suffix == ".py":
                cmd = ["python", str(script_path)]
            elif script_path.suffix in (".sh", ".bash"):
                cmd = ["bash", str(script_path)]
            else:
                cmd = [str(script_path)]

            # Run in subprocess
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                    cwd=skill.skill_dir,
                ),
            )

            output = result.stdout
            error_output = result.stderr

            # Truncate output if too large
            if len(output) > MAX_OUTPUT_SIZE:
                output = output[:MAX_OUTPUT_SIZE] + "\n... (truncated)"

            duration_ms = (time.monotonic() - start_time) * 1000

            return ExecutionResult(
                skill_path=skill.path,
                status=ExecutionStatus.SUCCESS
                if result.returncode == 0
                else ExecutionStatus.FAILED,
                output=output,
                error=error_output if error_output else None,
                exit_code=result.returncode,
                duration_ms=duration_ms,
                context=context,
            )

        except subprocess.TimeoutExpired:
            duration_ms = (time.monotonic() - start_time) * 1000
            return ExecutionResult(
                skill_path=skill.path,
                status=ExecutionStatus.TIMEOUT,
                error=f"Execution timed out after {timeout}s",
                duration_ms=duration_ms,
                context=context,
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error(f"Subprocess execution failed for {skill.path}: {e}")
            return ExecutionResult(
                skill_path=skill.path,
                status=ExecutionStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
                context=context,
            )

    def _find_script(self, skill: SkillInfo) -> Path | None:
        """Find the main executable script for a skill."""
        skill_dir = Path(skill.skill_dir)
        scripts_dir = skill_dir / "scripts"

        # Priority order for script discovery
        candidates = [
            scripts_dir / "main.py",
            scripts_dir / "run.py",
            scripts_dir / "execute.py",
            scripts_dir / "main.sh",
            scripts_dir / "run.sh",
        ]

        # Check priority candidates first
        for candidate in candidates:
            if candidate.exists():
                return candidate

        # Fall back to first available script
        if skill.scripts:
            first_script = scripts_dir / skill.scripts[0]
            if first_script.exists():
                return first_script

        return None


class SkillExecutorManager:
    """
    Manages skill executors with automatic fallback.

    Tries Microsandbox first, falls back to subprocess if unavailable.
    """

    def __init__(
        self,
        microsandbox_enabled: bool = True,
        microsandbox_url: str | None = None,
    ):
        """
        Initialize executor manager.

        Args:
            microsandbox_enabled: Whether to try Microsandbox
            microsandbox_url: Microsandbox server URL
        """
        self.microsandbox_enabled = microsandbox_enabled
        self._microsandbox = (
            MicrosandboxExecutor(server_url=microsandbox_url) if microsandbox_enabled else None
        )
        self._subprocess = SubprocessExecutor()
        self._active_executor: SkillExecutor | None = None
        self._outcomes: list[ExecutionOutcome] = []

    async def get_executor(self) -> SkillExecutor:
        """Get the appropriate executor, with fallback logic."""
        if self._active_executor is not None:
            return self._active_executor

        # Try Microsandbox first
        if self._microsandbox and await self._microsandbox.is_available():
            logger.info("Using Microsandbox executor")
            self._active_executor = self._microsandbox
        else:
            if self.microsandbox_enabled:
                logger.warning("Microsandbox not available, falling back to subprocess")
            self._active_executor = self._subprocess

        return self._active_executor

    async def execute(
        self,
        skill: SkillInfo,
        context: dict[str, Any],
        timeout: float | None = None,
        agent_id: str | None = None,
    ) -> ExecutionResult:
        """
        Execute a skill and record the outcome.

        Args:
            skill: Skill to execute
            context: Execution context
            timeout: Timeout in seconds
            agent_id: ID of the agent executing the skill

        Returns:
            ExecutionResult
        """
        executor = await self.get_executor()
        result = await executor.execute(skill, context, timeout)

        # Record outcome for learning
        outcome = ExecutionOutcome(
            skill_path=skill.path,
            agent_id=agent_id,
            status=result.status,
            success=result.status == ExecutionStatus.SUCCESS,
            duration_ms=result.duration_ms,
            context=context,
            output_summary=result.output[:500] if result.output else "",
            error=result.error,
            executed_at=result.executed_at,
        )
        self._outcomes.append(outcome)

        # Keep only last 1000 outcomes in memory
        if len(self._outcomes) > 1000:
            self._outcomes = self._outcomes[-1000:]

        return result

    def get_outcomes(self, limit: int = 100) -> list[ExecutionOutcome]:
        """Get recent execution outcomes."""
        return self._outcomes[-limit:]

    def get_executor_name(self) -> str:
        """Get the name of the active executor."""
        if self._active_executor:
            return self._active_executor.name
        return "none"


# Global executor manager
_executor_manager: SkillExecutorManager | None = None


def get_executor_manager(
    microsandbox_enabled: bool | None = None,
    microsandbox_url: str | None = None,
) -> SkillExecutorManager:
    """
    Get the global executor manager.

    Args:
        microsandbox_enabled: Enable Microsandbox (default: from env)
        microsandbox_url: Microsandbox URL (default: from env)

    Returns:
        SkillExecutorManager instance
    """
    global _executor_manager

    if _executor_manager is None:
        if microsandbox_enabled is None:
            microsandbox_enabled = os.environ.get("MICROSANDBOX_ENABLED", "true").lower() == "true"

        _executor_manager = SkillExecutorManager(
            microsandbox_enabled=microsandbox_enabled,
            microsandbox_url=microsandbox_url,
        )

    return _executor_manager
