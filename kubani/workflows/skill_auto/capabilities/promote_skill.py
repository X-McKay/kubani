"""Promote a skill from development to production.

This module provides functions for:
- Loading existing skills metadata
- Checking promotion overlap with production skills
- Sending promotion requests and notifications to Discord
- Awaiting approval reactions
- Syncing to the registry
- Moving skill files to production location
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..models import OverlapResult, SkillOverlapError, create_no_overlap_result
from ..utils import parse_skill_frontmatter

if TYPE_CHECKING:
    from ..protocols import DiscordClient, FileSystem, LLMClient, RegistryClient


logger = logging.getLogger(__name__)


# =============================================================================
# Skill Loading
# =============================================================================


def load_existing_skills(
    fs: "FileSystem",
    skills_path: str,
    include_development: bool = True,
) -> list[dict[str, Any]]:
    """
    Load metadata for all existing skills.

    Scans the skills directory for SKILL.md files and extracts
    metadata from their YAML frontmatter.

    Args:
        fs: File system for operations
        skills_path: Path to skills directory
        include_development: Whether to include _development skills

    Returns:
        List of skill metadata dicts with name, description, path, triggers
    """
    skills = []

    if not fs.exists(skills_path):
        return skills

    for skill_md in fs.list_files(skills_path, "**/SKILL.md"):
        # Skip _development if not included
        if not include_development and "_development" in skill_md:
            continue

        try:
            content = fs.read(skill_md)
            frontmatter = parse_skill_frontmatter(content)

            # Extract skill directory from SKILL.md path
            skill_dir = str(Path(skill_md).parent)

            skills.append(
                {
                    "name": frontmatter.get("name", Path(skill_dir).name),
                    "description": frontmatter.get("description", ""),
                    "path": skill_dir,
                    "triggers": frontmatter.get("triggers", []),
                }
            )
        except Exception as e:
            logger.warning(f"Failed to load skill {skill_md}: {e}")

    return skills


# =============================================================================
# Overlap Detection
# =============================================================================


async def check_promotion_overlap(
    client: "LLMClient",
    skill_name: str,
    skill_description: str,
    production_skills: list[dict[str, Any]],
    allow_overlap: bool = False,
) -> OverlapResult:
    """
    Check if a skill overlaps with production skills before promotion.

    Uses the detect_skill_overlap capability to analyze semantic
    similarity with existing production skills.

    Args:
        client: LLM client for analysis
        skill_name: Name of the skill to promote
        skill_description: Description of the skill
        production_skills: List of production skill metadata dicts
        allow_overlap: If True, return warning instead of raising

    Returns:
        OverlapResult indicating overlap status

    Raises:
        SkillOverlapError: If overlap detected and allow_overlap=False
    """
    from .detect_skill_overlap import detect_skill_overlap

    if not production_skills:
        return create_no_overlap_result("No production skills to compare")

    overlap_result = detect_skill_overlap(
        client,
        description=skill_description,
        existing_skills=production_skills,
    )

    if overlap_result.has_overlap and not allow_overlap:
        raise SkillOverlapError(
            skill_name=skill_name,
            overlapping=overlap_result.overlapping_skills,
            reasoning=overlap_result.reasoning,
        )

    return overlap_result


# =============================================================================
# Discord Notifications
# =============================================================================


async def send_notification(
    discord: "DiscordClient",
    event_type: str,
    channel: str,
    skill_name: str,
    iteration: int | None = None,
    metrics: dict[str, Any] | None = None,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Send workflow notification to Discord.

    Args:
        discord: Discord client for messaging
        event_type: Event type (started, iteration_complete, complete, failed)
        channel: Discord channel name
        skill_name: Name of the skill being developed
        iteration: Current iteration number
        metrics: Evaluation metrics dict
        error: Error message if failed
        result: Final result dict if complete

    Returns:
        Dict with sent status and message_id
    """

    # Helper to get metric value
    def get_metric(name: str, default: Any = None) -> Any:
        if metrics is None:
            return default
        return metrics.get(name, default)

    # Build embed based on event type
    if event_type == "started":
        embed = {
            "title": f"Skill Development Started: {skill_name}",
            "description": "Auto-mode skill development workflow has begun.",
            "color": 0x3498DB,
        }
    elif event_type == "iteration_complete":
        accuracy_pct = f"{get_metric('accuracy', 0) * 100:.1f}%"
        embed = {
            "title": f"Iteration {iteration} Complete: {skill_name}",
            "color": 0x2ECC71,
            "fields": [
                {"name": "Accuracy", "value": accuracy_pct, "inline": True},
                {
                    "name": "Tests Passed",
                    "value": f"{get_metric('tests_passed', 0)}/{get_metric('tests_total', 0)}",
                    "inline": True,
                },
            ],
        }
    elif event_type == "complete":
        status = "succeeded" if result and result.get("success") else "completed"
        embed = {
            "title": f"Skill Development {status.title()}: {skill_name}",
            "color": 0x27AE60 if status == "succeeded" else 0xF39C12,
            "fields": [],
        }
        if result:
            embed["fields"].append(
                {
                    "name": "Iterations",
                    "value": str(result.get("iterations_completed", 0)),
                    "inline": True,
                }
            )
            if result.get("promoted"):
                embed["fields"].append(
                    {"name": "Status", "value": "Promoted to production", "inline": True}
                )
    elif event_type == "failed":
        embed = {
            "title": f"Skill Development Failed: {skill_name}",
            "description": error or "Unknown error",
            "color": 0xE74C3C,
        }
    else:
        embed = {
            "title": f"Skill Event: {skill_name}",
            "description": f"Event: {event_type}",
            "color": 0x95A5A6,
        }

    try:
        response = await discord.send_embed(channel_name=channel, embed=embed)
        return {"sent": True, "message_id": response.get("message_id")}
    except Exception as e:
        logger.warning(f"Failed to send notification: {e}")
        return {"sent": False, "error": str(e)}


