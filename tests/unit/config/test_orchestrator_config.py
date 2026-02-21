"""Unit tests for orchestrator configuration validation.

Tests that the orchestrator worker correctly reads and uses environment
variables for Temporal connection settings.

Requirements: 9.1
"""

import os
from unittest.mock import AsyncMock, patch

import pytest


class TestOrchestratorConfiguration:
    """Test orchestrator environment variable configuration."""

    def test_get_temporal_settings_with_defaults(self):
        """
        Test that get_temporal_settings returns default values when
        environment variables are not set.
        
        Requirements: 9.1
        """
        from kubani.nexus.orchestrator.worker import get_temporal_settings

        # Clear environment variables
        with patch.dict(os.environ, {}, clear=True):
            host, namespace = get_temporal_settings()

            assert host == "localhost:7233"
            assert namespace == "nexus"

    def test_get_temporal_settings_with_custom_host(self):
        """
        Test that get_temporal_settings reads TEMPORAL_HOST from environment.
        
        Requirements: 9.1
        """
        from kubani.nexus.orchestrator.worker import get_temporal_settings

        custom_host = "temporal.example.com:7233"
        
        with patch.dict(os.environ, {"TEMPORAL_HOST": custom_host}):
            host, namespace = get_temporal_settings()

            assert host == custom_host
            assert namespace == "nexus"  # Default namespace

    def test_get_temporal_settings_with_custom_namespace(self):
        """
        Test that get_temporal_settings reads TEMPORAL_NAMESPACE from environment.
        
        Requirements: 9.1
        """
        from kubani.nexus.orchestrator.worker import get_temporal_settings

        custom_namespace = "production"
        
        with patch.dict(os.environ, {"TEMPORAL_NAMESPACE": custom_namespace}):
            host, namespace = get_temporal_settings()

            assert host == "localhost:7233"  # Default host
            assert namespace == custom_namespace

    def test_get_temporal_settings_with_both_custom(self):
        """
        Test that get_temporal_settings reads both TEMPORAL_HOST and
        TEMPORAL_NAMESPACE from environment.
        
        Requirements: 9.1
        """
        from kubani.nexus.orchestrator.worker import get_temporal_settings

        custom_host = "temporal.cluster.local:7233"
        custom_namespace = "staging"
        
        with patch.dict(
            os.environ,
            {
                "TEMPORAL_HOST": custom_host,
                "TEMPORAL_NAMESPACE": custom_namespace,
            },
        ):
            host, namespace = get_temporal_settings()

            assert host == custom_host
            assert namespace == custom_namespace

    @pytest.mark.asyncio
    async def test_run_worker_uses_environment_settings(self):
        """
        Test that run_worker uses the settings from get_temporal_settings.
        
        Requirements: 9.1
        """
        from kubani.nexus.orchestrator.worker import run_worker

        custom_host = "temporal.prod.example.com:7233"
        custom_namespace = "production-nexus"

        # Mock the Temporal Client and Worker
        mock_client = AsyncMock()
        mock_worker = AsyncMock()
        mock_worker.run = AsyncMock(side_effect=KeyboardInterrupt)  # Exit immediately

        with patch.dict(
            os.environ,
            {
                "TEMPORAL_HOST": custom_host,
                "TEMPORAL_NAMESPACE": custom_namespace,
            },
        ), patch(
            "kubani.nexus.orchestrator.worker.Client.connect",
            AsyncMock(return_value=mock_client),
        ) as mock_connect, patch(
            "kubani.nexus.orchestrator.worker.Worker",
            return_value=mock_worker,
        ):
            # Run the worker (will exit immediately due to KeyboardInterrupt)
            await run_worker()

            # Verify Client.connect was called with the correct settings
            mock_connect.assert_called_once_with(
                custom_host,
                namespace=custom_namespace,
            )

    @pytest.mark.asyncio
    async def test_start_nexus_workflow_uses_environment_settings(self):
        """
        Test that start_nexus_workflow uses environment settings for connection.
        
        Requirements: 9.1
        """
        from kubani.nexus.orchestrator.worker import start_nexus_workflow

        custom_host = "temporal.staging.example.com:7233"
        custom_namespace = "staging-nexus"

        # Mock the Temporal Client
        mock_client = AsyncMock()
        mock_handle = AsyncMock()
        mock_client.start_workflow = AsyncMock(return_value=mock_handle)

        with patch.dict(
            os.environ,
            {
                "TEMPORAL_HOST": custom_host,
                "TEMPORAL_NAMESPACE": custom_namespace,
            },
        ), patch(
            "kubani.nexus.orchestrator.worker.Client.connect",
            AsyncMock(return_value=mock_client),
        ) as mock_connect:
            # Start a workflow
            workflow_id = await start_nexus_workflow(
                user_id="test-user",
                conversation_id="test-conv",
            )

            # Verify Client.connect was called with the correct settings
            mock_connect.assert_called_once_with(
                custom_host,
                namespace=custom_namespace,
            )

            # Verify workflow was started
            assert workflow_id == "nexus-test-user"
