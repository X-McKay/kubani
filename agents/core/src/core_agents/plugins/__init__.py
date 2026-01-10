"""
Dynamic MCP Plugin Architecture for Kubani.

This module implements Recommendation #9 from the comprehensive improvement plan:
"Create a Dynamic MCP Plugin Architecture"

The plugin system allows:
1. Hot-loading of MCP servers without code changes
2. Plugin discovery from multiple sources (directory, registry, remote)
3. Lifecycle management (load, unload, reload)
4. Capability-based plugin selection

Usage:
    from core_agents.plugins import PluginManager, PluginConfig

    # Create plugin manager
    manager = PluginManager()

    # Load plugins from directory
    await manager.load_plugins_from_directory("/path/to/plugins")

    # Get tools from a specific plugin
    tools = await manager.get_plugin_tools("kubernetes-mcp")

    # Hot-reload a plugin
    await manager.reload_plugin("kubernetes-mcp")
"""

from core_agents.plugins.manager import (
    PluginManager,
    PluginConfig,
    PluginInfo,
    PluginState,
    get_plugin_manager,
)
from core_agents.plugins.loader import (
    PluginLoader,
    MCPPluginLoader,
    DirectoryPluginLoader,
)
from core_agents.plugins.registry import (
    PluginRegistry,
    PluginRegistryEntry,
)

__all__ = [
    # Manager
    "PluginManager",
    "PluginConfig",
    "PluginInfo",
    "PluginState",
    "get_plugin_manager",
    # Loaders
    "PluginLoader",
    "MCPPluginLoader",
    "DirectoryPluginLoader",
    # Registry
    "PluginRegistry",
    "PluginRegistryEntry",
]
