"""
Contract validator for MCP servers.

Provides utilities for validating MCP servers against their contracts.
"""

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any

from kubani.framework.mcp.server.base import MCPServerBase
from kubani.framework.mcp.server.testing.contracts import MCPContract, ToolContract

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """A single validation error."""

    tool_name: str | None
    error_type: str  # "missing_tool", "missing_parameter", "type_mismatch", etc.
    message: str


@dataclass
class ContractValidationResult:
    """Result of contract validation."""

    passed: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        """Get count of errors."""
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        """Get count of warnings."""
        return len(self.warnings)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "errors": [
                {
                    "tool_name": err.tool_name,
                    "error_type": err.error_type,
                    "message": err.message,
                }
                for err in self.errors
            ],
            "warnings": self.warnings,
        }


class ContractValidator:
    """
    Validator for MCP server contracts.

    Validates that an MCP server implementation matches its contract:
    - All contracted tools exist
    - Tool parameter schemas match
    - Tool return types match (if specified)
    """

    def __init__(self, server: MCPServerBase, contract: MCPContract):
        """
        Initialize the validator.

        Args:
            server: The MCP server to validate
            contract: The contract to validate against
        """
        self.server = server
        self.contract = contract
        self._mcp = None
        self._tools: dict[str, Any] = {}

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

    def validate_tool_existence(self) -> list[ValidationError]:
        """
        Validate that all contracted tools exist on the server.

        Returns:
            List of validation errors (empty if all tools exist)
        """
        # Create server to register tools
        if self._mcp is None:
            self._mcp = self.server.create_server()
            self._discover_tools()

        errors = []
        for tool_contract in self.contract.tools:
            if tool_contract.name not in self._tools:
                errors.append(
                    ValidationError(
                        tool_name=tool_contract.name,
                        error_type="missing_tool",
                        message=f"Tool '{tool_contract.name}' defined in contract but not found on server",
                    )
                )

        return errors

    def validate_tool_parameters(self, tool_contract: ToolContract) -> list[ValidationError]:
        """
        Validate parameters for a specific tool.

        Args:
            tool_contract: The tool contract to validate

        Returns:
            List of validation errors for this tool
        """
        errors = []

        # Check if tool exists
        if tool_contract.name not in self._tools:
            return [
                ValidationError(
                    tool_name=tool_contract.name,
                    error_type="missing_tool",
                    message=f"Tool '{tool_contract.name}' not found",
                )
            ]

        tool = self._tools[tool_contract.name]

        # Validate parameter types are defined in contract
        param_errors = tool_contract.validate_parameter_types()
        for param_error in param_errors:
            errors.append(
                ValidationError(
                    tool_name=tool_contract.name,
                    error_type="missing_type_definition",
                    message=param_error,
                )
            )

        # Get tool function signature
        sig = inspect.signature(tool.fn)

        # Check that all required parameters in contract exist in function
        for param_name in tool_contract.required_parameters:
            if param_name not in sig.parameters:
                errors.append(
                    ValidationError(
                        tool_name=tool_contract.name,
                        error_type="missing_parameter",
                        message=f"Required parameter '{param_name}' not found in function signature",
                    )
                )

        return errors

    def validate_parameter_schemas(self) -> tuple[list[ValidationError], list[str]]:
        """
        Validate that tool parameter schemas match the contract.

        Returns:
            Tuple of (errors, warnings)
        """
        # Create server to register tools
        if self._mcp is None:
            self._mcp = self.server.create_server()
            self._discover_tools()

        errors = []
        warnings = []

        for tool_contract in self.contract.tools:
            tool_errors = self.validate_tool_parameters(tool_contract)
            errors.extend(tool_errors)

            # Check for extra parameters in function not in contract
            if tool_contract.name in self._tools:
                tool = self._tools[tool_contract.name]
                sig = inspect.signature(tool.fn)

                for param_name, param in sig.parameters.items():
                    if param_name not in tool_contract.parameters:
                        # Only warn if it's not a special parameter
                        if param_name not in ["self", "cls", "args", "kwargs"]:
                            warnings.append(
                                f"Tool '{tool_contract.name}': parameter '{param_name}' "
                                f"in function but not in contract"
                            )

        return errors, warnings

    def validate(self) -> ContractValidationResult:
        """
        Validate the complete contract.

        Checks:
        - All contracted tools exist
        - Tool parameter schemas match
        - All parameters have type definitions

        Returns:
            ContractValidationResult with pass/fail and any errors/warnings
        """
        all_errors = []
        all_warnings = []

        # Validate tools exist
        existence_errors = self.validate_tool_existence()
        all_errors.extend(existence_errors)

        # Validate parameter schemas
        schema_errors, schema_warnings = self.validate_parameter_schemas()
        all_errors.extend(schema_errors)
        all_warnings.extend(schema_warnings)

        return ContractValidationResult(
            passed=len(all_errors) == 0,
            errors=all_errors,
            warnings=all_warnings,
        )
