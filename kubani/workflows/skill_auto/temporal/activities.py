"""Temporal activities for the Skill Auto workflow.

Activities are thin wrappers around capability functions, handling:
- Service instantiation from config
- Resource cleanup
- Temporal serialization requirements (dicts instead of dataclasses)

All business logic lives in the capabilities/ modules.
"""

import json
import logging
from dataclasses import asdict
from typing import Any

from temporalio import activity

from ..models import create_no_overlap_result

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


def _get_file_service():
    """Create file service."""
    from ..utils import DefaultFileSystem

    return DefaultFileSystem()


def _get_llm_client():
    """Create LLM client from config for evaluation."""
    from kubani.framework.llm import FrameworkLLM

    return FrameworkLLM()


# =============================================================================
# Skill Discovery Activities
# =============================================================================


@activity.defn
async def load_existing_skills_activity(
    skills_path: str,
    include_development: bool = True,
) -> list[dict[str, Any]]:
    """
    Load metadata for all existing skills.

    Args:
        skills_path: Path to skills directory
        include_development: Whether to include _development skills

    Returns:
        List of skill metadata dicts
    """
    from ..capabilities.promote_skill import load_existing_skills

    fs = _get_file_service()
    return load_existing_skills(fs, skills_path, include_development)


@activity.defn
async def detect_skill_overlap_activity(
    description: str,
    existing_skills: list[dict[str, Any]],
    llm_client: Any = None,  # Kept for backward compatibility, ignored
) -> dict[str, Any]:
    """
    Detect if a new skill overlaps with existing skills.

    Args:
        description: Description of the new skill
        existing_skills: List of existing skills with name and description
        llm_client: Deprecated, ignored

    Returns:
        OverlapResult as dict
    """
    from ..capabilities.detect_skill_overlap import detect_skill_overlap

    if not existing_skills:
        result = create_no_overlap_result()
        return asdict(result)

    llm = _get_llm_service()
    result = await detect_skill_overlap(llm, description, existing_skills)
    return asdict(result)


# =============================================================================
# Skill Creation Activities
# =============================================================================


@activity.defn
async def infer_skill_structure_activity(
    description: str,
    llm_client: Any = None,  # Kept for backward compatibility, ignored
    context: str | None = None,
) -> dict[str, Any]:
    """
    Infer skill structure from a description using LLM.

    Args:
        description: Natural language description of the skill
        llm_client: Deprecated, ignored
        context: Optional additional context

    Returns:
        Skill specification dict
    """
    from ..capabilities.draft_skill import draft_skill

    llm = _get_llm_service()
    spec = await draft_skill(llm, description, context)
    return spec.model_dump()


@activity.defn
async def generate_test_cases_activity(
    spec: dict[str, Any],
    llm_client: Any = None,  # Kept for backward compatibility, ignored
    seed_tests: str | None = None,
) -> str:
    """
    Generate test cases YAML from skill specification.

    Args:
        spec: Skill specification with examples
        llm_client: Deprecated, ignored
        seed_tests: Optional seed test cases to expand from

    Returns:
        YAML string with test cases
    """
    from ..capabilities.draft_test_cases import draft_test_cases

    llm = _get_llm_service()
    return await draft_test_cases(llm, spec, seed_tests)


@activity.defn
async def write_skill_files_activity(
    spec: dict[str, Any],
    test_cases: str,
    output_dir: str,
) -> dict[str, str]:
    """
    Write skill files to disk.

    Args:
        spec: Skill specification
        test_cases: Test cases YAML content
        output_dir: Directory to write to

    Returns:
        Dict with path, content, and test_cases
    """
    from ..utils import write_skill_files

    fs = _get_file_service()
    return write_skill_files(fs, spec, test_cases, output_dir)


# =============================================================================
# File I/O Activities
# =============================================================================


@activity.defn
async def read_file_content_activity(file_path: str) -> str:
    """
    Read file content as a string.

    Args:
        file_path: Path to file to read

    Returns:
        File content as string
    """
    fs = _get_file_service()
    return fs.read(file_path)


@activity.defn
async def write_file_content_activity(file_path: str, content: str) -> None:
    """
    Write content to a file.

    Args:
        file_path: Path to file to write
        content: Content to write
    """
    fs = _get_file_service()
    fs.write(file_path, content)


# =============================================================================
# Evaluation Activities
# =============================================================================