async def send_promotion_request(
    discord: "DiscordClient",
    skill_name: str,
    skill_path: str,
    metrics: dict[str, Any] | None,
    iterations: int,
    channel: str,
) -> dict[str, Any]:
    """
    Send a promotion request message to Discord.

    Args:
        discord: Discord client for messaging
        skill_name: Name of the skill
        skill_path: Path to the skill
        metrics: Final evaluation metrics dict
        iterations: Number of iterations completed
        channel: Discord channel name

    Returns:
        Dict with sent status, message_id, and channel_id
    """
    accuracy_pct = f"{metrics.get('accuracy', 0) * 100:.1f}%" if metrics else "N/A"
    tests_info = (
        f"{metrics.get('tests_passed', 0)}/{metrics.get('tests_total', 0)}" if metrics else "N/A"
    )

    embed = {
        "title": f"Promotion Request: {skill_name}",
        "description": ("Skill is ready for promotion.\nReact with ✅ to approve or ❌ to reject."),
        "color": 0x9B59B6,
        "fields": [
            {"name": "Accuracy", "value": accuracy_pct, "inline": True},
            {"name": "Tests Passed", "value": tests_info, "inline": True},
            {"name": "Iterations", "value": str(iterations), "inline": True},
            {"name": "Path", "value": skill_path, "inline": False},
        ],
    }

    try:
        response = await discord.send_embed(channel_name=channel, embed=embed)
        return {
            "sent": True,
            "message_id": response.get("message_id"),
            "channel_id": response.get("channel_id"),
        }
    except Exception as e:
        logger.warning(f"Failed to send promotion request: {e}")
        return {"sent": False, "error": str(e)}


