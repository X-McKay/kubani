"""Unit tests for gateway configuration validation.

Tests that the gateway correctly reads and uses environment variables
for database, Redis, and Temporal connections.

Requirements: 9.2
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGatewayConfiguration:
    """Test gateway environment variable configuration."""

    @pytest.mark.asyncio
    async def test_gateway_state_initialize_with_defaults(self):
        """
        Test that GatewayState.initialize uses default values when
        environment variables are not set.
        
        Requirements: 9.2
        """
        from kubani.nexus.gateway.app import GatewayState

        # Mock all the dependencies
        mock_client = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_pubsub.connect = AsyncMock()
        mock_pool = AsyncMock()

        with patch.dict(os.environ, {}, clear=True), \
             patch("temporalio.client.Client.connect", AsyncMock(return_value=mock_client)) as mock_connect, \
             patch("kubani.nexus.gateway.app.NexusPubSub", return_value=mock_pubsub) as mock_pubsub_class, \
             patch("kubani.nexus.gateway.app.create_pool", AsyncMock(return_value=mock_pool)) as mock_create_pool:
            
            state = GatewayState()
            await state.initialize()

            # Verify default values were used
            mock_connect.assert_called_once_with(
                "localhost:7233",
                namespace="nexus",
            )
            mock_pubsub_class.assert_called_once_with(redis_url="redis://localhost:6379")
            mock_create_pool.assert_called_once_with(
                "postgresql://kubani:kubani@localhost:5432/kubani_nexus"
            )

    @pytest.mark.asyncio
    async def test_gateway_state_initialize_with_custom_temporal_host(self):
        """
        Test that GatewayState.initialize reads TEMPORAL_HOST from environment.
        
        Requirements: 9.2
        """
        from kubani.nexus.gateway.app import GatewayState

        custom_host = "temporal.example.com:7233"

        # Mock all the dependencies
        mock_client = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_pubsub.connect = AsyncMock()
        mock_pool = AsyncMock()

        with patch.dict(os.environ, {"TEMPORAL_HOST": custom_host}), \
             patch("temporalio.client.Client.connect", AsyncMock(return_value=mock_client)) as mock_connect, \
             patch("kubani.nexus.gateway.app.NexusPubSub", return_value=mock_pubsub), \
             patch("kubani.nexus.gateway.app.create_pool", AsyncMock(return_value=mock_pool)):
            
            state = GatewayState()
            await state.initialize()

            # Verify custom TEMPORAL_HOST was used
            mock_connect.assert_called_once_with(
                custom_host,
                namespace="nexus",
            )

    @pytest.mark.asyncio
    async def test_gateway_state_initialize_with_custom_redis_url(self):
        """
        Test that GatewayState.initialize reads REDIS_URL from environment.
        
        Requirements: 9.2
        """
        from kubani.nexus.gateway.app import GatewayState

        custom_redis = "redis://redis.example.com:6379/1"

        # Mock all the dependencies
        mock_client = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_pubsub.connect = AsyncMock()
        mock_pool = AsyncMock()

        with patch.dict(os.environ, {"REDIS_URL": custom_redis}), \
             patch("temporalio.client.Client.connect", AsyncMock(return_value=mock_client)), \
             patch("kubani.nexus.gateway.app.NexusPubSub", return_value=mock_pubsub) as mock_pubsub_class, \
             patch("kubani.nexus.gateway.app.create_pool", AsyncMock(return_value=mock_pool)):
            
            state = GatewayState()
            await state.initialize()

            # Verify custom REDIS_URL was used
            mock_pubsub_class.assert_called_once_with(redis_url=custom_redis)

    @pytest.mark.asyncio
    async def test_gateway_state_initialize_with_custom_database_url(self):
        """
        Test that GatewayState.initialize reads NEXUS_DATABASE_URL from environment.
        
        Requirements: 9.2
        """
        from kubani.nexus.gateway.app import GatewayState

        custom_db = "postgresql://user:pass@db.example.com:5432/nexus_prod"

        # Mock all the dependencies
        mock_client = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_pubsub.connect = AsyncMock()
        mock_pool = AsyncMock()

        with patch.dict(os.environ, {"NEXUS_DATABASE_URL": custom_db}), \
             patch("temporalio.client.Client.connect", AsyncMock(return_value=mock_client)), \
             patch("kubani.nexus.gateway.app.NexusPubSub", return_value=mock_pubsub), \
             patch("kubani.nexus.gateway.app.create_pool", AsyncMock(return_value=mock_pool)) as mock_create_pool:
            
            state = GatewayState()
            await state.initialize()

            # Verify custom NEXUS_DATABASE_URL was used
            mock_create_pool.assert_called_once_with(custom_db)

    @pytest.mark.asyncio
    async def test_gateway_state_initialize_with_all_custom_values(self):
        """
        Test that GatewayState.initialize reads all environment variables correctly.
        
        Requirements: 9.2
        """
        from kubani.nexus.gateway.app import GatewayState

        custom_temporal = "temporal.prod.example.com:7233"
        custom_namespace = "production"
        custom_redis = "redis://redis.prod.example.com:6379/2"
        custom_db = "postgresql://prod_user:prod_pass@db.prod.example.com:5432/nexus"

        # Mock all the dependencies
        mock_client = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_pubsub.connect = AsyncMock()
        mock_pool = AsyncMock()

        with patch.dict(
            os.environ,
            {
                "TEMPORAL_HOST": custom_temporal,
                "TEMPORAL_NAMESPACE": custom_namespace,
                "REDIS_URL": custom_redis,
                "NEXUS_DATABASE_URL": custom_db,
            },
        ), \
             patch("temporalio.client.Client.connect", AsyncMock(return_value=mock_client)) as mock_connect, \
             patch("kubani.nexus.gateway.app.NexusPubSub", return_value=mock_pubsub) as mock_pubsub_class, \
             patch("kubani.nexus.gateway.app.create_pool", AsyncMock(return_value=mock_pool)) as mock_create_pool:
            
            state = GatewayState()
            await state.initialize()

            # Verify all custom values were used
            mock_connect.assert_called_once_with(
                custom_temporal,
                namespace=custom_namespace,
            )
            mock_pubsub_class.assert_called_once_with(redis_url=custom_redis)
            mock_create_pool.assert_called_once_with(custom_db)

    @pytest.mark.asyncio
    async def test_gateway_state_cleanup(self):
        """
        Test that GatewayState.cleanup properly closes all connections.
        
        Requirements: 9.2
        """
        from kubani.nexus.gateway.app import GatewayState

        # Create mock connections
        mock_pubsub = AsyncMock()
        mock_pubsub.close = AsyncMock()
        mock_pool = AsyncMock()
        mock_pool.close = AsyncMock()

        state = GatewayState()
        state.pubsub = mock_pubsub
        state.db_pool = mock_pool

        # Cleanup
        await state.cleanup()

        # Verify cleanup was called
        mock_pubsub.close.assert_called_once()
        mock_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_gateway_state_cleanup_handles_none_values(self):
        """
        Test that GatewayState.cleanup handles None values gracefully.
        
        Requirements: 9.2
        """
        from kubani.nexus.gateway.app import GatewayState

        state = GatewayState()
        # Don't set pubsub or db_pool (they remain None)

        # Should not raise an exception
        await state.cleanup()
