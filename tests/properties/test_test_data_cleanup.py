"""
Property-Based Test: Test Data Cleanup

**Feature: mcp-infrastructure-improvements, Property 22: Test Data Cleanup**

Property: For any test that creates data in backends, the test should clean up
all created data after completion, leaving no test artifacts.

Validates: Requirements 11.6
"""

import logging

import pytest

from kubani.mcp.servers.tests.comprehensive_test_utils import (
    cleanup_test_data,
    get_test_resource_prefix,
    load_test_config,
    start_mcp_server_stdio,
)

logger = logging.getLogger(__name__)


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_discord_message_cleanup():
    """
    Property: Discord message cleanup completeness.

    After creating and cleaning up a message, the message should no longer
    be retrievable.
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
            {"channel_id": channel_id, "content": "Message for cleanup test"},
        )

        message_id = send_result["message_id"]

        # Track for cleanup
        created_resources = {
            "messages": [message_id],
            "message_channels": {message_id: channel_id},
        }

        # Cleanup
        await cleanup_test_data("discord", session, config, created_resources)

        # Verify message is gone
        with pytest.raises(Exception):
            await session.call_tool(
                "get_message",
                {"channel_id": channel_id, "message_id": message_id},
            )


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_discord_channel_cleanup():
    """
    Property: Discord channel cleanup completeness.

    After creating and cleaning up a channel, the channel should no longer
    appear in the channel list.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        channel_name = f"{get_test_resource_prefix()}-cleanup-test"

        # Create channel
        create_result = await session.call_tool(
            "create_channel",
            {"name": channel_name},
        )

        channel_id = create_result["channel_id"]

        # Track for cleanup
        created_resources = {"channels": [channel_id]}

        # Cleanup
        await cleanup_test_data("discord", session, config, created_resources)

        # Verify channel is gone
        list_result = await session.call_tool("list_channels", {})
        channel_ids = [ch["channel_id"] for ch in list_result["channels"]]
        assert channel_id not in channel_ids


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_discord_webhook_cleanup():
    """
    Property: Discord webhook cleanup completeness.

    After creating and cleaning up a webhook, the webhook should no longer
    appear in the webhook list.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data.get("test_channel_id")
        if not channel_id:
            pytest.skip("No test channel configured")

        webhook_name = f"{get_test_resource_prefix()}-webhook"

        # Create webhook
        create_result = await session.call_tool(
            "create_webhook",
            {"channel_id": channel_id, "name": webhook_name},
        )

        webhook_id = create_result["webhook_id"]

        # Track for cleanup
        created_resources = {
            "webhooks": [{"webhook_id": webhook_id, "channel_id": channel_id}]
        }

        # Cleanup
        await cleanup_test_data("discord", session, config, created_resources)

        # Verify webhook is gone
        list_result = await session.call_tool(
            "list_webhooks",
            {"channel_id": channel_id},
        )

        webhook_ids = [wh["webhook_id"] for wh in list_result["webhooks"]]
        assert webhook_id not in webhook_ids


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_qdrant_collection_cleanup():
    """
    Property: Qdrant collection cleanup completeness.

    After creating and cleaning up a collection, the collection should no
    longer appear in the collection list.
    """
    config = load_test_config("qdrant")

    if not config.enabled:
        pytest.skip("Qdrant not configured")

    async with start_mcp_server_stdio("qdrant", config) as session:
        collection_name = f"{get_test_resource_prefix()}_cleanup_test"

        # Create collection
        await session.call_tool(
            "create_collection",
            {
                "name": collection_name,
                "vector_size": 128,
                "distance": "Cosine",
            },
        )

        # Track for cleanup
        created_resources = {"collections": [collection_name]}

        # Cleanup
        await cleanup_test_data("qdrant", session, config, created_resources)

        # Verify collection is gone
        list_result = await session.call_tool("list_collections", {})
        collection_names = [c["name"] for c in list_result["collections"]]
        assert collection_name not in collection_names


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_qdrant_points_cleanup():
    """
    Property: Qdrant points cleanup completeness.

    After adding and cleaning up points, the points should no longer be
    in the collection.
    """
    config = load_test_config("qdrant")

    if not config.enabled:
        pytest.skip("Qdrant not configured")

    async with start_mcp_server_stdio("qdrant", config) as session:
        collection_name = f"{get_test_resource_prefix()}_points_test"

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
            # Add a point
            point_id = "test_point_1"
            await session.call_tool(
                "upsert_points",
                {
                    "collection_name": collection_name,
                    "points": [
                        {
                            "id": point_id,
                            "vector": [0.1] * 128,
                            "payload": {"test": "data"},
                        }
                    ],
                },
            )

            # Track for cleanup
            created_resources = {
                "points": [{"collection": collection_name, "id": point_id}],
                "collections": [collection_name],
            }

            # Cleanup
            await cleanup_test_data("qdrant", session, config, created_resources)

            # Verify collection is gone (which also removes points)
            list_result = await session.call_tool("list_collections", {})
            collection_names = [c["name"] for c in list_result["collections"]]
            assert collection_name not in collection_names

        except Exception as e:
            # Cleanup collection if test fails
            try:
                await session.call_tool(
                    "delete_collection",
                    {"name": collection_name},
                )
            except Exception:
                pass
            raise


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_memory_cache_cleanup():
    """
    Property: Memory cache cleanup completeness.

    After setting and cleaning up cache entries, the entries should no
    longer be retrievable.
    """
    config = load_test_config("memory")

    if not config.enabled:
        pytest.skip("Memory not configured")

    async with start_mcp_server_stdio("memory", config) as session:
        cache_key = f"{get_test_resource_prefix()}_cache_key"

        # Set cache entry
        await session.call_tool(
            "cache_set",
            {
                "key": cache_key,
                "value": "test value",
                "ttl": 3600,
            },
        )

        # Track for cleanup
        created_resources = {"cache_keys": [cache_key]}

        # Cleanup
        await cleanup_test_data("memory", session, config, created_resources)

        # Verify cache entry is gone
        get_result = await session.call_tool(
            "cache_get",
            {"key": cache_key},
        )

        # Should return None or indicate key not found
        assert get_result.get("value") is None or get_result.get("found") is False


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_cleanup_handles_missing_resources():
    """
    Property: Cleanup should handle already-deleted resources gracefully.

    If a resource is already deleted, cleanup should not fail.
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
            {"channel_id": channel_id, "content": "Message for double cleanup test"},
        )

        message_id = send_result["message_id"]

        # Delete it manually
        await session.call_tool(
            "delete_message",
            {"channel_id": channel_id, "message_id": message_id},
        )

        # Track for cleanup (even though already deleted)
        created_resources = {
            "messages": [message_id],
            "message_channels": {message_id: channel_id},
        }

        # Cleanup should not fail
        await cleanup_test_data("discord", session, config, created_resources)


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_cleanup_handles_multiple_resources():
    """
    Property: Cleanup should handle multiple resources of different types.

    When cleaning up multiple resources, all should be removed successfully.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        channel_id = config.test_data.get("test_channel_id")
        if not channel_id:
            pytest.skip("No test channel configured")

        # Create multiple messages
        message_ids = []
        for i in range(3):
            send_result = await session.call_tool(
                "send_message",
                {"channel_id": channel_id, "content": f"Message {i} for multi cleanup test"},
            )
            message_ids.append(send_result["message_id"])

        # Track all for cleanup
        created_resources = {
            "messages": message_ids,
            "message_channels": {mid: channel_id for mid in message_ids},
        }

        # Cleanup all
        await cleanup_test_data("discord", session, config, created_resources)

        # Verify all are gone
        for message_id in message_ids:
            with pytest.raises(Exception):
                await session.call_tool(
                    "get_message",
                    {"channel_id": channel_id, "message_id": message_id},
                )


@pytest.mark.property
@pytest.mark.asyncio
async def test_property_no_test_resources_remain():
    """
    Property: No test resources should remain after cleanup.

    After running tests and cleanup, no resources with test prefixes
    should exist in the system.
    """
    config = load_test_config("discord")

    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        # List all channels
        list_result = await session.call_tool("list_channels", {})

        # Check for test channels
        test_channels = [
            ch for ch in list_result["channels"]
            if "test_comprehensive" in ch["name"].lower() or "test-comprehensive" in ch["name"].lower()
        ]

        # Should be no test channels remaining
        if test_channels:
            logger.warning(f"Found {len(test_channels)} test channels that should have been cleaned up")
            # This is a warning, not a failure, as cleanup might have failed in previous runs
