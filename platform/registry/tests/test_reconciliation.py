"""Tests for MCP server reconciliation service."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from kubani_registry.db import MCPServer
from kubani_registry.services.reconciliation import ReconciliationService

pytestmark = pytest.mark.asyncio


class TestReconciliationService:
    """Test MCP server reconciliation service."""

    @pytest.fixture
    async def reconciliation_service(self):
        """Create a reconciliation service instance."""
        service = ReconciliationService()
        # Don't initialize Kubernetes client for unit tests
        return service

    @pytest.fixture
    async def mock_k8s_client(self):
        """Create a mock Kubernetes client."""
        mock_client = AsyncMock()
        mock_deployment = MagicMock()
        mock_deployment.metadata.name = "discord-mcp-server"
        mock_deployment.metadata.labels = {
            "mcp.kubani.io/server": "true",
            "mcp.kubani.io/server-id": "discord-mcp",
        }

        mock_list = MagicMock()
        mock_list.items = [mock_deployment]
        mock_client.list_deployment_for_all_namespaces.return_value = mock_list

        return mock_client

    async def test_get_mcp_deployments_no_k8s_client(self, reconciliation_service):
        """Should return empty set when Kubernetes client not initialized."""
        result = await reconciliation_service.get_mcp_deployments()
        assert result == set()

    async def test_get_mcp_deployments_with_server_id_label(
        self, reconciliation_service, mock_k8s_client
    ):
        """Should extract server ID from deployment labels."""
        reconciliation_service.k8s_apps_v1 = mock_k8s_client

        result = await reconciliation_service.get_mcp_deployments()
        assert result == {"discord-mcp"}

    async def test_get_mcp_deployments_fallback_to_name(self, reconciliation_service):
        """Should fall back to deployment name if server-id label not present."""
        mock_client = AsyncMock()
        mock_deployment = MagicMock()
        mock_deployment.metadata.name = "memory-mcp-server"
        mock_deployment.metadata.labels = {"mcp.kubani.io/server": "true"}

        mock_list = MagicMock()
        mock_list.items = [mock_deployment]
        mock_client.list_deployment_for_all_namespaces.return_value = mock_list

        reconciliation_service.k8s_apps_v1 = mock_client

        result = await reconciliation_service.get_mcp_deployments()
        assert result == {"memory-mcp"}

    async def test_reconcile_marks_missing_servers_inactive(
        self, reconciliation_service, async_session
    ):
        """Should mark servers as inactive if not found in Kubernetes."""
        # Create a server in the database
        server = MCPServer(
            id="missing-server",
            name="Missing Server",
            transport="sse",
            connection_config={"url": "http://missing:8000"},
            status="active",
        )
        async_session.add(server)
        await async_session.commit()

        # Mock Kubernetes to return no deployments
        reconciliation_service.k8s_apps_v1 = AsyncMock()
        mock_list = MagicMock()
        mock_list.items = []
        reconciliation_service.k8s_apps_v1.list_deployment_for_all_namespaces.return_value = (
            mock_list
        )

        # Mock get_session_factory to return our test session
        with patch(
            "kubani_registry.services.reconciliation.get_session_factory"
        ) as mock_factory:
            mock_factory.return_value = lambda: async_session

            await reconciliation_service.reconcile()

        # Verify server was marked inactive
        await async_session.refresh(server)
        assert server.status == "inactive"

    async def test_reconcile_removes_old_inactive_servers(
        self, reconciliation_service, async_session
    ):
        """Should remove servers inactive for more than 24 hours."""
        # Create an old inactive server
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        server = MCPServer(
            id="old-inactive-server",
            name="Old Inactive Server",
            transport="sse",
            connection_config={"url": "http://old:8000"},
            status="inactive",
            updated_at=old_time,
        )
        async_session.add(server)
        await async_session.commit()

        # Mock Kubernetes to return no deployments
        reconciliation_service.k8s_apps_v1 = AsyncMock()
        mock_list = MagicMock()
        mock_list.items = []
        reconciliation_service.k8s_apps_v1.list_deployment_for_all_namespaces.return_value = (
            mock_list
        )

        # Mock get_session_factory to return our test session
        with patch(
            "kubani_registry.services.reconciliation.get_session_factory"
        ) as mock_factory:
            mock_factory.return_value = lambda: async_session

            await reconciliation_service.reconcile()

        # Verify server was removed
        result = await async_session.execute(
            select(MCPServer).where(MCPServer.id == "old-inactive-server")
        )
        assert result.scalar_one_or_none() is None

    async def test_reconcile_reactivates_found_servers(
        self, reconciliation_service, async_session
    ):
        """Should reactivate servers that are found in Kubernetes."""
        # Create an inactive server
        server = MCPServer(
            id="reactivate-server",
            name="Reactivate Server",
            transport="sse",
            connection_config={"url": "http://reactivate:8000"},
            status="inactive",
        )
        async_session.add(server)
        await async_session.commit()

        # Mock Kubernetes to return this deployment
        mock_client = AsyncMock()
        mock_deployment = MagicMock()
        mock_deployment.metadata.name = "reactivate-server"
        mock_deployment.metadata.labels = {
            "mcp.kubani.io/server": "true",
            "mcp.kubani.io/server-id": "reactivate-server",
        }

        mock_list = MagicMock()
        mock_list.items = [mock_deployment]
        mock_client.list_deployment_for_all_namespaces.return_value = mock_list

        reconciliation_service.k8s_apps_v1 = mock_client

        # Mock get_session_factory to return our test session
        with patch(
            "kubani_registry.services.reconciliation.get_session_factory"
        ) as mock_factory:
            mock_factory.return_value = lambda: async_session

            await reconciliation_service.reconcile()

        # Verify server was reactivated
        await async_session.refresh(server)
        assert server.status == "active"

    async def test_reconcile_handles_k8s_errors(self, reconciliation_service, async_session):
        """Should handle Kubernetes API errors gracefully."""
        # Mock Kubernetes to raise an error
        reconciliation_service.k8s_apps_v1 = AsyncMock()
        reconciliation_service.k8s_apps_v1.list_deployment_for_all_namespaces.side_effect = (
            Exception("K8s API error")
        )

        # Mock get_session_factory to return our test session
        with patch(
            "kubani_registry.services.reconciliation.get_session_factory"
        ) as mock_factory:
            mock_factory.return_value = lambda: async_session

            # Should not raise exception
            await reconciliation_service.reconcile()

    async def test_reconcile_preserves_active_servers(
        self, reconciliation_service, async_session
    ):
        """Should not modify servers that exist in Kubernetes."""
        # Create an active server
        server = MCPServer(
            id="active-server",
            name="Active Server",
            transport="sse",
            connection_config={"url": "http://active:8000"},
            status="healthy",
        )
        async_session.add(server)
        await async_session.commit()

        original_updated_at = server.updated_at

        # Mock Kubernetes to return this deployment
        mock_client = AsyncMock()
        mock_deployment = MagicMock()
        mock_deployment.metadata.name = "active-server"
        mock_deployment.metadata.labels = {
            "mcp.kubani.io/server": "true",
            "mcp.kubani.io/server-id": "active-server",
        }

        mock_list = MagicMock()
        mock_list.items = [mock_deployment]
        mock_client.list_deployment_for_all_namespaces.return_value = mock_list

        reconciliation_service.k8s_apps_v1 = mock_client

        # Mock get_session_factory to return our test session
        with patch(
            "kubani_registry.services.reconciliation.get_session_factory"
        ) as mock_factory:
            mock_factory.return_value = lambda: async_session

            await reconciliation_service.reconcile()

        # Verify server status unchanged
        await async_session.refresh(server)
        assert server.status == "healthy"
        # updated_at should not change for servers that remain active
        assert server.updated_at == original_updated_at
