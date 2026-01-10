"""
Plugin Manager - Core plugin lifecycle management.

Handles loading, unloading, and managing MCP plugins dynamically.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PluginState(str, Enum):
    """Plugin lifecycle states."""

    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"
    UNLOADING = "unloading"


@dataclass
class PluginConfig:
    """Configuration for a plugin."""

    name: str
    type: str  # "mcp", "python", "remote"
    source: str  # Path, URL, or module name
    enabled: bool = True
    auto_reload: bool = False
    capabilities: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginInfo:
    """Runtime information about a loaded plugin."""

    name: str
    config: PluginConfig
    state: PluginState = PluginState.UNLOADED
    version: str = "unknown"
    tools: list[dict[str, Any]] = field(default_factory=list)
    loaded_at: datetime | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PluginManager:
    """
    Manages the lifecycle of MCP plugins.

    Features:
    - Hot-loading and unloading of plugins
    - Plugin discovery from multiple sources
    - Capability-based plugin selection
    - Health monitoring and auto-recovery
    """

    def __init__(self):
        self._plugins: dict[str, PluginInfo] = {}
        self._loaders: dict[str, PluginLoader] = {}
        self._lock = asyncio.Lock()

    async def register_loader(self, plugin_type: str, loader: "PluginLoader") -> None:
        """Register a loader for a plugin type."""
        self._loaders[plugin_type] = loader
        logger.info(f"Registered plugin loader for type: {plugin_type}")

    async def load_plugin(self, config: PluginConfig) -> PluginInfo:
        """
        Load a plugin from configuration.

        Args:
            config: Plugin configuration

        Returns:
            PluginInfo with loaded plugin details
        """
        async with self._lock:
            # Check if already loaded
            if config.name in self._plugins:
                existing = self._plugins[config.name]
                if existing.state == PluginState.LOADED:
                    logger.info(f"Plugin already loaded: {config.name}")
                    return existing

            # Create plugin info
            info = PluginInfo(
                name=config.name,
                config=config,
                state=PluginState.LOADING,
            )
            self._plugins[config.name] = info

            try:
                # Get appropriate loader
                loader = self._loaders.get(config.type)
                if not loader:
                    raise ValueError(f"No loader for plugin type: {config.type}")

                # Load the plugin
                result = await loader.load(config)

                # Update info
                info.state = PluginState.LOADED
                info.version = result.get("version", "unknown")
                info.tools = result.get("tools", [])
                info.loaded_at = datetime.now(UTC)
                info.metadata = result.get("metadata", {})

                logger.info(
                    f"Loaded plugin: {config.name} "
                    f"(version={info.version}, tools={len(info.tools)})"
                )

            except Exception as e:
                info.state = PluginState.ERROR
                info.error = str(e)
                logger.error(f"Failed to load plugin {config.name}: {e}")

            return info

    async def unload_plugin(self, name: str) -> bool:
        """
        Unload a plugin.

        Args:
            name: Plugin name

        Returns:
            True if unloaded successfully
        """
        async with self._lock:
            if name not in self._plugins:
                return False

            info = self._plugins[name]
            info.state = PluginState.UNLOADING

            try:
                loader = self._loaders.get(info.config.type)
                if loader:
                    await loader.unload(info.config)

                info.state = PluginState.UNLOADED
                info.tools = []
                info.loaded_at = None

                logger.info(f"Unloaded plugin: {name}")
                return True

            except Exception as e:
                info.state = PluginState.ERROR
                info.error = str(e)
                logger.error(f"Failed to unload plugin {name}: {e}")
                return False

    async def reload_plugin(self, name: str) -> PluginInfo:
        """
        Reload a plugin (unload then load).

        Args:
            name: Plugin name

        Returns:
            Updated PluginInfo
        """
        if name not in self._plugins:
            raise ValueError(f"Plugin not found: {name}")

        config = self._plugins[name].config

        await self.unload_plugin(name)
        return await self.load_plugin(config)

    async def get_plugin(self, name: str) -> PluginInfo | None:
        """Get plugin info by name."""
        return self._plugins.get(name)

    async def list_plugins(self) -> list[PluginInfo]:
        """List all plugins."""
        return list(self._plugins.values())

    async def get_plugin_tools(self, name: str) -> list[dict[str, Any]]:
        """Get tools from a specific plugin."""
        info = self._plugins.get(name)
        if info and info.state == PluginState.LOADED:
            return info.tools
        return []

    async def get_all_tools(self) -> list[dict[str, Any]]:
        """Get tools from all loaded plugins."""
        tools = []
        for info in self._plugins.values():
            if info.state == PluginState.LOADED:
                tools.extend(info.tools)
        return tools

    async def find_plugins_by_capability(self, capability: str) -> list[PluginInfo]:
        """Find plugins that provide a specific capability."""
        return [
            info
            for info in self._plugins.values()
            if info.state == PluginState.LOADED and capability in info.config.capabilities
        ]

    async def load_plugins_from_directory(self, directory: str | Path) -> list[PluginInfo]:
        """
        Load all plugins from a directory.

        Args:
            directory: Directory containing plugin configurations

        Returns:
            List of loaded PluginInfo objects
        """
        from core_agents.plugins.loader import DirectoryPluginLoader

        directory = Path(directory)
        if not directory.exists():
            logger.warning(f"Plugin directory not found: {directory}")
            return []

        # Register directory loader if not present
        if "directory" not in self._loaders:
            await self.register_loader("directory", DirectoryPluginLoader())

        loaded = []
        for config_file in directory.glob("*.yaml"):
            try:
                import yaml

                with open(config_file) as f:
                    data = yaml.safe_load(f)

                config = PluginConfig(
                    name=data.get("name", config_file.stem),
                    type=data.get("type", "mcp"),
                    source=data.get("source", ""),
                    enabled=data.get("enabled", True),
                    capabilities=data.get("capabilities", []),
                    config=data.get("config", {}),
                )

                if config.enabled:
                    info = await self.load_plugin(config)
                    loaded.append(info)

            except Exception as e:
                logger.error(f"Failed to load plugin config {config_file}: {e}")

        return loaded

    async def health_check(self) -> dict[str, Any]:
        """Check health of all plugins."""
        results = {}
        for name, info in self._plugins.items():
            results[name] = {
                "state": info.state.value,
                "healthy": info.state == PluginState.LOADED,
                "error": info.error,
                "tools": len(info.tools),
            }
        return results


# Singleton instance
_plugin_manager: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager


# Import PluginLoader for type hints
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core_agents.plugins.loader import PluginLoader
