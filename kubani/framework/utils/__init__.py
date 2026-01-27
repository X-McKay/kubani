"""Shared utility functions for Kubani workflows.

This module provides common utilities used across skill_auto, agent_auto,
and syndicates:

- File system operations (DefaultFileSystem)
- LLM output parsing (JSON/YAML/Markdown extraction)
- Iteration persistence (saving/loading iteration history)
"""

from .filesystem import DefaultFileSystem
from .iteration import (
    load_iteration_history,
    save_iteration_result,
)
from .llm_parsing import (
    clean_llm_output,
    clean_markdown_output,
    clean_yaml_output,
    extract_json,
)

__all__ = [
    # File System
    "DefaultFileSystem",
    # LLM Output Parsing
    "extract_json",
    "clean_yaml_output",
    "clean_markdown_output",
    "clean_llm_output",
    # Iteration Persistence
    "save_iteration_result",
    "load_iteration_history",
]
