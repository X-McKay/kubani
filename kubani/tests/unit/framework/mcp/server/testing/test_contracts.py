"""Tests for MCP contract definitions."""

from kubani.framework.mcp.server.testing.contracts import MCPContract, ToolContract


class TestToolContract:
    """Tests for ToolContract."""

    def test_basic_tool(self):
        tool = ToolContract(
            name="my_tool",
            parameters={
                "query": {"type": "string", "required": True},
            },
        )
        assert tool.name == "my_tool"
        assert "query" in tool.parameters

    def test_tool_with_description(self):
        tool = ToolContract(
            name="search",
            description="Search for items",
            parameters={
                "query": {"type": "string", "required": True},
                "limit": {"type": "integer", "required": False},
            },
        )
        assert tool.description == "Search for items"

    def test_required_parameters(self):
        tool = ToolContract(
            name="test",
            parameters={
                "required_param": {"type": "string", "required": True},
                "optional_param": {"type": "string", "required": False},
            },
        )
        assert tool.required_parameters == ["required_param"]

    def test_optional_parameters(self):
        tool = ToolContract(
            name="test",
            parameters={
                "required_param": {"type": "string", "required": True},
                "optional_param": {"type": "string", "required": False},
            },
        )
        assert tool.optional_parameters == ["optional_param"]


class TestMCPContract:
    """Tests for MCPContract."""

    def test_basic_contract(self):
        contract = MCPContract(
            server_name="test-server",
            tools=[
                ToolContract(name="tool1", parameters={}),
                ToolContract(name="tool2", parameters={}),
            ],
        )
        assert contract.server_name == "test-server"
        assert len(contract.tools) == 2

    def test_get_tool(self):
        contract = MCPContract(
            server_name="test-server",
            tools=[
                ToolContract(name="find", parameters={}),
                ToolContract(name="search", parameters={}),
            ],
        )
        tool = contract.get_tool("find")
        assert tool is not None
        assert tool.name == "find"

    def test_get_tool_not_found(self):
        contract = MCPContract(
            server_name="test-server",
            tools=[],
        )
        tool = contract.get_tool("nonexistent")
        assert tool is None

    def test_tool_names(self):
        contract = MCPContract(
            server_name="test-server",
            tools=[
                ToolContract(name="a", parameters={}),
                ToolContract(name="b", parameters={}),
                ToolContract(name="c", parameters={}),
            ],
        )
        assert contract.tool_names == ["a", "b", "c"]
