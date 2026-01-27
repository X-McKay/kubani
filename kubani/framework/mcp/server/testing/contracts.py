"""
Contract definitions for MCP server testing.

Contracts define the expected interface of an MCP server, including
what tools it should provide and their parameter schemas.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContract:
    """
    Contract for an MCP tool.

    Defines the expected name, parameters, and behavior of a tool.
    """

    name: str
    parameters: dict[str, dict[str, Any]] = field(default_factory=dict)
    description: str | None = None

    @property
    def required_parameters(self) -> list[str]:
        """Get list of required parameter names."""
        return [name for name, spec in self.parameters.items() if spec.get("required", False)]

    @property
    def optional_parameters(self) -> list[str]:
        """Get list of optional parameter names."""
        return [name for name, spec in self.parameters.items() if not spec.get("required", False)]


@dataclass
class MCPContract:
    """
    Contract for an MCP server.

    Defines the expected tools and capabilities of the server.
    """

    server_name: str
    tools: list[ToolContract] = field(default_factory=list)
    description: str | None = None

    def get_tool(self, name: str) -> ToolContract | None:
        """Get a tool contract by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    @property
    def tool_names(self) -> list[str]:
        """Get list of all tool names."""
        return [tool.name for tool in self.tools]
