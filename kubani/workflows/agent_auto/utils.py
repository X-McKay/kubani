"""Shared utility functions for the Agent Auto workflow.

This module contains agent-specific pure functions for:
- Agent file operations (write, load config/prompt)

Common utilities (DefaultFileSystem, LLM parsing, iteration persistence)
are imported from kubani.framework.utils.
"""

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

import yaml

# Re-export common utilities from framework for backwards compatibility
from kubani.framework.utils import (
    DefaultFileSystem,
    clean_llm_output,
    clean_markdown_output,
    clean_yaml_output,
    extract_json,
    load_iteration_history,
    save_iteration_result,
)

if TYPE_CHECKING:
    from kubani.framework.protocols import FileSystemProtocol


# =============================================================================
# Agent File Operations
# =============================================================================


def write_agent_files(
    fs: "FileSystemProtocol",
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


def load_agent_config(fs: "FileSystemProtocol", agent_path: str) -> dict[str, Any]:
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


def load_agent_prompt(fs: "FileSystemProtocol", agent_path: str) -> str:
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
    # Re-exported from framework
    "DefaultFileSystem",
    "extract_json",
    "clean_yaml_output",
    "clean_markdown_output",
    "clean_llm_output",
    "save_iteration_result",
    "load_iteration_history",
    # Agent-specific operations
    "write_agent_files",
    "load_agent_config",
    "load_agent_prompt",
]
