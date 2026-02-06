"""
Standardized error classes for MCP servers.

All MCP servers should use these error classes for consistent
error handling and reporting.
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


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


class MCPBackendError(MCPError):
    """Error from a backend service."""

    code: str = "MCP_BACKEND_ERROR"

    def __init__(
        self,
        message: str,
        backend: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details=details)
        self.backend = backend

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        if self.backend:
            d["backend"] = self.backend
        return d


class MCPErrorHandler:
    """
    Standardized error handler for MCP servers.

    Provides consistent error response formatting across all error types.

    Usage:
        handler = MCPErrorHandler(tool_name="send_message")

        try:
            # ... tool logic ...
        except ValidationError as e:
            return handler.handle_validation_error(e)
        except BackendError as e:
            return handler.handle_backend_error(e, "discord_api")
        except TimeoutError as e:
            return handler.handle_timeout_error(e, "send_message")
    """

    def __init__(self, tool_name: str):
        """
        Initialize error handler.

        Args:
            tool_name: Name of the tool being executed
        """
        self.tool_name = tool_name

    def _create_error_response(
        self,
        error_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create standardized error response.

        Args:
            error_type: Type of error (validation_error, backend_error, etc.)
            message: Human-readable error message
            details: Additional error context

        Returns:
            Standardized error response dictionary
        """
        return {
            "error_type": error_type,
            "message": message,
            "details": details or {},
            "tool_name": self.tool_name,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def handle_validation_error(
        self,
        error: Exception,
        field: str | None = None,
        value: Any = None,
    ) -> dict[str, Any]:
        """
        Handle validation errors.

        Args:
            error: The validation error
            field: Field that failed validation
            value: Invalid value

        Returns:
            Standardized error response
        """
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)

        logger.warning(f"Validation error in {self.tool_name}: {error}")

        return self._create_error_response(
            error_type="validation_error",
            message=str(error),
            details=details,
        )

    def handle_backend_error(
        self,
        error: Exception,
        backend: str,
        operation: str | None = None,
    ) -> dict[str, Any]:
        """
        Handle backend service errors.

        Args:
            error: The backend error
            backend: Name of the backend service
            operation: Operation that failed

        Returns:
            Standardized error response
        """
        details = {
            "backend": backend,
        }
        if operation:
            details["operation"] = operation

        logger.error(f"Backend error in {self.tool_name} ({backend}): {error}")

        return self._create_error_response(
            error_type="backend_error",
            message=f"Backend service error: {str(error)}",
            details=details,
        )

    def handle_timeout_error(
        self,
        error: Exception,
        operation: str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        Handle timeout errors.

        Args:
            error: The timeout error
            operation: Operation that timed out
            timeout: Timeout value in seconds

        Returns:
            Standardized error response
        """
        details = {
            "operation": operation,
        }
        if timeout is not None:
            details["timeout_seconds"] = timeout

        logger.warning(f"Timeout in {self.tool_name} ({operation}): {error}")

        return self._create_error_response(
            error_type="timeout_error",
            message=f"Operation timed out: {operation}",
            details=details,
        )

    def handle_internal_error(
        self,
        error: Exception,
        context: str | None = None,
    ) -> dict[str, Any]:
        """
        Handle internal/unexpected errors.

        Args:
            error: The internal error
            context: Additional context about where the error occurred

        Returns:
            Standardized error response
        """
        details = {}
        if context:
            details["context"] = context

        logger.exception(f"Internal error in {self.tool_name}: {error}")

        return self._create_error_response(
            error_type="internal_error",
            message="An internal error occurred",
            details=details,
        )

    def handle_error(self, error: Exception) -> dict[str, Any]:
        """
        Handle any error with automatic type detection.

        Args:
            error: The error to handle

        Returns:
            Standardized error response
        """
        if isinstance(error, MCPValidationError):
            return self.handle_validation_error(
                error,
                field=error.field,
                value=error.value,
            )
        elif isinstance(error, MCPBackendError):
            return self.handle_backend_error(
                error,
                backend=error.backend or "unknown",
            )
        elif isinstance(error, MCPTimeoutError):
            return self.handle_timeout_error(
                error,
                operation=self.tool_name,
                timeout=error.timeout,
            )
        elif isinstance(error, MCPConnectionError):
            return self.handle_backend_error(
                error,
                backend=error.server or "unknown",
                operation="connect",
            )
        elif isinstance(error, MCPError):
            return self._create_error_response(
                error_type=error.code.lower(),
                message=error.message,
                details=error.details,
            )
        else:
            return self.handle_internal_error(error)

