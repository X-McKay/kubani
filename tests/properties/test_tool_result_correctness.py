"""
Property-Based Test: Tool Result Correctness

**Feature: mcp-infrastructure-improvements, Property 20: Tool Result Correctness**

Property: For any MCP server tool with valid inputs and real backends, the tool
should produce correct results that match expected behavior.

Validates: Requirements 11.2
"""

import logging

import pytest
from hypothesis import given, settings, strategies as st

from kubani.mcp.servers.tests.comprehensive_test_utils import (
    get_test_resource_prefix,
    load_test_config,
    start_mcp_server_stdio,
)

logger = logging.getLogger(__name__)


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_discord_message_round_trip():
    """
    Property: Discord message round trip correctness.

    For any message sent to Discord, retrieving it should return the same content.
    This verifies the send_message and get_message tools work correctly together.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data.get("test_channel_id")
        if not channel_id:
            pytest.skip("No test channel configured")

        # Send a message
        test_content = f"Round trip test - {get_test_resource_prefix()}"
        send_result = await session.call_tool(
            "send_message",
            {"channel_id": channel_id, "content": test_content},
        )

        message_id = send_result["message_id"]

        try:
            # Retrieve the message
            get_result = await session.call_tool(
                "get_message",
                {"channel_id": channel_id, "message_id": message_id},
            )

            # Verify correctness
            assert get_result["message_id"] == message_id
            assert get_result["content"] == test_content
            assert get_result["channel_id"] == channel_id

        finally:
            # Cleanup
            try:
                await session.call_tool(
                    "delete_message",
                    {"channel_id": channel_id, "message_id": message_id},
                )
            except Exception as e:
                logger.warning(f"Failed to cleanup message {message_id}: {e}")


@pytest.mark.property
@pytest.mark.asyncio
@settings(max_examples=5)
@given(content=st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=("Cs",))))
async def test_property_discord_message_content_preserved(content):
    """
    Property: Discord message content preservation.

    For any valid text content, sending and retrieving a message should
    preserve the exact content.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data.get("test_channel_id")
        if not channel_id:
            pytest.skip("No test channel configured")

        # Send message
        send_result = await session.call_tool(
            "send_message",
            {"channel_id": channel_id, "content": content},
        )

        message_id = send_result["message_id"]

        try:
            # Retrieve and verify
            get_result = await session.call_tool(
                "get_message",
                {"channel_id": channel_id, "message_id": message_id},
            )

            # Content should be preserved exactly
            assert get_result["content"] == content

        finally:
            # Cleanup
            try:
                await session.call_tool(
                    "delete_message",
                    {"channel_id": channel_id, "message_id": message_id},
                )
            except Exception:
                pass


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_discord_channel_creation_correctness():
    """
    Property: Discord channel creation correctness.

    When creating a channel, the returned channel should have the specified
    properties and should appear in the channel list.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        channel_name = f"{get_test_resource_prefix()}-test"
        topic = "Test channel for property testing"

        # Create channel
        create_result = await session.call_tool(
            "create_channel",
            {"name": channel_name, "topic": topic},
        )

        channel_id = create_result["channel_id"]

        try:
            # Verify channel properties
            assert create_result["name"] == channel_name.lower().replace("_", "-")
            assert create_result["topic"] == topic

            # Verify channel appears in list
            list_result = await session.call_tool("list_channels", {})
            channel_ids = [ch["channel_id"] for ch in list_result["channels"]]
            assert channel_id in channel_ids

        finally:
            # Cleanup
            try:
                await session.call_tool(
                    "delete_channel",
                    {"channel_id": channel_id},
                )
            except Exception as e:
                logger.warning(f"Failed to cleanup channel {channel_id}: {e}")


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_discord_reaction_correctness():
    """
    Property: Discord reaction correctness.

    When adding a reaction to a message, the reaction should appear in the
    reactions list for that message.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data.get("test_channel_id")
        if not channel_id:
            pytest.skip("No test channel configured")

        # Create a message
        send_result = await session.call_tool(
            "send_message",
            {"channel_id": channel_id, "content": "Message for reaction test"},
        )

        message_id = send_result["message_id"]

        try:
            # Add reaction
            emoji = "👍"
            await session.call_tool(
                "add_reaction",
                {"channel_id": channel_id, "message_id": message_id, "emoji": emoji},
            )

            # Verify reaction appears
            reactions_result = await session.call_tool(
                "get_reactions",
                {"channel_id": channel_id, "message_id": message_id},
            )

            # Should have at least one reaction
            assert len(reactions_result["reactions"]) > 0

            # Should include our emoji
            emojis = [r["emoji"] for r in reactions_result["reactions"]]
            assert emoji in emojis

        finally:
            # Cleanup
            try:
                await session.call_tool(
                    "delete_message",
                    {"channel_id": channel_id, "message_id": message_id},
                )
            except Exception:
                pass


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_qdrant_collection_round_trip():
    """
    Property: Qdrant collection round trip correctness.

    Creating a collection and then listing collections should show the
    created collection.
    """
    config = load_test_config("qdrant")

    if not config.enabled:
        pytest.skip("Qdrant not configured")

    async with start_mcp_server_stdio("qdrant", config) as session:
        collection_name = f"{get_test_resource_prefix()}_collection"

        # Create collection
        await session.call_tool(
            "create_collection",
            {
                "name": collection_name,
                "vector_size": 128,
                "distance": "Cosine",
            },
        )

        try:
            # List collections
            list_result = await session.call_tool("list_collections", {})

            # Verify collection appears
            collection_names = [c["name"] for c in list_result["collections"]]
            assert collection_name in collection_names

        finally:
            # Cleanup
            try:
                await session.call_tool(
                    "delete_collection",
                    {"name": collection_name},
                )
            except Exception as e:
                logger.warning(f"Failed to cleanup collection {collection_name}: {e}")


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_skills_list_skills_structure():
    """
    Property: Skills list structure correctness.

    The list_skills tool should always return a properly structured response
    with required fields.
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

        # Each skill should have required fields
        for skill in result["skills"]:
            assert "name" in skill
            assert "description" in skill
            assert isinstance(skill["name"], str)
            assert isinstance(skill["description"], str)


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_memory_agent_isolation():
    """
    Property: Memory agent isolation correctness.

    Data stored for one agent should not be visible to another agent.
    This verifies proper namespacing.
    """
    config = load_test_config("memory")

    if not config.enabled:
        pytest.skip("Memory not configured")

    async with start_mcp_server_stdio("memory", config) as session:
        agent1_id = f"{get_test_resource_prefix()}_agent1"
        agent2_id = f"{get_test_resource_prefix()}_agent2"

        # Store learning for agent1
        learning_content = "Test learning for agent isolation"
        await session.call_tool(
            "store_learning",
            {
                "agent_id": agent1_id,
                "content": learning_content,
                "learning_type": "pattern",
                "confidence": 0.9,
            },
        )

        # Query learnings for agent2
        agent2_learnings = await session.call_tool(
            "get_agent_learnings",
            {"agent_id": agent2_id},
        )

        # Agent2 should not see agent1's learning
        agent2_contents = [l["content"] for l in agent2_learnings.get("learnings", [])]
        assert learning_content not in agent2_contents

        # Agent1 should see their own learning
        agent1_learnings = await session.call_tool(
            "get_agent_learnings",
            {"agent_id": agent1_id},
        )

        agent1_contents = [l["content"] for l in agent1_learnings.get("learnings", [])]
        assert learning_content in agent1_contents
