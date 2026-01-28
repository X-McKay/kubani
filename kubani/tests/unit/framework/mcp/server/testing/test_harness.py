"""Tests for MCP test harness."""

import pytest

from kubani.framework.mcp.server import MCPServerBase
from kubani.framework.mcp.server.testing import (
    MCPContract,
    MCPTestHarness,
    ToolContract,
)


class MockServer(MCPServerBase):
    """Mock server for testing the harness."""

    name = "mock-server"
    description = "A mock server for testing"

    async def connect_backend(self) -> None:
        pass

    async def disconnect_backend(self) -> None:
        pass

    def register_tools(self, mcp) -> None:
        @mcp.tool()
        async def echo(message: str) -> dict:
            """Echo the message back."""
            return {"echo": message}

        @mcp.tool()
        async def add(a: int, b: int) -> dict:
            """Add two numbers."""
            return {"result": a + b}


MOCK_CONTRACT = MCPContract(
    server_name="mock-server",
    tools=[
        ToolContract(
            name="echo",
            parameters={"message": {"type": "string", "required": True}},
        ),
        ToolContract(
            name="add",
            parameters={
                "a": {"type": "integer", "required": True},
                "b": {"type": "integer", "required": True},
            },
        ),
        ToolContract(name="health", parameters={}),
    ],
)


class TestMCPTestHarness:
    """Tests for MCPTestHarness."""

    @pytest.mark.asyncio
    async def test_validate_tools_exist(self):
        server = MockServer()
        harness = MCPTestHarness(server, MOCK_CONTRACT)

        result = await harness.validate_tools_exist()
        assert result.passed
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_tools_missing(self):
        server = MockServer()
        contract_with_missing = MCPContract(
            server_name="mock-server",
            tools=[
                ToolContract(name="echo", parameters={}),
                ToolContract(name="nonexistent_tool", parameters={}),
            ],
        )
        harness = MCPTestHarness(server, contract_with_missing)

        result = await harness.validate_tools_exist()
        assert not result.passed
        assert "nonexistent_tool" in str(result.errors)

    @pytest.mark.asyncio
    async def test_call_tool(self):
        server = MockServer()
        harness = MCPTestHarness(server, MOCK_CONTRACT)

        await harness.setup()
        result = await harness.call_tool("echo", message="hello")
        await harness.teardown()

        assert result == {"echo": "hello"}

    @pytest.mark.asyncio
    async def test_call_tool_with_multiple_args(self):
        server = MockServer()
        harness = MCPTestHarness(server, MOCK_CONTRACT)

        await harness.setup()
        result = await harness.call_tool("add", a=2, b=3)
        await harness.teardown()

        assert result == {"result": 5}

    @pytest.mark.asyncio
    async def test_validation_result_to_dict(self):
        server = MockServer()
        harness = MCPTestHarness(server, MOCK_CONTRACT)

        result = await harness.validate_tools_exist()
        d = result.to_dict()

        assert "passed" in d
        assert "errors" in d
        assert d["passed"] is True