@activity.defn
async def run_evaluation_activity(
    skill_path: str,
    sandbox_type: str = "auto",
) -> dict[str, Any]:
    """
    Run skill evaluation and return metrics with feedback.

    Uses sandbox-based evaluation to run test cases against the skill.

    Args:
        skill_path: Path to skill directory
        sandbox_type: Sandbox backend (auto, microsandbox, docker)

    Returns:
        Dict with 'metrics' (EvalMetrics as dict) and 'feedback' (formatted feedback string)
    """
    from ..capabilities.evaluate_skill import evaluate_skill

    logger.info(f"run_evaluation_activity: Starting for {skill_path}")

    try:
        metrics, feedback = evaluate_skill(skill_path, sandbox_type=sandbox_type)
        logger.info(
            f"run_evaluation_activity: Accuracy={metrics.accuracy:.1%}, "
            f"Tests={metrics.tests_passed}/{metrics.tests_total}"
        )

        return {
            "metrics": {
                "accuracy": metrics.accuracy,
                "latency_ms": metrics.latency_ms,
                "tests_passed": metrics.tests_passed,
                "tests_total": metrics.tests_total,
                "critic_confidence": metrics.critic_confidence,
                "tokens_prompt": metrics.tokens_prompt,
                "tokens_completion": metrics.tokens_completion,
            },
            "feedback": feedback,
        }
    except Exception as e:
        logger.exception(f"run_evaluation_activity: Failed with error: {e}")
        raise


@activity.defn
async def run_improvement_activity(
    skill_path: str,
    feedback: str,
    llm_client: Any | None = None,  # Kept for backward compatibility
    create_backups: bool = True,
    max_backups: int = 3,
) -> dict[str, Any]:
    """
    Run skill improvement based on feedback.

    Args:
        skill_path: Path to skill directory
        feedback: Evaluation feedback to address
        llm_client: Deprecated, ignored (created from config)
        create_backups: Whether to create backups before modification
        max_backups: Maximum number of backups to keep per file

    Returns:
        Dict with improvement results
    """
    from ..capabilities.improve_skill import improve_skill
    from ..utils import create_backup, parse_skill_frontmatter

    fs = _get_file_service()
    skill_md_path = f"{skill_path}/SKILL.md"
    metadata_path = f"{skill_path}/metadata.json"

    # Read current content
    current_content = fs.read(skill_md_path)

    # Get improved content from LLM
    client = _get_llm_client()
    new_content = await improve_skill(client, current_content, feedback)

    # Create backup before modification (if enabled)
    if create_backups and fs.exists(skill_md_path):
        create_backup(fs, skill_md_path, max_backups=max_backups)

    fs.write(skill_md_path, new_content)

    result = {"improved": True, "new_content": new_content}

    # Update metadata.json version to match SKILL.md frontmatter
    frontmatter = parse_skill_frontmatter(new_content)
    if frontmatter.get("version") and fs.exists(metadata_path):
        try:
            metadata = json.loads(fs.read(metadata_path))
            if metadata.get("version") != frontmatter["version"]:
                metadata["version"] = frontmatter["version"]
                fs.write(metadata_path, json.dumps(metadata, indent=2))
                result["version_updated"] = frontmatter["version"]
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to update metadata.json version: {e}")

    return result


# =============================================================================
# Notification Activities
# =============================================================================


