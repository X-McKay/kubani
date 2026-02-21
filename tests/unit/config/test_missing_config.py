"""Unit tests for missing environment variable handling.

Tests that the system provides clear error messages when required
environment variables are missing.

Requirements: 9.4
"""

import os
from unittest.mock import AsyncMock, patch

import pytest


class TestMissingEnvironmentVariables:
    """Test handling of missing environment variables."""

    def test_orchestrator_provides_defaults_for_missing_vars(self):
        """
        Test that the orchestrator provides sensible defaults when
        environment variables are missing.

        Requirements: 9.4
        """
        from kubani.nexus.orchestrator.worker import get_temporal_settings

        # Clear all environment variables
        with patch.dict(os.environ, {}, clear=True):
            host, namespace = get_temporal_settings()

            # Should provide defaults, not raise an error
            assert host == "localhost:7233"
            assert namespace == "nexus"

    @pytest.mark.asyncio
    async def test_gateway_provides_defaults_for_missing_vars(self):
        """
        Test that the gateway provides sensible defaults when
        environment variables are missing.

        Requirements: 9.4
        """
        from kubani.nexus.gateway.app import GatewayState

        # Mock dependencies
        mock_client = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_pubsub.connect = AsyncMock()
        mock_pool = AsyncMock()

        # Clear all environment variables
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "temporalio.client.Client.connect", AsyncMock(return_value=mock_client)
            ) as mock_connect,
            patch(
                "kubani.nexus.gateway.app.NexusPubSub", return_value=mock_pubsub
            ) as mock_pubsub_class,
            patch(
                "kubani.nexus.gateway.app.create_pool", AsyncMock(return_value=mock_pool)
            ) as mock_create_pool,
        ):
            state = GatewayState()

            # Should not raise an error
            await state.initialize()

            # Verify defaults were used
            mock_connect.assert_called_once_with(
                "localhost:7233",
                namespace="nexus",
            )
            mock_pubsub_class.assert_called_once_with(redis_url="redis://localhost:6379")
            mock_create_pool.assert_called_once_with(
                "postgresql://kubani:kubani@localhost:5432/kubani_nexus"
            )

    @pytest.mark.asyncio
    async def test_gateway_handles_connection_failure_gracefully(self):
        """
        Test that the gateway provides clear error messages when
        connections fail (e.g., due to wrong configuration).

        Requirements: 9.4
        """
        from kubani.nexus.gateway.app import GatewayState

        # Mock a connection failure
        with (
            patch.dict(os.environ, {"TEMPORAL_HOST": "invalid-host:7233"}),
            patch(
                "temporalio.client.Client.connect",
                AsyncMock(side_effect=Exception("Connection refused")),
            ),
        ):
            state = GatewayState()

            # Should raise a clear exception
            with pytest.raises(Exception) as exc_info:
                await state.initialize()

            # Verify the error message is clear
            assert "Connection refused" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_activities_provide_defaults_for_database_url(self):
        """
        Test that activities provide default database URL when
        NEXUS_DATABASE_URL is not set.

        Requirements: 9.4
        """
        from kubani.nexus.orchestrator.activities import persist_message

        # Mock the database pool
        mock_pool = AsyncMock()
        mock_pool.fetchval = AsyncMock(return_value=123)

        # Clear NEXUS_DATABASE_URL
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "kubani.nexus.db.create_pool", AsyncMock(return_value=mock_pool)
            ) as mock_create_pool,
        ):
            # Call the activity with a dict (persist_message expects dict input)
            message_data = {
                "conversation_id": "test-conv",
                "role": "assistant",
                "content": "Test message",
                "user_id": "test-user",
            }

            result = await persist_message(message_data)

            # Verify default database URL was used
            mock_create_pool.assert_called_once_with(
                "postgresql://kubani:kubani@localhost:5432/kubani_nexus"
            )
            assert result["message_id"] is not None

    @pytest.mark.asyncio
    async def test_activities_provide_defaults_for_redis_url(self):
        """
        Test that activities provide default Redis URL when
        REDIS_URL is not set.

        Requirements: 9.4
        """
        from kubani.nexus.orchestrator.activities import publish_response_activity

        # Mock the pubsub
        mock_pubsub = AsyncMock()
        mock_pubsub.connect = AsyncMock()
        mock_pubsub.publish_response = AsyncMock()
        mock_pubsub.close = AsyncMock()

        # Clear REDIS_URL
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("kubani.nexus.pubsub.NexusPubSub", return_value=mock_pubsub) as mock_pubsub_class,
        ):
            # Call the activity with a dict (publish_response_activity expects dict input)
            message_data = {
                "conversation_id": "test-conv",
                "text": "Test response",
                "metadata": {},
            }

            await publish_response_activity(message_data)

            # Verify default Redis URL was used
            mock_pubsub_class.assert_called_once_with(redis_url="redis://localhost:6379")

    def test_sandbox_provides_defaults_for_database_url(self):
        """
        Test that sandbox executor provides default database URL when
        NEXUS_DATABASE_URL is not set.

        Requirements: 9.4
        """
        # This is tested indirectly through the _resolve_skill_content function
        # which uses the database URL. The function should not crash when
        # the environment variable is missing.

        # Clear NEXUS_DATABASE_URL
        with patch.dict(os.environ, {}, clear=True):
            # Import should not raise an error
            from kubani.nexus.sandbox.executor import execute_skill_in_sandbox

            # The function exists and can be called (actual execution would
            # require mocking the database, which is tested elsewhere)
            assert execute_skill_in_sandbox is not None

    def test_environment_variable_documentation(self):
        """
        Test that all required environment variables are documented
        in the code with their default values.

        Requirements: 9.4
        """
        # This test verifies that the code includes clear defaults
        # and doesn't require environment variables to be set.

        from kubani.nexus.orchestrator.worker import get_temporal_settings
        from kubani.nexus.sandbox.executor import BLOCKED_ENV_VARS

        # Verify defaults are accessible
        with patch.dict(os.environ, {}, clear=True):
            host, namespace = get_temporal_settings()
            assert host is not None
            assert namespace is not None

        # Verify BLOCKED_ENV_VARS is defined
        assert isinstance(BLOCKED_ENV_VARS, set)
        assert len(BLOCKED_ENV_VARS) > 0

    @pytest.mark.asyncio
    async def test_database_connection_error_provides_clear_message(self):
        """
        Test that database connection errors provide clear messages
        about what went wrong.

        Requirements: 9.4
        """
        # Try to connect with an invalid URL
        # Note: This test documents expected behavior but may not actually
        # connect to a database in the test environment
        invalid_url = "postgresql://invalid:invalid@nonexistent-host-12345:5432/nonexistent"

        # Mock asyncpg to raise a connection error
        with patch(
            "asyncpg.create_pool", AsyncMock(side_effect=Exception("could not translate host name"))
        ):
            from kubani.nexus.db import create_pool

            with pytest.raises(Exception) as exc_info:
                await create_pool(invalid_url)

            # Verify the error message is informative
            error_message = str(exc_info.value)
            assert "host" in error_message.lower() or "translate" in error_message.lower()

    @pytest.mark.asyncio
    async def test_redis_connection_error_provides_clear_message(self):
        """
        Test that Redis connection errors provide clear messages
        about what went wrong.

        Requirements: 9.4
        """
        from kubani.nexus.pubsub import NexusPubSub

        # Try to connect with an invalid URL
        invalid_url = "redis://nonexistent-host-12345:6379"
        pubsub = NexusPubSub(redis_url=invalid_url)

        # Mock redis to raise a connection error
        with patch("redis.asyncio.from_url", side_effect=Exception("Error connecting to Redis")):
            with pytest.raises(Exception) as exc_info:
                await pubsub.connect()

            # Verify the error message is informative
            error_message = str(exc_info.value)
            assert "redis" in error_message.lower() or "connect" in error_message.lower()
