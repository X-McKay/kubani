"""
Standardized error classes for MCP servers.

All MCP servers should use these error classes for consistent
error handling and reporting.
"""

from typing import Any


class MCPError(Exception):
    """Base exception for all MCP errors."""

    code: str = "MCP_ERROR"

    def __init__(
        self,
        message: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for MCP response."""
        return {
            "message": self.message,
            "code": self.code,
            "details": self.details,
        }


class MCPConnectionError(MCPError):
    """Error connecting to a backend service."""

    code: str = "MCP_CONNECTION_ERROR"

    def __init__(
        self,
        message: str,
        server: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details=details)
        self.server = server

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        if self.server:
            d["server"] = self.server
        return d


class MCPTimeoutError(MCPError):
    """Operation timed out."""

    code: str = "MCP_TIMEOUT"

    def __init__(
        self,
        message: str,
        timeout: float | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details=details)
        self.timeout = timeout

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        if self.timeout is not None:
            d["timeout"] = self.timeout
        return d


class MCPValidationError(MCPError):
    """Validation error for tool inputs."""

    code: str = "MCP_VALIDATION_ERROR"

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details=details)
        self.field = field
        self.value = value

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        if self.field:
            d["field"] = self.field
        if self.value is not None:
            d["value"] = self.value
        return d
