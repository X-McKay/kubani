"""Iteration persistence utilities.

Functions for saving and loading iteration history for workflows
that use iterative improvement loops (skill_auto, agent_auto, etc.).
"""

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kubani.framework.protocols import FileSystemProtocol

logger = logging.getLogger(__name__)


def save_iteration_result(
    fs: "FileSystemProtocol",
    output_path: str,
    iteration: int,
    score: float,
    improved: bool,
    action: str,
    metrics: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """
    Save iteration result to a JSON file for auditing.

    Creates iteration_N.json in the specified directory.

    Args:
        fs: File system for operations
        output_path: Path to save the iteration file
        iteration: Iteration number
        score: Computed score
        improved: Whether this iteration improved
        action: Action taken (continue, stop_success, etc.)
        metrics: Optional metrics dict
        error: Optional error message

    Returns:
        Dict with save status and file path

    Example:
        >>> save_iteration_result(fs, "/path/to/skill", 1, 0.85, True, "continue")
        {'saved': True, 'file': '/path/to/skill/iteration_1.json'}
    """
    iteration_file = f"{output_path}/iteration_{iteration}.json"

    data = {
        "iteration": iteration,
        "score": score,
        "improved": improved,
        "action": action,
        "error": error,
        "saved_at": datetime.now().isoformat(),
    }

    if metrics:
        data["metrics"] = metrics

    fs.write(iteration_file, json.dumps(data, indent=2))

    return {
        "saved": True,
        "file": iteration_file,
    }


def load_iteration_history(
    fs: "FileSystemProtocol",
    output_path: str,
) -> list[dict[str, Any]]:
    """
    Load all iteration history files from a directory.

    Args:
        fs: File system for operations
        output_path: Path to the directory containing iteration files

    Returns:
        List of iteration result dicts, sorted by iteration number

    Example:
        >>> history = load_iteration_history(fs, "/path/to/skill")
        >>> len(history)
        3
        >>> history[0]['iteration']
        1
    """
    history = []

    if not fs.exists(output_path):
        return history

    for iteration_file in fs.list_files(output_path, "iteration_*.json"):
        try:
            content = fs.read(iteration_file)
            data = json.loads(content)
            history.append(data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to load {iteration_file}: {e}")

    # Sort by iteration number
    history.sort(key=lambda x: x.get("iteration", 0))

    return history


__all__ = [
    "save_iteration_result",
    "load_iteration_history",
]
