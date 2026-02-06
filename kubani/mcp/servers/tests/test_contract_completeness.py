"""
Property-based tests for MCP server contract completeness.

**Feature: mcp-infrastructure-improvements, Property 3: Contract Completeness**

Tests that all MCP servers implement their contracted tools with matching signatures.
"""

import pytest
from hypothesis import given, settings, strategies as st

from kubani.framework.mcp.server.testing import ContractValidator
from kubani.framework.mcp.server.base import MCPServerBase
from kubani.mcp.servers.tests.contracts import ALL_CONTRACTS


class ServerWrapper(MCPServerBase):
    """
    Wrapper to adapt functional MCP servers to the MCPServerBase interface.

    This allows us to test servers that use the create_server() pattern.
    """

    def __init__(self, name: str, description: str, create_fn):
        """Initialize wrapper with server creation function."""
        self.name = name
        self.description = description
        self._create_fn = create_fn
        super().__init__()

    async def connect_backend(self):
        """No-op for testing - backends not needed for contract validation."""
        pass

    async def disconnect_backend(self):
        """No-op for testing."""
        pass

    def register_tools(self, mcp):
        """No-op - tools are registered by create_fn."""
        pass

    def create_server(self):
        """Use the server's create_server function."""
        return self._create_fn()


def get_server_instance(server_name: str) -> MCPServerBase:
    """
    Get a wrapped instance of an MCP server by name.

    Args:
        server_name: Name of the server (discord, temporal, qdrant, memory, skills)

    Returns:
        Server instance wrapped in ServerWrapper

    Raises:
        ValueError: If server name is unknown
    """
    if server_name == "discord":
        from discord_mcp.server import create_server

        return ServerWrapper("discord-mcp", "Discord MCP Server", create_server)
    elif server_name == "temporal":
        from temporal_mcp.server import create_server

        return ServerWrapper("temporal-mcp", "Temporal MCP Server", create_server)
    elif server_name == "qdrant":
        from qdrant_mcp.server import create_server

        return ServerWrapper("qdrant-mcp", "Qdrant MCP Server", create_server)
    elif server_name == "memory":
        from memory_mcp.server import create_server

        return ServerWrapper("memory-mcp", "Memory MCP Server", create_server)
    elif server_name == "skills":
        from skills_mcp.server import create_server

        return ServerWrapper("skills-mcp", "Skills MCP Server", create_server)
    else:
        raise ValueError(f"Unknown server: {server_name}")


@pytest.mark.parametrize("server_name", list(ALL_CONTRACTS.keys()))
def test_contract_tools_exist(server_name: str):
    """
    Test that all contracted tools exist on the server.

    **Validates: Requirements 2.2**

    For any MCP server with a defined contract, the server should implement
    all tools specified in the contract.
    """
    contract = ALL_CONTRACTS[server_name]
    server = get_server_instance(server_name)

    validator = ContractValidator(server, contract)
    errors = validator.validate_tool_existence()

    assert len(errors) == 0, f"Missing tools in {server_name}: {[e.message for e in errors]}"


@pytest.mark.parametrize("server_name", list(ALL_CONTRACTS.keys()))
def test_contract_parameter_schemas(server_name: str):
    """
    Test that tool parameter schemas match the contract.

    **Validates: Requirements 2.2**

    For any MCP server with a defined contract, all tool parameters should
    match the contract definitions (required parameters exist, types defined).
    """
    contract = ALL_CONTRACTS[server_name]
    server = get_server_instance(server_name)

    validator = ContractValidator(server, contract)
    errors, warnings = validator.validate_parameter_schemas()

    # We allow warnings (extra parameters) but not errors
    assert len(errors) == 0, f"Parameter schema errors in {server_name}: {[e.message for e in errors]}"


@pytest.mark.parametrize("server_name", list(ALL_CONTRACTS.keys()))
def test_contract_completeness(server_name: str):
    """
    Property 3: Contract Completeness

    **Validates: Requirements 2.2**

    For any MCP server with a defined contract, the server should:
    1. Implement all tools specified in the contract
    2. Have matching parameter signatures
    3. Have all parameters properly typed in the contract

    This is the comprehensive contract validation test.
    """
    contract = ALL_CONTRACTS[server_name]
    server = get_server_instance(server_name)

    validator = ContractValidator(server, contract)
    result = validator.validate()

    # Build detailed error message
    error_messages = []
    if result.errors:
        error_messages.append(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            error_messages.append(f"  - [{error.error_type}] {error.message}")

    if result.warnings:
        error_messages.append(f"\nWarnings ({len(result.warnings)}):")
        for warning in result.warnings:
            error_messages.append(f"  - {warning}")

    assert result.passed, f"Contract validation failed for {server_name}:{''.join(error_messages)}"


@given(
    server_name=st.sampled_from(list(ALL_CONTRACTS.keys())),
)
@settings(max_examples=10, deadline=None)
def test_contract_validation_is_deterministic(server_name: str):
    """
    Property test: Contract validation should be deterministic.

    Running validation multiple times on the same server should produce
    the same results.
    """
    contract = ALL_CONTRACTS[server_name]
    server = get_server_instance(server_name)

    validator1 = ContractValidator(server, contract)
    result1 = validator1.validate()

    validator2 = ContractValidator(server, contract)
    result2 = validator2.validate()

    # Results should be identical
    assert result1.passed == result2.passed
    assert len(result1.errors) == len(result2.errors)
    assert len(result1.warnings) == len(result2.warnings)


@given(
    server_name=st.sampled_from(list(ALL_CONTRACTS.keys())),
)
@settings(max_examples=10, deadline=None)
def test_all_contract_tools_have_type_definitions(server_name: str):
    """
    Property test: All parameters in contracts should have type definitions.

    For any server contract, every parameter should have a 'type' field defined.
    """
    contract = ALL_CONTRACTS[server_name]

    for tool in contract.tools:
        for param_name, param_spec in tool.parameters.items():
            assert "type" in param_spec, (
                f"Parameter '{param_name}' in tool '{tool.name}' "
                f"of {server_name} contract missing type definition"
            )


@given(
    server_name=st.sampled_from(list(ALL_CONTRACTS.keys())),
)
@settings(max_examples=10, deadline=None)
def test_all_contract_tools_have_return_types(server_name: str):
    """
    Property test: All tools in contracts should have return type definitions.

    For any server contract, every tool should have a return_type specified.
    """
    contract = ALL_CONTRACTS[server_name]

    for tool in contract.tools:
        assert tool.return_type is not None, (
            f"Tool '{tool.name}' in {server_name} contract missing return type definition"
        )