@activity.defn
async def send_notification_activity(
    event: str,
    skill_name: str,
    channel: str,
    discord_client: Any = None,  # Kept for signature compatibility
    iteration: int | None = None,
    metrics: Any | None = None,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Send Discord notification for workflow events.

    Args:
        event: Event type (started, iteration_complete, complete, failed)
        skill_name: Name of the skill being developed
        channel: Discord channel name
        discord_client: Discord MCP client (optional)
        iteration: Current iteration number
        metrics: EvalMetrics dict or object
        error: Error message if failed
        result: Final result dict if complete

    Returns:
        Dict with sent status and message_id
    """
    from ..capabilities.promote_skill import send_notification

    if discord_client:
        return await send_notification(
            discord=discord_client,
            event_type=event,
            channel=channel,
            skill_name=skill_name,
            iteration=iteration,
            metrics=metrics,
            error=error,
            result=result,
        )

    # Log if no Discord client
    logger.info(f"Notification ({event}): {skill_name}")
    return {"sent": False, "reason": "no_discord_client"}


# =============================================================================
# Promotion Activities
# =============================================================================


@activity.defn
async def check_promotion_overlap_activity(
    skill_name: str,
    skill_description: str,
    production_skills: list[dict[str, str]],
    llm_client: Any = None,  # Kept for backward compatibility
    allow_overlap: bool = False,
) -> dict[str, Any]:
    """
    Check if a skill overlaps with production skills before promotion.

    Args:
        skill_name: Name of the skill to promote
        skill_description: Description of the skill
        production_skills: List of production skills
        llm_client: Deprecated, ignored
        allow_overlap: If True, return warning instead of raising

    Returns:
        OverlapResult as dict

    Raises:
        SkillOverlapError: If overlap detected and allow_overlap=False
    """
    from ..capabilities.promote_skill import check_promotion_overlap

    llm = _get_llm_service()
    result = await check_promotion_overlap(
        client=llm,
        skill_name=skill_name,
        skill_description=skill_description,
        production_skills=production_skills,
        allow_overlap=allow_overlap,
    )
    return asdict(result)


@activity.defn
async def promote_skill_activity(
    skill_path: str,
    target_category: str,
    skills_root: str,
) -> dict[str, Any]:
    """
    Promote a skill from _development to production location.

    Args:
        skill_path: Path to the development skill directory
        target_category: Target category directory
        skills_root: Root skills directory

    Returns:
        Dict with success status and promoted_path
    """
    from ..capabilities.promote_skill import promote_skill

    fs = _get_file_service()
    try:
        return promote_skill(fs, skill_path, target_category, skills_root)
    except Exception as e:
        logger.error(f"Failed to promote skill: {e}")
        return {"success": False, "error": str(e)}


@activity.defn
async def await_approval_activity(
    channel_id: str,
    message_id: str,
    discord_client: Any,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """
    Wait for approval reaction on a Discord message.

    Args:
        channel_id: Discord channel ID
        message_id: Message ID to watch
        discord_client: Discord MCP client
        timeout_seconds: How long to wait

    Returns:
        Dict with approved/rejected/timeout status
    """
    from ..capabilities.promote_skill import await_approval

    return await await_approval(
        discord=discord_client,
        channel_id=channel_id,
        message_id=message_id,
        timeout_seconds=timeout_seconds,
    )


@activity.defn
async def sync_registry_activity(
    skill_path: str,
    registry_client: Any,
) -> dict[str, Any]:
    """
    Sync a promoted skill to the registry.

    Args:
        skill_path: Path to the skill directory
        registry_client: Registry client for registration

    Returns:
        Dict with sync status
    """
    from ..capabilities.promote_skill import sync_registry

    fs = _get_file_service()
    return await sync_registry(fs, skill_path, registry_client)


@activity.defn
async def send_promotion_request_activity(
    skill_name: str,
    skill_path: str,
    metrics: Any,
    iterations: int,
    channel: str,
    discord_client: Any,
) -> dict[str, Any]:
    """
    Send a promotion request message to Discord.

    Args:
        skill_name: Name of the skill
        skill_path: Path to the skill
        metrics: Final evaluation metrics
        iterations: Number of iterations completed
        channel: Discord channel name
        discord_client: Discord MCP client

    Returns:
        Dict with sent status and message_id
    """
    from ..capabilities.promote_skill import send_promotion_request

    # Convert metrics to dict if needed
    metrics_dict = None
    if metrics:
        if hasattr(metrics, "accuracy"):
            metrics_dict = {
                "accuracy": metrics.accuracy,
                "tests_passed": metrics.tests_passed,
                "tests_total": metrics.tests_total,
            }
        else:
            metrics_dict = metrics

    return await send_promotion_request(
        discord=discord_client,
        skill_name=skill_name,
        skill_path=skill_path,
        metrics=metrics_dict,
        iterations=iterations,
        channel=channel,
    )


# =============================================================================
# Hardening Activities
# =============================================================================


@activity.defn
async def generate_harder_tests_activity(
    skill_name: str,
    current_test_cases: str,
    metrics: Any,
    failing_tests: list[dict[str, str]],
    llm_client: Any = None,  # Kept for backward compatibility
    count: int = 2,
) -> str:
    """
    Generate harder test cases targeting weaknesses.

    Args:
        skill_name: Name of the skill
        current_test_cases: Current test cases YAML
        metrics: Current evaluation metrics
        failing_tests: List of failing tests
        llm_client: Deprecated, ignored
        count: Number of new tests to generate

    Returns:
        YAML string with new test cases
    """
    from ..capabilities.draft_test_cases import generate_harder_tests

    # Handle metrics as dict or object
    accuracy = metrics.accuracy if hasattr(metrics, "accuracy") else metrics.get("accuracy", 0)
    tests_passed = (
        metrics.tests_passed if hasattr(metrics, "tests_passed") else metrics.get("tests_passed", 0)
    )
    tests_total = (
        metrics.tests_total if hasattr(metrics, "tests_total") else metrics.get("tests_total", 0)
    )

    llm = _get_llm_service()
    return await generate_harder_tests(
        client=llm,
        skill_name=skill_name,
        current_tests=current_test_cases,
        accuracy=accuracy,
        tests_passed=tests_passed,
        tests_total=tests_total,
        failing_tests=failing_tests,
        count=count,
    )


@activity.defn
async def revert_to_best_version_activity(
    skill_path: str,
    best_version: Any,
) -> dict[str, Any]:
    """
    Revert skill files to a previous best version.

    Args:
        skill_path: Path to the skill directory
        best_version: SkillVersion with content to restore

    Returns:
        Dict with revert status
    """
    from ..capabilities.improve_skill import revert_to_best_version

    # Handle best_version as dict (Temporal serialization)
    content = (
        best_version.content
        if hasattr(best_version, "content")
        else best_version.get("content", "")
    )
    test_cases = (
        best_version.test_cases
        if hasattr(best_version, "test_cases")
        else best_version.get("test_cases", "")
    )
    iteration = (
        best_version.iteration
        if hasattr(best_version, "iteration")
        else best_version.get("iteration", 0)
    )

    fs = _get_file_service()
    result = revert_to_best_version(fs, skill_path, content, test_cases)
    result["reverted_to_iteration"] = iteration

    return result


@activity.defn
async def save_iteration_result_activity(
    skill_path: str,
    iteration_result: Any,
) -> dict[str, Any]:
    """
    Save iteration result to a JSON file.

    Args:
        skill_path: Path to the skill directory
        iteration_result: IterationResult to save

    Returns:
        Dict with save status
    """
    from ..utils import save_iteration_result

    # Handle iteration_result as dict
    iteration = (
        iteration_result.iteration
        if hasattr(iteration_result, "iteration")
        else iteration_result.get("iteration", 0)
    )
    score = (
        iteration_result.score
        if hasattr(iteration_result, "score")
        else iteration_result.get("score", 0)
    )
    improved = (
        iteration_result.improved
        if hasattr(iteration_result, "improved")
        else iteration_result.get("improved", False)
    )
    action = (
        iteration_result.action
        if hasattr(iteration_result, "action")
        else iteration_result.get("action", "unknown")
    )
    error = (
        iteration_result.error
        if hasattr(iteration_result, "error")
        else iteration_result.get("error")
    )

    # Extract metrics if present
    metrics = None
    if hasattr(iteration_result, "metrics") and iteration_result.metrics:
        m = iteration_result.metrics
        metrics = {
            "accuracy": m.accuracy if hasattr(m, "accuracy") else m.get("accuracy", 0),
            "latency_ms": m.latency_ms if hasattr(m, "latency_ms") else m.get("latency_ms", 0),
            "tests_passed": m.tests_passed
            if hasattr(m, "tests_passed")
            else m.get("tests_passed", 0),
            "tests_total": m.tests_total if hasattr(m, "tests_total") else m.get("tests_total", 0),
            "critic_confidence": m.critic_confidence
            if hasattr(m, "critic_confidence")
            else m.get("critic_confidence", 0),
        }
    elif isinstance(iteration_result, dict) and iteration_result.get("metrics"):
        metrics = iteration_result["metrics"]

    fs = _get_file_service()
    return save_iteration_result(fs, skill_path, iteration, score, improved, action, metrics, error)


@activity.defn
async def load_iteration_history_activity(
    skill_path: str,
) -> list[dict[str, Any]]:
    """
    Load all iteration history files from a skill directory.

    Args:
        skill_path: Path to the skill directory

    Returns:
        List of iteration result dicts
    """
    from ..utils import load_iteration_history

    fs = _get_file_service()
    return load_iteration_history(fs, skill_path)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Skill Discovery
    "load_existing_skills_activity",
    "detect_skill_overlap_activity",
    # Skill Creation
    "infer_skill_structure_activity",
    "generate_test_cases_activity",
    "write_skill_files_activity",
    # File I/O
    "read_file_content_activity",
    "write_file_content_activity",
    # Evaluation
    "run_evaluation_activity",
    "run_improvement_activity",
    # Notifications
    "send_notification_activity",
    # Promotion
    "check_promotion_overlap_activity",
    "promote_skill_activity",
    "await_approval_activity",
    "sync_registry_activity",
    "send_promotion_request_activity",
    # Hardening
    "generate_harder_tests_activity",
    "revert_to_best_version_activity",
    "save_iteration_result_activity",
    "load_iteration_history_activity",
]
