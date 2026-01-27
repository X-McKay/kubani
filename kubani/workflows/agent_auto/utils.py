"""Shared utility functions for the Agent Auto workflow.

This module contains:
- File system implementation
- Agent file operations
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from .protocols import FileSystem

# =============================================================================
# File System Implementation
# =============================================================================


class DefaultFileSystem:
    """Default filesystem implementation using standard library.

    Provides a concrete implementation of the FileSystem protocol
    for use in production code.
    """

    def read(self, path: str) -> str:
        """Read file content as string."""
        return Path(path).read_text()

    def write(self, path: str, content: str) -> None:
        """Write content to file, creating parent directories if needed."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        return Path(path).exists()

    def mkdir(self, path: str) -> None:
        """Create directory and parents."""
        Path(path).mkdir(parents=True, exist_ok=True)

    def list_files(self, path: str, pattern: str) -> list[str]:
        """List files matching glob pattern in path."""
        p = Path(path)
        if not p.exists():
            return []
        return [str(f) for f in p.glob(pattern)]

    def copy(self, src: str, dst: str) -> None:
        """Copy file from src to dst."""
        shutil.copy2(src, dst)

    def move(self, src: str, dst: str) -> None:
        """Move file or directory from src to dst."""
        shutil.move(src, dst)

    def list_dir(self, path: str) -> list[str]:
        """List directory contents."""
        p = Path(path)
        if not p.exists():
            return []
        return [f.name for f in p.iterdir()]

    def delete(self, path: str) -> None:
        """Delete file or directory."""
        p = Path(path)
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()


# =============================================================================
# Agent File Operations
# =============================================================================


def write_agent_files(
    fs: "FileSystem",
    agent_name: str,
    prompt_content: str,
    config_content: str,
    output_dir: str,
) -> dict[str, str]:
    """
    Write agent files to disk.

    Creates:
    - prompt.md with the agent prompt
    - config.yaml with agent configuration
    - metadata.json with agent metadata

    Args:
        fs: File system for operations
        agent_name: Name of the agent
        prompt_content: Content for prompt.md
        config_content: Content for config.yaml
        output_dir: Directory to write to

    Returns:
        Dict with path and created file paths
    """
    agent_dir = f"{output_dir}/{agent_name}"

    # Ensure directory exists
    fs.mkdir(agent_dir)

    # Write prompt.md
    prompt_path = f"{agent_dir}/prompt.md"
    fs.write(prompt_path, prompt_content)

    # Write config.yaml
    config_path = f"{agent_dir}/config.yaml"
    fs.write(config_path, config_content)

    # Write metadata.json
    metadata = {
        "name": agent_name,
        "version": "0.1.0",
        "status": "development",
        "created_at": datetime.now().isoformat(),
    }
    metadata_path = f"{agent_dir}/metadata.json"
    fs.write(metadata_path, json.dumps(metadata, indent=2))

    return {
        "path": agent_dir,
        "prompt_path": prompt_path,
        "config_path": config_path,
        "metadata_path": metadata_path,
    }


def load_agent_config(fs: "FileSystem", agent_path: str) -> dict[str, Any]:
    """
    Load agent configuration from config.yaml.

    Args:
        fs: File system for operations
        agent_path: Path to the agent directory

    Returns:
        Parsed configuration dict, or empty dict if not found
    """
    config_path = f"{agent_path}/config.yaml"
    if not fs.exists(config_path):
        return {}

    content = fs.read(config_path)
    return yaml.safe_load(content) or {}


def load_agent_prompt(fs: "FileSystem", agent_path: str) -> str:
    """
    Load agent prompt from prompt.md.

    Args:
        fs: File system for operations
        agent_path: Path to the agent directory

    Returns:
        Prompt content, or empty string if not found
    """
    prompt_path = f"{agent_path}/prompt.md"
    if not fs.exists(prompt_path):
        return ""

    return fs.read(prompt_path)


__all__ = [
    # File System
    "DefaultFileSystem",
    # Agent File Operations
    "write_agent_files",
    "load_agent_config",
    "load_agent_prompt",
]
