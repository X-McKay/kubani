"""
Property-Based Test: Tool Error Handling

**Feature: mcp-infrastructure-improvements, Property 21: Tool Error Handling**

Property: For any MCP server tool with invalid inputs, the tool should handle
errors gracefully and return informative error messages.

Validates: Requirements 11.3
"""

import logging

import pytest
from hypothesis import given, settings, strategies as st

from kubani.mcp.servers.tests.comprehensive_test_utils import (
    load_test_config,
    start_mcp_server_stdio,
)

logger = logging.getLogger(__name__)


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_discord_invalid_channel_id_error():
    """
    Property: Discord tools should handle invalid channel IDs gracefully.

    For any invalid channel ID, tools should raise an error with a clear message.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        # Test with invalid channel ID
        invalid_channel_id = "999999999999999999"

        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "send_message",
                {"channel_id": invalid_channel_id, "content": "Test"},
            )

        # Error message should be informative
        error_msg = str(exc_info.value).lower()
        assert "not found" in error_msg or "invalid" in error_msg or "channel" in error_msg


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_discord_invalid_message_id_error():
    """
    Property: Discord tools should handle invalid message IDs gracefully.

    For any invalid message ID, tools should raise an error with a clear message.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data.get("test_channel_id")
        if not channel_id:
            pytest.skip("No test channel configured")

        # Test with invalid message ID
        invalid_message_id = "999999999999999999"

        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "get_message",
                {"channel_id": channel_id, "message_id": invalid_message_id},
            )

        # Error message should be informative
        error_msg = str(exc_info.value).lower()
        assert "not found" in error_msg or "invalid" in error_msg or "message" in error_msg


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_discord_invalid_channel_name_error():
    """
    Property: Discord tools should handle invalid channel names gracefully.

    For any non-existent channel name, tools should raise an error.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        # Test with non-existent channel name
        invalid_channel_name = "nonexistent-channel-xyz-12345"

        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "send_message_to_channel_name",
                {"channel_name": invalid_channel_name, "content": "Test"},
            )

        # Error message should be informative
        error_msg = str(exc_info.value).lower()
        assert "not found" in error_msg or "invalid" in error_msg or "channel" in error_msg


@pytest.mark.property
@pytest.mark.asyncio
@settings(max_examples=5)
@given(invalid_id=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))))
async def test_property_discord_non_numeric_ids_error(invalid_id):
    """
    Property: Discord tools should reject non-numeric IDs.

    For any non-numeric ID string, tools should raise an error.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    # Skip if the generated string happens to be numeric
    if invalid_id.isdigit():
        pytest.skip("Generated numeric ID")

    async with start_mcp_server_stdio("discord", config) as session:
        with pytest.raises(Exception):
            await session.call_tool(
                "send_message",
                {"channel_id": invalid_id, "content": "Test"},
            )


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_qdrant_invalid_collection_error():
    """
    Property: Qdrant tools should handle invalid collection names gracefully.

    For any non-existent collection, tools should raise an error.
    """
    config = load_test_config("qdrant")

    if not config.enabled:
        pytest.skip("Qdrant not configured")

    async with start_mcp_server_stdio("qdrant", config) as session:
        # Test with non-existent collection
        invalid_collection = "nonexistent_collection_xyz_12345"

        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "get_collection",
                {"name": invalid_collection},
            )

        # Error message should be informative
        error_msg = str(exc_info.value).lower()
        assert "not found" in error_msg or "not exist" in error_msg or "collection" in error_msg


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_qdrant_invalid_vector_size_error():
    """
    Property: Qdrant should reject invalid vector sizes.

    For any invalid vector size (e.g., 0, negative), collection creation
    should raise an error.
    """
    config = load_test_config("qdrant")

    if not config.enabled:
        pytest.skip("Qdrant not configured")

    async with start_mcp_server_stdio("qdrant", config) as session:
        # Test with invalid vector size
        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "create_collection",
                {
                    "name": "test_invalid_size",
                    "vector_size": 0,
                    "distance": "Cosine",
                },
            )

        # Error message should mention vector size or validation
        error_msg = str(exc_info.value).lower()
        assert "vector" in error_msg or "size" in error_msg or "invalid" in error_msg


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_memory_missing_required_fields_error():
    """
    Property: Memory tools should reject requests with missing required fields.

    For any tool call missing required parameters, an error should be raised.
    """
    config = load_test_config("memory")

    if not config.enabled:
        pytest.skip("Memory not configured")

    async with start_mcp_server_stdio("memory", config) as session:
        # Test store_learning without required fields
        with pytest.raises(Exception):
            await session.call_tool(
                "store_learning",
                {
                    # Missing agent_id, content, learning_type
                    "confidence": 0.9,
                },
            )


