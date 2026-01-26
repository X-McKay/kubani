"""Temporal activities for the Skill Auto workflow.

Activities are thin wrappers around service layers, handling:
- Service instantiation from config
- Resource cleanup
- Temporal serialization requirements (strings instead of Path objects)

All business logic lives in the service modules (core.py, llm_service.py, etc.).
"""

import logging
from typing import Any

from temporalio import activity

from kubani.framework.config import get_config

from .core import create_no_overlap_result
from .eval_service import (
    EvalService,
    ImproveService,
    results_to_metrics,
)
from .file_service import FileService
from .file_service import load_existing_skills as _load_existing_skills
from .file_service import promote_skill as _promote_skill
from .file_service import revert_to_version as _revert_to_version
from .file_service import save_iteration_result as _save_iteration_result
from .file_service import write_skill_files as _write_skill_files
from .llm_service import LLMService
from .llm_service import detect_overlap as _detect_overlap
from .llm_service import generate_harder_tests as _generate_harder_tests
from .llm_service import generate_test_cases as _generate_test_cases
from .llm_service import infer_skill_structure as _infer_skill_structure
from .models import OverlapResult

logger = logging.getLogger(__name__)


# =============================================================================
# Service Factory
# =============================================================================


def _get_llm_service() -> LLMService:
    """Create LLM service from config."""
    config = get_config()
    return LLMService(
        base_url=config.llm.api_url,
        model=config.llm.model,
        api_key=config.llm.api_key,
    )


def _get_file_service() -> FileService:
    """Create file service."""
    return FileService()


# =============================================================================
# Skill Discovery Activities
# =============================================================================


