# kubani/framework/mcp/server/tests/test_errors.py
"""Tests for MCP error classes."""

from kubani.framework.mcp.server.errors import (
    MCPBackendError,
    MCPConnectionError,
    MCPError,
    MCPErrorHandler,
    MCPTimeoutError,
    MCPValidationError,
)


class TestMCPError:
    """Tests for base MCPError."""

    def test_basic_error(self):
        error = MCPError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.code == "MCP_ERROR"

    def test_error_with_details(self):
        error = MCPError("Failed", details={"key": "value"})
        assert error.details == {"key": "value"}

    def test_error_to_dict(self):
        error = MCPError("Failed", code="CUSTOM_CODE", details={"x": 1})
        d = error.to_dict()
        assert d["message"] == "Failed"
        assert d["code"] == "CUSTOM_CODE"
        assert d["details"] == {"x": 1}


class TestMCPConnectionError:
    """Tests for MCPConnectionError."""

    def test_connection_error(self):
        error = MCPConnectionError("Cannot connect to backend", server="qdrant")
        assert "Cannot connect to backend" in str(error)
        assert error.server == "qdrant"
        assert error.code == "MCP_CONNECTION_ERROR"

    def test_connection_error_to_dict(self):
        error = MCPConnectionError("Failed", server="temporal")
        d = error.to_dict()
        assert d["server"] == "temporal"


class TestMCPTimeoutError:
    """Tests for MCPTimeoutError."""

    def test_timeout_error(self):
        error = MCPTimeoutError("Operation timed out", timeout=30.0)
        assert error.timeout == 30.0
        assert error.code == "MCP_TIMEOUT"

    def test_timeout_error_to_dict(self):
        error = MCPTimeoutError("Slow", timeout=60.0)
        d = error.to_dict()
        assert d["timeout"] == 60.0


class TestMCPValidationError:
    """Tests for MCPValidationError."""

    def test_validation_error(self):
        error = MCPValidationError("Invalid input", field="name", value="")
        assert error.field == "name"
        assert error.value == ""
        assert error.code == "MCP_VALIDATION_ERROR"

    def test_validation_error_to_dict(self):
        error = MCPValidationError("Bad", field="age", value=-1)
        d = error.to_dict()
        assert d["field"] == "age"
        assert d["value"] == -1


class TestMCPBackendError:
    """Tests for MCPBackendError."""

    def test_backend_error(self):
        error = MCPBackendError("Backend failed", backend="discord_api")
        assert "Backend failed" in str(error)
        assert error.backend == "discord_api"
        assert error.code == "MCP_BACKEND_ERROR"

    def test_backend_error_to_dict(self):
        error = MCPBackendError("Failed", backend="redis")
        d = error.to_dict()
        assert d["backend"] == "redis"


class TestMCPErrorHandler:
    """Tests for MCPErrorHandler."""

    def test_initialization(self):
        handler = MCPErrorHandler(tool_name="test_tool")
        assert handler.tool_name == "test_tool"

    def test_handle_validation_error(self):
        handler = MCPErrorHandler(tool_name="test_tool")
        error = ValueError("Invalid value")

        response = handler.handle_validation_error(error, field="name", value="")

        assert response["error_type"] == "validation_error"
        assert response["tool_name"] == "test_tool"
        assert response["details"]["field"] == "name"
        assert "timestamp" in response

    def test_handle_backend_error(self):
        handler = MCPErrorHandler(tool_name="test_tool")
        error = ConnectionError("Cannot connect")

        response = handler.handle_backend_error(error, backend="discord_api")

        assert response["error_type"] == "backend_error"
        assert response["tool_name"] == "test_tool"
        assert response["details"]["backend"] == "discord_api"

    def test_handle_timeout_error(self):
        handler = MCPErrorHandler(tool_name="test_tool")
        error = TimeoutError("Timed out")

        response = handler.handle_timeout_error(error, operation="send_message", timeout=30.0)

        assert response["error_type"] == "timeout_error"
        assert response["tool_name"] == "test_tool"
        assert response["details"]["operation"] == "send_message"
        assert response["details"]["timeout_seconds"] == 30.0

    def test_handle_internal_error(self):
        handler = MCPErrorHandler(tool_name="test_tool")
        error = RuntimeError("Unexpected error")

        response = handler.handle_internal_error(error, context="processing")

        assert response["error_type"] == "internal_error"
        assert response["tool_name"] == "test_tool"
        assert response["details"]["context"] == "processing"

    def test_handle_error_with_validation_error(self):
        handler = MCPErrorHandler(tool_name="test_tool")
        error = MCPValidationError("Invalid", field="name", value="")

        response = handler.handle_error(error)

        assert response["error_type"] == "validation_error"
        assert response["details"]["field"] == "name"

    def test_handle_error_with_backend_error(self):
        handler = MCPErrorHandler(tool_name="test_tool")
        error = MCPBackendError("Failed", backend="redis")

        response = handler.handle_error(error)

        assert response["error_type"] == "backend_error"
        assert response["details"]["backend"] == "redis"

    def test_handle_error_with_timeout_error(self):
        handler = MCPErrorHandler(tool_name="test_tool")
        error = MCPTimeoutError("Timeout", timeout=30.0)

        response = handler.handle_error(error)

        assert response["error_type"] == "timeout_error"

    def test_handle_error_with_connection_error(self):
        handler = MCPErrorHandler(tool_name="test_tool")
        error = MCPConnectionError("Cannot connect", server="qdrant")

        response = handler.handle_error(error)

        assert response["error_type"] == "backend_error"
        assert response["details"]["backend"] == "qdrant"

    def test_handle_error_with_generic_exception(self):
        handler = MCPErrorHandler(tool_name="test_tool")
        error = ValueError("Some error")

        response = handler.handle_error(error)

        assert response["error_type"] == "internal_error"