@pytest.mark.property
@pytest.mark.asyncio
@settings(max_examples=5)
@given(confidence=st.floats(min_value=-10.0, max_value=-0.1) | st.floats(min_value=1.1, max_value=10.0))
async def test_property_memory_invalid_confidence_error(confidence):
    """
    Property: Memory tools should reject invalid confidence values.

    For any confidence value outside [0, 1], an error should be raised.
    """
    config = load_test_config("memory")

    if not config.enabled:
        pytest.skip("Memory not configured")

    async with start_mcp_server_stdio("memory", config) as session:
        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "store_learning",
                {
                    "agent_id": "test-agent",
                    "content": "Test learning",
                    "learning_type": "pattern",
                    "confidence": confidence,
                },
            )

        # Error should mention confidence or validation
        error_msg = str(exc_info.value).lower()
        assert "confidence" in error_msg or "invalid" in error_msg or "range" in error_msg


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_temporal_invalid_workflow_id_error():
    """
    Property: Temporal tools should handle invalid workflow IDs gracefully.

    For any non-existent workflow ID, tools should raise an error.
    """
    config = load_test_config("temporal")

    if not config.enabled:
        pytest.skip("Temporal not configured")

    async with start_mcp_server_stdio("temporal", config) as session:
        # Test with non-existent workflow ID
        invalid_workflow_id = "nonexistent-workflow-xyz-12345"

        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "get_workflow_status",
                {"workflow_id": invalid_workflow_id},
            )

        # Error message should be informative
        error_msg = str(exc_info.value).lower()
        assert "not found" in error_msg or "not exist" in error_msg or "workflow" in error_msg


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_skills_invalid_skill_name_error():
    """
    Property: Skills tools should handle invalid skill names gracefully.

    For any non-existent skill name, tools should raise an error.
    """
    config = load_test_config("skills")

    if not config.enabled:
        pytest.skip("Skills not configured")

    async with start_mcp_server_stdio("skills", config) as session:
        # Test with non-existent skill
        invalid_skill_name = "nonexistent-skill-xyz-12345"

        with pytest.raises(Exception) as exc_info:
            await session.call_tool(
                "get_skill",
                {"name": invalid_skill_name},
            )

        # Error message should be informative
        error_msg = str(exc_info.value).lower()
        assert "not found" in error_msg or "not exist" in error_msg or "skill" in error_msg


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_error_messages_are_strings():
    """
    Property: All error messages should be strings.

    For any error from any tool, the error message should be a string
    (not None, not empty, not a complex object).
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        # Trigger an error
        try:
            await session.call_tool(
                "send_message",
                {"channel_id": "999999999999999999", "content": "Test"},
            )
        except Exception as e:
            # Error should have a string representation
            error_str = str(e)
            assert isinstance(error_str, str)
            assert len(error_str) > 0
            assert error_str != "None"


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_errors_dont_crash_server():
    """
    Property: Errors should not crash the server.

    After an error occurs, the server should still be responsive and
    able to handle subsequent requests.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        # Trigger an error
        try:
            await session.call_tool(
                "send_message",
                {"channel_id": "999999999999999999", "content": "Test"},
            )
        except Exception:
            pass  # Expected

        # Server should still be responsive
        result = await session.call_tool("list_channels", {})
        assert result is not None
        assert "channels" in result
