# kubani/framework/mcp/server/tests/test_errors.py
"""Tests for MCP error classes."""

from kubani.framework.mcp.server.errors import (
    MCPConnectionError,
    MCPError,
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