async def await_approval(
    discord: "DiscordClient",
    channel_id: str,
    message_id: str,
    timeout_seconds: int = 3600,
) -> dict[str, Any]:
    """
    Wait for approval reaction on a Discord message.

    Adds checkmark and X reactions, then waits for a user reaction.

    Args:
        discord: Discord client for reactions
        channel_id: Discord channel ID
        message_id: Message ID to watch
        timeout_seconds: How long to wait (default: 1 hour)

    Returns:
        Dict with approved/rejected/timeout status and user_name if available
    """
    CHECKMARK = "\u2705"  # ✅
    X_MARK = "\u274c"  # ❌

    try:
        # Add reaction options
        await discord.add_reaction(channel_id=channel_id, message_id=message_id, emoji=CHECKMARK)
        await discord.add_reaction(channel_id=channel_id, message_id=message_id, emoji=X_MARK)

        # Wait for reaction
        reaction = await discord.await_reaction(
            channel_id=channel_id,
            message_id=message_id,
            valid_emojis=[CHECKMARK, X_MARK],
            timeout_seconds=timeout_seconds,
        )

        if reaction is None:
            return {"approved": False, "rejected": False, "timeout": True}

        is_approved = reaction.get("emoji") == CHECKMARK
        return {
            "approved": is_approved,
            "rejected": not is_approved,
            "timeout": False,
            "user_name": reaction.get("user_name"),
        }
    except Exception as e:
        logger.warning(f"Error waiting for approval: {e}")
        return {"approved": False, "rejected": False, "timeout": True, "error": str(e)}


# =============================================================================
# Registry Sync
# =============================================================================


async def sync_registry(
    fs: "FileSystem",
    skill_path: str,
    registry_client: "RegistryClient",
) -> dict[str, Any]:
    """
    Sync a promoted skill to the registry.

    Reads skill metadata and registers it with the central registry.

    Args:
        fs: File system for reading skill files
        skill_path: Path to the skill directory
        registry_client: Registry client for registration

    Returns:
        Dict with sync status and skill_id if successful
    """
    try:
        skill_md_path = f"{skill_path}/SKILL.md"
        if not fs.exists(skill_md_path):
            return {"synced": False, "error": "SKILL.md not found"}

        content = fs.read(skill_md_path)

        # Parse frontmatter for metadata
        metadata = parse_skill_frontmatter(content)

        # Load additional metadata from JSON if present
        metadata_json_path = f"{skill_path}/metadata.json"
        if fs.exists(metadata_json_path):
            extra = json.loads(fs.read(metadata_json_path))
            metadata.update(extra)

        metadata["path"] = skill_path

        result = await registry_client.sync_skill(skill_path, metadata)

        return {"synced": True, "skill_id": result.get("skill_id")}
    except Exception as e:
        logger.warning(f"Failed to sync skill to registry: {e}")
        return {"synced": False, "error": str(e)}


# =============================================================================
# File Operations
# =============================================================================


def promote_skill(
    fs: "FileSystem",
    skill_path: str,
    target_category: str,
    skills_root: str,
) -> dict[str, Any]:
    """
    Promote a skill from _development to production location.

    Moves the skill directory and updates metadata status.

    Args:
        fs: File system for operations
        skill_path: Path to the development skill directory
        target_category: Target category directory (e.g., "general", "k8s")
        skills_root: Root skills directory (e.g., "kubani/skills")

    Returns:
        Dict with success status, promoted_path, and skill_name
    """
    skill_name = Path(skill_path).name
    target_dir = f"{skills_root}/{target_category}"
    target_path = f"{target_dir}/{skill_name}"

    # Ensure target category exists
    fs.mkdir(target_dir)

    # Move skill directory
    fs.move(skill_path, target_path)

    # Update metadata
    metadata_path = f"{target_path}/metadata.json"
    if fs.exists(metadata_path):
        content = fs.read(metadata_path)
        metadata = json.loads(content)
    else:
        metadata = {}

    metadata["status"] = "production"
    metadata["promoted_at"] = datetime.now().isoformat()
    metadata["category"] = target_category

    fs.write(metadata_path, json.dumps(metadata, indent=2))

    return {
        "success": True,
        "promoted_path": target_path,
        "skill_name": skill_name,
    }


__all__ = [
    # Skill Loading
    "load_existing_skills",
    # Overlap Detection
    "check_promotion_overlap",
    # Discord
    "send_notification",
    "send_promotion_request",
    "await_approval",
    # Registry
    "sync_registry",
    # File Operations
    "promote_skill",
]
