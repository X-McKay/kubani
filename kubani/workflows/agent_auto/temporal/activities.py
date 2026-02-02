"""Temporal activities for the agent_auto workflow.

Activities are thin wrappers around capability functions, handling:
- Service instantiation from config
- Resource cleanup
- Temporal serialization requirements

All business logic lives in the capabilities/ modules.
"""

import logging
from typing import Any

from temporalio import activity

from kubani.framework.config import get_config

from ..capabilities.analysis import analyze_evaluation_failures
from ..capabilities.draft_agent import DraftingService
from ..capabilities.evaluate_agent import EvaluationService
from ..models import (
    AgentEvaluationResult,
    AgentTestCase,
    ImprovementSuggestions,
)
from ..protocols import (
    AgentRunner,
    AgentRunResult,
    SkillInfo,
    SkillRepository,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Service Factories
# =============================================================================


def _get_llm_service():
    """Create LLM service from config.

    Returns FrameworkLLM which implements the async LLMClient protocol.
    """
    from kubani.framework.llm import FrameworkLLM

    return FrameworkLLM()


class RealSkillRepository:
    """Real skill repository implementation that reads from disk."""

    def __init__(self, skills_root: str = "kubani/skills"):
        self._skills_root = skills_root

    def get_skills_by_name(self, names: list[str]) -> list[SkillInfo]:
        all_skills = self.list_skills()
        name_set = set(names)
        return [s for s in all_skills if s.name in name_set]

    def list_skills(self) -> list[SkillInfo]:
        import json
        from pathlib import Path

        skills = []
        skills_path = Path(self._skills_root)

        if not skills_path.exists():
            return skills

        for skill_dir in skills_path.rglob("SKILL.md"):
            skill_path = skill_dir.parent
            # Skip development skills
            if "_development" in str(skill_path):
                continue

            metadata_path = skill_path / "metadata.json"
            if metadata_path.exists():
                try:
                    metadata = json.loads(metadata_path.read_text())
                    skills.append(
                        SkillInfo(
                            name=metadata.get("name", skill_path.name),
                            description=metadata.get("description", ""),
                            version=metadata.get("version", "1.0.0"),
                        )
                    )
                except (json.JSONDecodeError, OSError):
                    # Fallback to directory name
                    skills.append(SkillInfo(name=skill_path.name))
            else:
                skills.append(SkillInfo(name=skill_path.name))

        return skills


class SkillInvocationTracker:
    """Context manager for tracking skill invocations during agent execution."""

    def __init__(self):
        self.invoked_skills: list[str] = []
        self._original_read = None

    def track_skill_read(self, skill_path: str) -> None:
        """Record a skill being read/invoked."""
        # Extract skill name from path (e.g., "kubani/skills/news/collection/fetch-rss-feeds/SKILL.md")
        from pathlib import Path

        path = Path(skill_path)
        if path.name == "SKILL.md":
            skill_name = path.parent.name
            if skill_name not in self.invoked_skills:
                self.invoked_skills.append(skill_name)
                logger.debug(f"Tracked skill invocation: {skill_name}")


class RealAgentRunner:
    """Real agent runner implementation.

    Runs agents in a sandboxed environment and captures their outputs.
    Supports SkillsOrchestrator-based agents.
    """

    def __init__(self, timeout_seconds: int = 120):
        self.timeout_seconds = timeout_seconds

    async def run(self, agent_path: str, prompt: str) -> AgentRunResult:
        """Run an agent with the given prompt.

        Dynamically imports the agent, runs it with the prompt, and captures
        skill invocations and output.

        Args:
            agent_path: Path to the agent directory (containing agent.py)
            prompt: The prompt/task to execute

        Returns:
            AgentRunResult with output, invoked skills, and success status
        """
        import asyncio
        import importlib.util
        import sys
        from pathlib import Path

        agent_dir = Path(agent_path)
        agent_file = agent_dir / "agent.py"

        if not agent_file.exists():
            return AgentRunResult(
                output="",
                invoked_skills=[],
                success=False,
                error=f"Agent file not found: {agent_file}",
            )

        tracker = SkillInvocationTracker()

        try:
            # Add agent directory to path temporarily
            agent_parent = str(agent_dir.parent)
            if agent_parent not in sys.path:
                sys.path.insert(0, agent_parent)

            # Import the agent module dynamically
            spec = importlib.util.spec_from_file_location(
                f"agent_{agent_dir.name}", str(agent_file)
            )
            if spec is None or spec.loader is None:
                return AgentRunResult(
                    output="",
                    invoked_skills=[],
                    success=False,
                    error=f"Could not load agent module: {agent_file}",
                )

            module = importlib.util.module_from_spec(spec)
            sys.modules[f"agent_{agent_dir.name}"] = module
            spec.loader.exec_module(module)

            # Find the agent class (should inherit from SkillsOrchestrator)
            agent_class = None
            for name, obj in vars(module).items():
                if (
                    isinstance(obj, type)
                    and hasattr(obj, "SKILLS_DOMAIN")
                    and name != "SkillsOrchestrator"
                ):
                    agent_class = obj
                    break

            if agent_class is None:
                # Try to find any class that looks like an agent
                for name, obj in vars(module).items():
                    if isinstance(obj, type) and "Agent" in name:
                        agent_class = obj
                        break

            if agent_class is None:
                return AgentRunResult(
                    output="",
                    invoked_skills=[],
                    success=False,
                    error="No agent class found in module",
                )

            # Instantiate and run the agent
            agent = agent_class(agent_dir=agent_dir)

            # Hook into skill loading to track invocations
            if hasattr(agent, "_skills"):
                for skill in agent._skills:
                    tracker.track_skill_read(str(skill.skill_path / "SKILL.md"))

            # Run the agent with timeout
            output = ""
            try:
                # Look for common execution methods
                if hasattr(agent, "execute"):
                    output = await asyncio.wait_for(
                        agent.execute(prompt),
                        timeout=self.timeout_seconds,
                    )
                elif hasattr(agent, "run"):
                    output = await asyncio.wait_for(
                        agent.run(prompt),
                        timeout=self.timeout_seconds,
                    )
                elif hasattr(agent, "collect"):  # FeedCollector pattern
                    result = await asyncio.wait_for(
                        agent.collect(),
                        timeout=self.timeout_seconds,
                    )
                    output = str(result) if result else ""
                elif hasattr(agent, "analyze"):  # ContentAnalyst pattern
                    # Need to parse input from prompt
                    result = await asyncio.wait_for(
                        agent.analyze_articles([]),  # Empty for now
                        timeout=self.timeout_seconds,
                    )
                    output = str(result) if result else ""
                else:
                    return AgentRunResult(
                        output="",
                        invoked_skills=tracker.invoked_skills,
                        success=False,
                        error="Agent has no recognized execution method (execute, run, collect, analyze)",
                    )

                # Convert output to string
                if output is None:
                    output = ""
                elif hasattr(output, "model_dump"):
                    import json
                    output = json.dumps(output.model_dump(), indent=2)
                elif hasattr(output, "__dict__"):
                    import json
                    output = json.dumps(output.__dict__, indent=2, default=str)
                else:
                    output = str(output)

            except asyncio.TimeoutError:
                return AgentRunResult(
                    output="",
                    invoked_skills=tracker.invoked_skills,
                    success=False,
                    error=f"Agent execution timed out after {self.timeout_seconds}s",
                )

            return AgentRunResult(
                output=output,
                invoked_skills=tracker.invoked_skills,
                success=True,
                error=None,
            )

        except Exception as e:
            logger.exception(f"Agent execution failed: {e}")
            return AgentRunResult(
                output="",
                invoked_skills=tracker.invoked_skills,
                success=False,
                error=str(e),
            )
        finally:
            # Clean up sys.path
            if agent_parent in sys.path:
                sys.path.remove(agent_parent)
            # Clean up module
            if f"agent_{agent_dir.name}" in sys.modules:
                del sys.modules[f"agent_{agent_dir.name}"]


def _get_file_service():
    """Create file service."""
    from ..utils import DefaultFileSystem

    return DefaultFileSystem()


def create_skill_repo() -> SkillRepository:
    """Create skill repository from config."""
    config = get_config()
    skills_root = getattr(config, "skills_root", "kubani/skills")
    return RealSkillRepository(skills_root)


def create_agent_runner() -> AgentRunner:
    """Create agent runner implementation."""
    return RealAgentRunner()


# =============================================================================
# Agent Drafting Activities
# =============================================================================


@activity.defn
async def draft_agent_activity(description: str) -> dict[str, Any]:
    """Activity to draft an agent, identifying missing skills and initial files.

    Args:
        description: High-level description of the agent to create.

    Returns:
        Dictionary containing:
        - agent_spec: The generated agent specification
        - missing_skills: List of skill names that need to be created
        - files_to_create: Dict mapping file paths to their content
    """
    activity.heartbeat()

    drafting_service = DraftingService(
        llm_client=_get_llm_service(),
        fs=_get_file_service(),
        skill_repo=create_skill_repo(),
    )

    result = await drafting_service.draft_agent(description)

    # Convert AgentSpec to dict for Temporal serialization
    if hasattr(result.get("agent_spec"), "model_dump"):
        result["agent_spec"] = result["agent_spec"].model_dump()

    return result


@activity.defn
async def write_agent_files_activity(
    files_to_create: dict[str, str],
) -> dict[str, Any]:
    """Activity to write agent files to disk.

    Args:
        files_to_create: Dict mapping file paths to their content.

    Returns:
        Dictionary with written file paths and status.
    """
    activity.heartbeat()

    fs = _get_file_service()
    written_files = []

    for path, content in files_to_create.items():
        try:
            fs.write(path, content)
            written_files.append(path)
            logger.info(f"Wrote agent file: {path}")
        except Exception as e:
            logger.error(f"Failed to write {path}: {e}")
            return {
                "success": False,
                "written_files": written_files,
                "error": str(e),
            }

    return {
        "success": True,
        "written_files": written_files,
    }


# =============================================================================
# Agent Evaluation Activities
# =============================================================================


@activity.defn
async def evaluate_agent_activity(
    agent_path: str,
    test_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Activity to evaluate an agent's performance.

    Args:
        agent_path: Path to the agent directory.
        test_cases: List of test case dictionaries.

    Returns:
        AgentEvaluationResult as a dictionary.
    """
    activity.heartbeat()

    # Convert dict test cases to AgentTestCase objects
    typed_test_cases = [AgentTestCase(**tc) for tc in test_cases]

    eval_service = EvaluationService(agent_runner=create_agent_runner())
    result = await eval_service.evaluate_agent(agent_path, typed_test_cases)

    # Return as dict for Temporal serialization
    return result.model_dump()


@activity.defn
async def analyze_failures_activity(
    eval_result: dict[str, Any],
) -> dict[str, Any]:
    """Activity to analyze evaluation failures and suggest improvements.

    Args:
        eval_result: AgentEvaluationResult as a dictionary.

    Returns:
        ImprovementSuggestions as a dictionary.
    """
    activity.heartbeat()

    # Convert dict to typed model
    typed_result = AgentEvaluationResult(**eval_result)

    # Use pure domain function for analysis
    suggestions = analyze_evaluation_failures(typed_result)

    return suggestions.model_dump()


# =============================================================================
# Agent Improvement Activities
# =============================================================================


@activity.defn
async def apply_improvements_activity(
    agent_path: str,
    suggestions: dict[str, Any],
) -> dict[str, Any]:
    """Activity to apply improvements to agent files.

    Args:
        agent_path: Path to the agent directory.
        suggestions: ImprovementSuggestions as a dictionary.

    Returns:
        Dictionary with improvement results.
    """
    activity.heartbeat()

    # Convert dict to typed model
    typed_suggestions = ImprovementSuggestions(**suggestions)

    fs = _get_file_service()

    # Read current prompt
    prompt_path = f"{agent_path}/prompt.md"
    if not fs.exists(prompt_path):
        return {
            "success": False,
            "error": f"Prompt file not found: {prompt_path}",
        }

    current_prompt = fs.read(prompt_path)

    # Apply prompt clarifications
    if typed_suggestions.prompt_clarifications:
        # Add clarifications as comments/notes to the prompt
        clarification_section = "\n\n## Improvement Notes\n\n"
        for clarification in typed_suggestions.prompt_clarifications:
            clarification_section += f"- {clarification}\n"
        current_prompt += clarification_section

    # Write updated prompt
    fs.write(prompt_path, current_prompt)

    # Update config with skill changes if needed
    config_path = f"{agent_path}/config.yaml"
    if fs.exists(config_path) and (
        typed_suggestions.skill_additions or typed_suggestions.config_changes
    ):
        import yaml

        config_content = fs.read(config_path)
        config = yaml.safe_load(config_content)

        # Add new skills
        if typed_suggestions.skill_additions:
            current_required = config.get("skills", {}).get("required", [])
            for skill in typed_suggestions.skill_additions:
                if skill not in current_required:
                    current_required.append(skill)
            config.setdefault("skills", {})["required"] = current_required

        # Apply other config changes
        if typed_suggestions.config_changes:
            for key, value in typed_suggestions.config_changes.items():
                # Handle nested keys like "settings.timeout"
                keys = key.split(".")
                target = config
                for k in keys[:-1]:
                    target = target.setdefault(k, {})
                target[keys[-1]] = value

        fs.write(config_path, yaml.dump(config, default_flow_style=False))

    return {
        "success": True,
        "prompt_updated": bool(typed_suggestions.prompt_clarifications),
        "config_updated": bool(
            typed_suggestions.skill_additions or typed_suggestions.config_changes
        ),
    }


# =============================================================================
# Agent Publishing Activities
# =============================================================================


@activity.defn
async def publish_agent_activity(
    agent_path: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    """Activity to publish the final agent.

    Args:
        agent_path: Path to the agent directory.
        options: Publishing options (e.g., target location, registry sync).

    Returns:
        Dictionary with publishing results.
    """
    activity.heartbeat()

    fs = _get_file_service()

    # Verify agent files exist
    prompt_path = f"{agent_path}/prompt.md"
    config_path = f"{agent_path}/config.yaml"

    if not fs.exists(prompt_path):
        return {"success": False, "error": "Agent prompt.md not found"}
    if not fs.exists(config_path):
        return {"success": False, "error": "Agent config.yaml not found"}

    # Copy to target location if specified
    target_path = options.get("target_path")
    if target_path and target_path != agent_path:
        import shutil
        from pathlib import Path

        src = Path(agent_path)
        dst = Path(target_path)
        dst.mkdir(parents=True, exist_ok=True)

        for file in src.iterdir():
            if file.is_file():
                shutil.copy2(file, dst / file.name)

        logger.info(f"Published agent from {agent_path} to {target_path}")
        published_path = target_path
    else:
        published_path = agent_path

    # TODO: Sync to registry if requested
    sync_to_registry = options.get("sync_to_registry", False)
    if sync_to_registry:
        logger.info("Registry sync not yet implemented")

    return {
        "success": True,
        "published_path": published_path,
        "synced_to_registry": False,
    }
