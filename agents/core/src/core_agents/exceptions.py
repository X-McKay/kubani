"""Kubani exception hierarchy for structured error handling."""

from __future__ import annotations

from typing import Any


class KubaniError(Exception):
    """Base exception for all Kubani errors."""

    def __init__(
        self,
        message: str,
        *,
        cause: Exception | None = None,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.cause = cause
        self.context = context or {}

    def __str__(self) -> str:
        if self.cause:
            return f"{self.message} (caused by: {self.cause})"
        return self.message


class ConfigurationError(KubaniError):
    """Configuration-related errors (missing keys, invalid values, etc.)."""

    pass


class MCPError(KubaniError):
    """MCP server communication errors."""

    def __init__(
        self,
        message: str,
        *,
        server: str | None = None,
        tool: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.server = server
        self.tool = tool


class MCPConnectionError(MCPError):
    """MCP server connection failures."""

    pass


class MCPToolError(MCPError):
    """MCP tool execution errors."""

    pass


class SkillError(KubaniError):
    """Skill-related errors."""

    def __init__(
        self,
        message: str,
        *,
        skill_name: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.skill_name = skill_name


class SkillNotFoundError(SkillError):
    """Skill not found in registry or filesystem."""

    pass


class SkillExecutionError(SkillError):
    """Skill execution failures."""

    pass


class SkillValidationError(SkillError):
    """Skill validation failures (invalid SKILL.md, missing fields, etc.)."""

    pass


class AgentError(KubaniError):
    """Agent-related errors."""

    def __init__(
        self,
        message: str,
        *,
        agent_name: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.agent_name = agent_name


class AgentInitializationError(AgentError):
    """Agent failed to initialize."""

    pass


class AgentExecutionError(AgentError):
    """Agent execution failures."""

    pass


class MemoryError(KubaniError):
    """Memory system errors (Qdrant, Neo4j, Redis)."""

    def __init__(
        self,
        message: str,
        *,
        backend: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.backend = backend


class TemporalError(KubaniError):
    """Temporal workflow errors."""

    def __init__(
        self,
        message: str,
        *,
        workflow_id: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.workflow_id = workflow_id


class LLMError(KubaniError):
    """LLM provider errors."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.provider = provider
        self.model = model


class LLMRateLimitError(LLMError):
    """LLM rate limit hit."""

    pass


class LLMTimeoutError(LLMError):
    """LLM request timeout."""

    pass


class RegistryError(KubaniError):
    """Registry service errors."""

    pass


# Convenience function for migration
def wrap_exception(exc: Exception, error_class: type[KubaniError], message: str) -> KubaniError:
    """Wrap a generic exception in a Kubani error type."""
    return error_class(message, cause=exc, context={"original_type": type(exc).__name__})
