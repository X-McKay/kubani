"""
Property-Based Test: Tool Execution Success

**Feature: mcp-infrastructure-improvements, Property 19: Tool Execution Success**

Property: For any MCP server tool with valid inputs, calling the tool should
complete without errors and return a valid response.

Validates: Requirements 11.1
"""

import logging

import pytest
from hypothesis import given, settings, strategies as st

from kubani.mcp.servers.tests.comprehensive_test_utils import (
    load_test_config,
    start_mcp_server_stdio,
)

logger = logging.getLogger(__name__)

# Define server configurations
SERVERS = ["discord", "temporal", "qdrant", "memory", "skills"]

# Define tools that can be tested without side effects (read-only operations)
SAFE_TOOLS = {
    "discord": [
        ("list_channels", {}),
        ("get_messages", {"channel_id": "test_channel_id", "limit": 1}),
    ],
    "temporal": [
        ("list_workflows", {"namespace": "default"}),
    ],
    "qdrant": [
        ("list_collections", {}),
    ],
    "memory": [
        ("get_agent_learnings", {"agent_id": "test-agent"}),
    ],
    "skills": [
        ("list_skills", {}),
    ],
}


@pytest.mark.property
@pytest.mark.parametrize("server_name", SERVERS)
@settings(max_examples=10, deadline=30000)  # 30 second deadline for each example
@given(data=st.data())
@pytest.mark.asyncio
async def test_property_tool_execution_success(server_name, data):
    """
    Property: Tool execution success.

    For any MCP server tool with valid inputs, the tool should execute
    without errors and return a valid response.

    This property tests that all tools can be called successfully with
    appropriate inputs.
    """
    # Load configuration
    config = load_test_config(server_name)

    if not config.enabled:
        pytest.skip(f"{server_name} not configured in config/local.yaml")

    # Get safe tools for this server
    safe_tools = SAFE_TOOLS.get(server_name, [])
    if not safe_tools:
        pytest.skip(f"No safe tools defined for {server_name}")

    # Select a random tool to test
    tool_name, base_params = data.draw(st.sampled_from(safe_tools))

    # Prepare parameters with actual values from config
    params = base_params.copy()
    if server_name == "discord" and "channel_id" in params:
        if params["channel_id"] == "test_channel_id":
            params["channel_id"] = config.test_data.get("test_channel_id", "")
            if not params["channel_id"]:
                pytest.skip("No test channel configured")

    logger.info(f"Testing {server_name}.{tool_name} with params: {params}")

    # Start server and call tool
    async with start_mcp_server_stdio(server_name, config) as session:
        try:
            result = await session.call_tool(tool_name, params)

            # Verify result is not None and is a valid response
            assert result is not None, f"Tool {tool_name} returned None"

            # For list operations, verify structure
            if "list" in tool_name:
                assert isinstance(result, dict), f"Tool {tool_name} should return dict"

            logger.info(f"✓ {server_name}.{tool_name} executed successfully")

        except Exception as e:
            # Log the error for debugging
            logger.error(f"✗ {server_name}.{tool_name} failed: {e}")
            raise


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_discord_list_channels_always_succeeds():
    """
    Specific property: Discord list_channels should always succeed.

    This is a focused property test for a critical read-only operation.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        result = await session.call_tool("list_channels", {})

        # Verify structure
        assert isinstance(result, dict)
        assert "channels" in result
        assert "guild_id" in result
        assert "count" in result
        assert isinstance(result["channels"], list)
        assert result["count"] >= 0


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_skills_list_skills_always_succeeds():
    """
    Specific property: Skills list_skills should always succeed.

    This is a focused property test for the skills MCP server.
    """
    config = load_test_config("skills")

    if not config.enabled:
        pytest.skip("Skills not configured")

    async with start_mcp_server_stdio("skills", config) as session:
        result = await session.call_tool("list_skills", {})

        # Verify structure
        assert isinstance(result, dict)
        assert "skills" in result
        assert isinstance(result["skills"], list)


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_qdrant_list_collections_always_succeeds():
    """
    Specific property: Qdrant list_collections should always succeed.

    This is a focused property test for the qdrant MCP server.
    """
    config = load_test_config("qdrant")

    if not config.enabled:
        pytest.skip("Qdrant not configured")

    async with start_mcp_server_stdio("qdrant", config) as session:
        result = await session.call_tool("list_collections", {})

        # Verify structure
        assert isinstance(result, dict)
        assert "collections" in result
        assert isinstance(result["collections"], list)
