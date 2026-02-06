"""Tests for registry integration utilities."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from kubani.framework.mcp.server.registry import RegistryClient


class TestRegistryClient:
    """Tests for RegistryClient."""

    def test_initialization(self):
        """Test registry client initialization."""
        client = RegistryClient(
            registry_url="http://registry:8000",
            server_id="test-server",
        )

        assert client.registry_url == "http://registry:8000"
        assert client.server_id == "test-server"
        assert not client._registered

    @pytest.mark.asyncio
    async def test_register_success(self):
        """Test successful registration."""
        client = RegistryClient(
            registry_url="http://registry:8000",
            server_id="test-server",
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await client.register(
                name="Test Server",
                description="Test description",
                transport="sse",
                connection_config={"url": "http://test:8080"},
                capabilities=["tool1", "tool2"],
            )

            assert result is True
            assert client._registered is True
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_failure(self):
        """Test registration failure."""
        client = RegistryClient(
            registry_url="http://registry:8000",
            server_id="test-server",
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=Exception("Connection failed"))
            mock_client_class.return_value = mock_client

            result = await client.register(
                name="Test Server",
                description="Test description",
                transport="sse",
                connection_config={"url": "http://test:8080"},
                capabilities=["tool1"],
            )

            assert result is False
            assert client._registered is False

    @pytest.mark.asyncio
    async def test_heartbeat_success(self):
        """Test successful heartbeat."""
        client = RegistryClient(
            registry_url="http://registry:8000",
            server_id="test-server",
        )
        client._registered = True

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await client.heartbeat(
                backend_status={"db": "healthy", "cache": "healthy"}
            )

            assert result is True
            mock_client.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_heartbeat_not_registered(self):
        """Test heartbeat when not registered."""
        client = RegistryClient(
            registry_url="http://registry:8000",
            server_id="test-server",
        )

        result = await client.heartbeat()

        assert result is False

    @pytest.mark.asyncio
    async def test_heartbeat_failure(self):
        """Test heartbeat failure."""
        client = RegistryClient(
            registry_url="http://registry:8000",
            server_id="test-server",
        )
        client._registered = True

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(side_effect=Exception("Connection failed"))
            mock_client_class.return_value = mock_client

            result = await client.heartbeat()

            assert result is False

    @pytest.mark.asyncio
    async def test_unregister_success(self):
        """Test successful unregistration."""
        client = RegistryClient(
            registry_url="http://registry:8000",
            server_id="test-server",
        )
        client._registered = True

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await client.unregister()

            assert result is True
            assert client._registered is False
            mock_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_unregister_not_registered(self):
        """Test unregister when not registered."""
        client = RegistryClient(
            registry_url="http://registry:8000",
            server_id="test-server",
        )

        result = await client.unregister()

        assert result is True