@activity.defn
async def load_existing_skills(
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
    fs = _get_file_service()
    return _load_existing_skills(fs, skills_path, include_development)


@activity.defn
async def detect_skill_overlap(
    description: str,
    existing_skills: list[dict[str, Any]],
    llm_client: Any = None,  # Kept for backward compatibility, ignored
) -> OverlapResult:
    """
    Detect if a new skill overlaps with existing skills.

    Args:
        description: Description of the new skill
        existing_skills: List of existing skills with name and description
        llm_client: Deprecated, ignored

    Returns:
        OverlapResult with overlap assessment
    """
    if not existing_skills:
        return create_no_overlap_result()

    llm = _get_llm_service()
    try:
        return await _detect_overlap(llm, description, existing_skills)
    finally:
        await llm.close()


# =============================================================================
# Skill Creation Activities
# =============================================================================


@activity.defn
async def infer_skill_structure(
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
    llm = _get_llm_service()
    try:
        return await _infer_skill_structure(llm, description, context)
    finally:
        await llm.close()


@activity.defn
async def generate_test_cases(
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
    llm = _get_llm_service()
    try:
        return await _generate_test_cases(llm, spec, seed_tests)
    finally:
        await llm.close()


@activity.defn
async def write_skill_files(
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
    fs = _get_file_service()
    return _write_skill_files(fs, spec, test_cases, output_dir)


# =============================================================================
# File I/O Activities
# =============================================================================


@activity.defn
async def read_file_content(file_path: str) -> str:
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
async def write_file_content(file_path: str, content: str) -> None:
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
async def run_evaluation(
    skill_path: str,
    llm_client: Any | None = None,  # Kept for backward compatibility
    evaluator: Any | None = None,  # Kept for backward compatibility
) -> dict[str, Any]:
    """
    Run skill evaluation and return metrics with feedback.

    Args:
        skill_path: Path to skill directory
        llm_client: Deprecated, ignored (created from config)
        evaluator: Deprecated, ignored (created internally)

    Returns:
        Dict with 'metrics' (EvalMetrics as dict) and 'feedback' (formatted feedback string)
    """
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"run_evaluation: Starting for {skill_path}")

    try:
        from kubani_dev.llm_client import LLMClient

        from .eval_service import format_evaluation_feedback

        config = get_config()
        # Strip /v1 suffix since LLMClient adds it
        base_url = config.llm.api_url.removesuffix("/v1")
        logger.info(f"run_evaluation: Using LLM at {base_url}")

        client = LLMClient(
            base_url=base_url,
            model=config.llm.model,
            timeout=120,
            enable_thinking=False,
        )

        eval_service = EvalService(client)
        logger.info("run_evaluation: Running evaluation...")
        raw_result = eval_service.evaluate_skill(skill_path)
        logger.info(f"run_evaluation: Got raw_result with keys: {raw_result.keys()}")

        metrics = results_to_metrics(raw_result)
        feedback = format_evaluation_feedback(raw_result)
        logger.info(
            f"run_evaluation: Accuracy={metrics.accuracy:.1%}, Tests={metrics.tests_passed}/{metrics.tests_total}"
        )

        # Return dict for Temporal serialization (dataclasses serialize to dicts)
        result = {
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
        logger.info(f"run_evaluation: Returning result with keys: {result.keys()}")
        return result
    except Exception as e:
        logger.exception(f"run_evaluation: Failed with error: {e}")
        raise


@activity.defn
async def run_improvement(
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
    from kubani_dev.llm_client import LLMClient

    from .file_service import create_backup

    config = get_config()
    # Strip /v1 suffix since LLMClient adds it
    base_url = config.llm.api_url.removesuffix("/v1")
    client = LLMClient(
        base_url=base_url,
        model=config.llm.model,
        timeout=120,
        enable_thinking=False,
    )

    improve_service = ImproveService(client)
    result = improve_service.improve_skill(skill_path, feedback)

    # Write improved content if successful
    if result.get("improved") and result.get("new_content"):
        import json

        from .core import parse_skill_frontmatter

        fs = _get_file_service()
        skill_md_path = f"{skill_path}/SKILL.md"
        metadata_path = f"{skill_path}/metadata.json"

        # Create backup before modification (if enabled)
        if create_backups and fs.exists(skill_md_path):
            create_backup(fs, skill_md_path, max_backups=max_backups)

        fs.write(skill_md_path, result["new_content"])

        # Update metadata.json version to match SKILL.md frontmatter
        frontmatter = parse_skill_frontmatter(result["new_content"])
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
async def send_notification(
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

    # Handle metrics as dict (Temporal serializes dataclasses to dicts)
    def get_metric(name: str, default: Any = None) -> Any:
        if metrics is None:
            return default
        if isinstance(metrics, dict):
            return metrics.get(name, default)
        return getattr(metrics, name, default)

    # Build embed based on event type
    if event == "started":
        embed = {
            "title": f"Skill Development Started: {skill_name}",
            "description": "Auto-mode skill development workflow has begun.",
            "color": 0x3498DB,
        }
    elif event == "iteration_complete":
        accuracy = get_metric("accuracy", 0)
        accuracy_pct = f"{accuracy * 100:.1f}%" if metrics else "N/A"
        tests_passed = get_metric("tests_passed", 0)
        tests_total = get_metric("tests_total", 0)
        embed = {
            "title": f"Iteration {iteration} Complete: {skill_name}",
            "description": f"Accuracy: {accuracy_pct}, Tests: {tests_passed}/{tests_total}",
            "color": 0xF39C12,
        }
    elif event == "complete":
        final_accuracy = result.get("final_metrics", {}).get("accuracy", 0) if result else 0
        embed = {
            "title": f"Skill Development Complete: {skill_name}",
            "description": f"Final accuracy: {final_accuracy * 100:.1f}%",
            "color": 0x2ECC71,
        }
    elif event == "failed":
        embed = {
            "title": f"Skill Development Failed: {skill_name}",
            "description": error or "Unknown error",
            "color": 0xE74C3C,
        }
    else:
        embed = {
            "title": f"Skill Update: {skill_name}",
            "description": f"Event: {event}",
            "color": 0x9B59B6,
        }

    # Try to send via Discord if client available
    if discord_client:
        try:
            response = await discord_client.send_embed(
                channel_name=channel,
                embed=embed,
            )
            return {"sent": True, "message_id": response.get("message_id")}
        except Exception as e:
            logger.warning(f"Failed to send Discord notification: {e}")
            return {"sent": False, "error": str(e)}

    # Log if no Discord client
    logger.info(f"Notification ({event}): {embed['title']} - {embed['description']}")
    return {"sent": False, "reason": "no_discord_client"}


# =============================================================================
# Promotion Activities
# =============================================================================


@activity.defn
async def check_promotion_overlap(
    skill_name: str,
    skill_description: str,
    production_skills: list[dict[str, str]],
    llm_client: Any = None,  # Kept for backward compatibility
    allow_overlap: bool = False,
) -> OverlapResult:
    """
    Check if a skill overlaps with production skills before promotion.

    Args:
        skill_name: Name of the skill to promote
        skill_description: Description of the skill
        production_skills: List of production skills
        llm_client: Deprecated, ignored
        allow_overlap: If True, return warning instead of raising

    Returns:
        OverlapResult if no overlap or allow_overlap=True

    Raises:
        SkillOverlapError: If overlap detected and allow_overlap=False
    """
    from .models import SkillOverlapError

    if not production_skills:
        return create_no_overlap_result("No production skills to compare")

    llm = _get_llm_service()
    try:
        overlap_result = await _detect_overlap(llm, skill_description, production_skills)
    finally:
        await llm.close()

    if overlap_result.has_overlap and not allow_overlap:
        raise SkillOverlapError(
            skill_name=skill_name,
            overlapping=overlap_result.overlapping_skills,
            reasoning=overlap_result.reasoning,
        )

    return overlap_result


@activity.defn
async def promote_skill(
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
    fs = _get_file_service()
    try:
        return _promote_skill(fs, skill_path, target_category, skills_root)
    except Exception as e:
        logger.error(f"Failed to promote skill: {e}")
        return {"success": False, "error": str(e)}


@activity.defn
async def await_approval(
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
    CHECKMARK = "\u2705"
    X_MARK = "\u274c"

    try:
        await discord_client.add_reaction(
            channel_id=channel_id, message_id=message_id, emoji=CHECKMARK
        )
        await discord_client.add_reaction(
            channel_id=channel_id, message_id=message_id, emoji=X_MARK
        )

        reaction = await discord_client.await_reaction(
            channel_id=channel_id,
            message_id=message_id,
            valid_emojis=[CHECKMARK, X_MARK],
            timeout_seconds=timeout_seconds,
        )

        if reaction is None:
            return {"approved": False, "rejected": False, "timeout": True}

        return {
            "approved": reaction.get("emoji") == CHECKMARK,
            "rejected": reaction.get("emoji") == X_MARK,
            "timeout": False,
            "reviewer": reaction.get("user_name", "unknown"),
        }

    except Exception as e:
        logger.error(f"Error awaiting approval: {e}")
        return {"approved": False, "rejected": False, "timeout": False, "error": str(e)}


@activity.defn
async def sync_registry(
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
    import json

    fs = _get_file_service()

    try:
        skill_md_path = f"{skill_path}/SKILL.md"
        if not fs.exists(skill_md_path):
            return {"synced": False, "error": "SKILL.md not found"}

        content = fs.read(skill_md_path)

        # Parse frontmatter
        from .core import parse_skill_frontmatter

        metadata = parse_skill_frontmatter(content)

        # Load additional metadata
        metadata_json_path = f"{skill_path}/metadata.json"
        if fs.exists(metadata_json_path):
            extra = json.loads(fs.read(metadata_json_path))
            metadata.update(extra)

        metadata["path"] = skill_path

        result = await registry_client.register_skill(metadata)

        return {"synced": True, "skill_id": result.get("skill_id")}

    except Exception as e:
        logger.error(f"Failed to sync to registry: {e}")
        return {"synced": False, "error": str(e)}


@activity.defn
async def send_promotion_request(
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
    accuracy_pct = f"{metrics.accuracy * 100:.1f}%" if metrics else "N/A"
    tests_info = f"{metrics.tests_passed}/{metrics.tests_total}" if metrics else "N/A"

    embed = {
        "title": f"Promotion Request: {skill_name}",
        "description": "Skill is ready for promotion.\nReact with checkmark to approve or X to reject.",
        "color": 0x9B59B6,
        "fields": [
            {"name": "Accuracy", "value": accuracy_pct, "inline": True},
            {"name": "Tests Passed", "value": tests_info, "inline": True},
            {"name": "Iterations", "value": str(iterations), "inline": True},
        ],
    }

    try:
        response = await discord_client.send_embed(channel_name=channel, embed=embed)
        return {"sent": True, "message_id": response.get("message_id")}
    except Exception as e:
        logger.warning(f"Failed to send promotion request: {e}")
        return {"sent": False, "error": str(e)}


# =============================================================================
# Hardening Activities
# =============================================================================


@activity.defn
async def generate_harder_tests(
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
    # Handle metrics as dict
    accuracy = metrics.accuracy if hasattr(metrics, "accuracy") else metrics.get("accuracy", 0)
    tests_passed = (
        metrics.tests_passed if hasattr(metrics, "tests_passed") else metrics.get("tests_passed", 0)
    )
    tests_total = (
        metrics.tests_total if hasattr(metrics, "tests_total") else metrics.get("tests_total", 0)
    )

    llm = _get_llm_service()
    try:
        return await _generate_harder_tests(
            llm,
            skill_name,
            current_test_cases,
            accuracy,
            tests_passed,
            tests_total,
            failing_tests,
            count,
        )
    finally:
        await llm.close()


@activity.defn
async def revert_to_best_version(
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
    result = _revert_to_version(fs, skill_path, content, test_cases)
    result["reverted_to_iteration"] = iteration

    return result


@activity.defn
async def save_iteration_result(
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
    return _save_iteration_result(
        fs, skill_path, iteration, score, improved, action, metrics, error
    )


@activity.defn
async def load_iteration_history(
    skill_path: str,
) -> list[dict[str, Any]]:
    """
    Load all iteration history files from a skill directory.

    Args:
        skill_path: Path to the skill directory

    Returns:
        List of iteration result dicts
    """
    from .file_service import load_iteration_history as _load_history

    fs = _get_file_service()
    return _load_history(fs, skill_path)
