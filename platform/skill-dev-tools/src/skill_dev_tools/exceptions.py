"""Agent framework exceptions."""

from __future__ import annotations


class FrameworkError(Exception):
    """Base exception for agent framework."""

    pass


class TraceBackendError(FrameworkError):
    """Trace backend errors."""

    pass


class ExecutorError(FrameworkError):
    """Skill/agent executor errors."""

    pass


class ConfigError(FrameworkError):
    """Framework configuration errors."""

    pass
