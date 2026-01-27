"""
Test harness for MCP servers.

Provides utilities for testing MCP servers against their contracts.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from kubani.framework.mcp.server.base import MCPServerBase
from kubani.framework.mcp.server.testing.contracts import MCPContract

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class MCPTestHarness:
    """
    Test harness for MCP servers.

    Provides utilities for:
    - Validating servers against contracts
    - Calling tools in tests
    - Managing server lifecycle

    Usage:
        server = MyMCPServer()
        harness = MCPTestHarness(server, MY_CONTRACT)

        # Validate contract
        result = await harness.validate_tools_exist()
        assert result.passed

        # Call tools
        await harness.setup()
        result = await harness.call_tool("my_tool", arg="value")
        await harness.teardown()
    """

    def __init__(self, server: MCPServerBase, contract: MCPContract):
        """
        Initialize the test harness.

        Args:
            server: The MCP server to test
            contract: The contract to validate against
        """
        self.server = server
        self.contract = contract
        self._mcp = None
        self._tools: dict[str, Any] = {}

    async def setup(self) -> None:
        """Set up the harness for testing (connect to backend)."""
        await self.server.startup()
        self._mcp = self.server.create_server()
        self._discover_tools()

    async def teardown(self) -> None:
        """Tear down the harness after testing."""
        await self.server.shutdown()

    def _discover_tools(self) -> None:
        """Discover tools registered on the MCP server."""
        if self._mcp is None:
            return

        # Access the tool manager to find registered tools
        # FastMCP stores tools in _tool_manager
        if hasattr(self._mcp, "_tool_manager"):
            manager = self._mcp._tool_manager
            if hasattr(manager, "_tools"):
                self._tools = dict(manager._tools)

    async def validate_tools_exist(self) -> ValidationResult:
        """
        Validate that all contracted tools exist on the server.

        Returns:
            ValidationResult with pass/fail and any errors
        """
        # Create server to register tools (don't need to connect)
        mcp = self.server.create_server()
        self._mcp = mcp
        self._discover_tools()

        errors = []
        for tool_contract in self.contract.tools:
            if tool_contract.name not in self._tools:
                errors.append(f"Missing tool: {tool_contract.name}")

        return ValidationResult(
            passed=len(errors) == 0,
            errors=errors,
        )

    async def call_tool(self, name: str, **kwargs: Any) -> Any:
        """
        Call a tool on the server.

        Args:
            name: Tool name
            **kwargs: Tool arguments

        Returns:
            Tool result

        Raises:
            KeyError: If tool not found
        """
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")

        tool = self._tools[name]
        # The tool is an async function, call it with the kwargs
        return await tool.fn(**kwargs)
