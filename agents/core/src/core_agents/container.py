"""Service container for dependency injection.

Replaces global singletons with a lightweight container pattern.
Enables easy testing via container.override() and container.reset().
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class Singleton(Generic[T]):
    """Lazy singleton with optional async initialization."""

    def __init__(
        self,
        factory: Callable[[], T] | Callable[[], Awaitable[T]],
        *,
        async_init: bool = False,
    ):
        self._factory = factory
        self._async_init = async_init
        self._instance: T | None = None
        self._lock = asyncio.Lock()

    def get(self) -> T:
        """Get the singleton instance (sync)."""
        if self._instance is None:
            if self._async_init:
                raise RuntimeError("Use get_async() for async-initialized singletons")
            self._instance = self._factory()
        return self._instance

    async def get_async(self) -> T:
        """Get the singleton instance (async-safe)."""
        if self._instance is None:
            async with self._lock:
                if self._instance is None:
                    if self._async_init:
                        self._instance = await self._factory()
                    else:
                        self._instance = self._factory()
        return self._instance

    def reset(self) -> None:
        """Reset the singleton (for testing)."""
        self._instance = None

    def override(self, instance: T) -> None:
        """Override with a specific instance (for testing)."""
        self._instance = instance


class ServiceContainer:
    """
    Lightweight service container for managing dependencies.

    Usage:
        container = ServiceContainer()

        # Register services
        container.register("config", lambda: get_config())
        container.register("mcp_client", create_mcp_client, async_init=True)

        # Get services
        config = container.get("config")
        client = await container.get_async("mcp_client")

        # Testing
        container.override("config", mock_config)
        container.reset_all()
    """

    def __init__(self):
        self._services: dict[str, Singleton] = {}

    def register(
        self,
        name: str,
        factory: Callable[[], Any] | Callable[[], Awaitable[Any]],
        *,
        async_init: bool = False,
    ) -> None:
        """Register a service factory."""
        self._services[name] = Singleton(factory, async_init=async_init)

    def get(self, name: str) -> Any:
        """Get a service instance (sync)."""
        if name not in self._services:
            raise KeyError(f"Service not registered: {name}")
        return self._services[name].get()

    async def get_async(self, name: str) -> Any:
        """Get a service instance (async-safe)."""
        if name not in self._services:
            raise KeyError(f"Service not registered: {name}")
        return await self._services[name].get_async()

    def override(self, name: str, instance: Any) -> None:
        """Override a service with a specific instance (for testing)."""
        if name not in self._services:
            # Create a dummy singleton for the override
            self._services[name] = Singleton(lambda: None)
        self._services[name].override(instance)

    def reset(self, name: str) -> None:
        """Reset a specific service."""
        if name in self._services:
            self._services[name].reset()

    def reset_all(self) -> None:
        """Reset all services (for testing cleanup)."""
        for service in self._services.values():
            service.reset()

    @asynccontextmanager
    async def test_context(self, **overrides: Any):
        """Context manager for test isolation."""
        for name, instance in overrides.items():
            self.override(name, instance)
        try:
            yield self
        finally:
            self.reset_all()


# Global container instance
_container: ServiceContainer | None = None


def get_container() -> ServiceContainer:
    """Get the global service container."""
    global _container
    if _container is None:
        _container = ServiceContainer()
        _register_default_services(_container)
    return _container


def _register_default_services(container: ServiceContainer) -> None:
    """Register default services."""
    # Config (sync)
    container.register("config", lambda: _lazy_get_config())

    # MCP Client (async)
    container.register("mcp_client", _lazy_create_mcp_client, async_init=True)

    # Plugin Manager (sync with async init)
    container.register("plugin_manager", lambda: _lazy_get_plugin_manager())


def _lazy_get_config():
    """Lazy config loader to avoid circular imports."""
    from core_agents.config_unified import get_config

    return get_config()


async def _lazy_create_mcp_client():
    """Lazy MCP client factory."""
    try:
        from core_agents.mcp.client import create_mcp_client

        return await create_mcp_client()
    except ImportError:
        return None


def _lazy_get_plugin_manager():
    """Lazy plugin manager factory."""
    try:
        from core_agents.plugins.manager import get_plugin_manager

        return get_plugin_manager()
    except ImportError:
        return None


# Convenience functions
def get_config_from_container():
    """Get config via container."""
    return get_container().get("config")


async def get_mcp_client_from_container():
    """Get MCP client via container."""
    return await get_container().get_async("mcp_client")
