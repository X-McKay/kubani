"""
Plugin Registry - Central registry for plugin discovery.

Provides a searchable registry of available plugins with
metadata, capabilities, and versioning information.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class PluginRegistryEntry:
    """Entry in the plugin registry."""

    name: str
    description: str
    type: str  # "mcp", "python", "remote"
    version: str
    author: str = ""
    license: str = ""
    capabilities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source: str = ""
    documentation_url: str = ""
    repository_url: str = ""
    downloads: int = 0
    rating: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


class PluginRegistry:
    """
    Central registry for plugin discovery and management.

    Features:
    - Search plugins by name, capability, or tags
    - Version management
    - Rating and download tracking
    - Integration with remote registries
    """

    def __init__(self):
        self._entries: dict[str, PluginRegistryEntry] = {}
        self._capability_index: dict[str, list[str]] = {}
        self._tag_index: dict[str, list[str]] = {}

    def _rebuild_indexes(self) -> None:
        """Rebuild search indexes."""
        self._capability_index = {}
        self._tag_index = {}

        for name, entry in self._entries.items():
            for cap in entry.capabilities:
                if cap not in self._capability_index:
                    self._capability_index[cap] = []
                self._capability_index[cap].append(name)

            for tag in entry.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = []
                self._tag_index[tag].append(name)

    def register(self, entry: PluginRegistryEntry) -> PluginRegistryEntry:
        """
        Register a plugin in the registry.

        Args:
            entry: Plugin registry entry

        Returns:
            The registered entry
        """
        self._entries[entry.name] = entry
        self._rebuild_indexes()
        logger.info(f"Registered plugin: {entry.name} v{entry.version}")
        return entry

    def unregister(self, name: str) -> bool:
        """
        Remove a plugin from the registry.

        Args:
            name: Plugin name

        Returns:
            True if removed
        """
        if name in self._entries:
            del self._entries[name]
            self._rebuild_indexes()
            return True
        return False

    def get(self, name: str) -> Optional[PluginRegistryEntry]:
        """Get a plugin by name."""
        return self._entries.get(name)

    def list_all(self) -> list[PluginRegistryEntry]:
        """List all registered plugins."""
        return list(self._entries.values())

    def search(
        self,
        query: Optional[str] = None,
        capability: Optional[str] = None,
        tag: Optional[str] = None,
        plugin_type: Optional[str] = None,
    ) -> list[PluginRegistryEntry]:
        """
        Search for plugins.

        Args:
            query: Text search in name and description
            capability: Filter by capability
            tag: Filter by tag
            plugin_type: Filter by type

        Returns:
            List of matching plugins
        """
        results = list(self._entries.values())

        # Filter by capability
        if capability:
            cap_names = self._capability_index.get(capability, [])
            results = [e for e in results if e.name in cap_names]

        # Filter by tag
        if tag:
            tag_names = self._tag_index.get(tag, [])
            results = [e for e in results if e.name in tag_names]

        # Filter by type
        if plugin_type:
            results = [e for e in results if e.type == plugin_type]

        # Text search
        if query:
            query_lower = query.lower()
            results = [
                e
                for e in results
                if query_lower in e.name.lower() or query_lower in e.description.lower()
            ]

        return results

    def find_by_capability(self, capability: str) -> list[PluginRegistryEntry]:
        """Find plugins that provide a capability."""
        names = self._capability_index.get(capability, [])
        return [self._entries[n] for n in names if n in self._entries]

    def find_by_tag(self, tag: str) -> list[PluginRegistryEntry]:
        """Find plugins with a specific tag."""
        names = self._tag_index.get(tag, [])
        return [self._entries[n] for n in names if n in self._entries]

    def get_popular(self, limit: int = 10) -> list[PluginRegistryEntry]:
        """Get most popular plugins by downloads."""
        sorted_entries = sorted(
            self._entries.values(),
            key=lambda e: e.downloads,
            reverse=True,
        )
        return sorted_entries[:limit]

    def get_top_rated(self, limit: int = 10) -> list[PluginRegistryEntry]:
        """Get top-rated plugins."""
        sorted_entries = sorted(
            self._entries.values(),
            key=lambda e: e.rating,
            reverse=True,
        )
        return sorted_entries[:limit]

    def get_recent(self, limit: int = 10) -> list[PluginRegistryEntry]:
        """Get recently updated plugins."""
        sorted_entries = sorted(
            self._entries.values(),
            key=lambda e: e.updated_at,
            reverse=True,
        )
        return sorted_entries[:limit]

    async def sync_from_remote(self, registry_url: str) -> int:
        """
        Sync plugins from a remote registry.

        Args:
            registry_url: URL of the remote registry

        Returns:
            Number of plugins synced
        """
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{registry_url}/plugins") as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch remote registry: {response.status}")
                        return 0

                    data = await response.json()

            count = 0
            for plugin_data in data.get("plugins", []):
                entry = PluginRegistryEntry(
                    name=plugin_data["name"],
                    description=plugin_data.get("description", ""),
                    type=plugin_data.get("type", "mcp"),
                    version=plugin_data.get("version", "1.0.0"),
                    author=plugin_data.get("author", ""),
                    capabilities=plugin_data.get("capabilities", []),
                    tags=plugin_data.get("tags", []),
                    source=plugin_data.get("source", ""),
                    downloads=plugin_data.get("downloads", 0),
                    rating=plugin_data.get("rating", 0.0),
                )
                self.register(entry)
                count += 1

            logger.info(f"Synced {count} plugins from remote registry")
            return count

        except Exception as e:
            logger.error(f"Failed to sync from remote registry: {e}")
            return 0

    def export_to_dict(self) -> dict[str, Any]:
        """Export registry to dictionary format."""
        return {
            "plugins": [
                {
                    "name": e.name,
                    "description": e.description,
                    "type": e.type,
                    "version": e.version,
                    "author": e.author,
                    "capabilities": e.capabilities,
                    "tags": e.tags,
                    "source": e.source,
                    "downloads": e.downloads,
                    "rating": e.rating,
                }
                for e in self._entries.values()
            ]
        }


# Built-in plugins that come with Kubani
BUILTIN_PLUGINS = [
    PluginRegistryEntry(
        name="kubernetes-mcp",
        description="Kubernetes cluster management via MCP",
        type="mcp",
        version="1.0.0",
        author="Kubani Team",
        capabilities=["kubernetes", "pods", "deployments", "services"],
        tags=["kubernetes", "infrastructure", "core"],
    ),
    PluginRegistryEntry(
        name="discord-mcp",
        description="Discord integration for notifications",
        type="mcp",
        version="1.0.0",
        author="Kubani Team",
        capabilities=["notifications", "discord", "messaging"],
        tags=["notifications", "discord"],
    ),
    PluginRegistryEntry(
        name="prometheus-mcp",
        description="Prometheus metrics querying",
        type="mcp",
        version="1.0.0",
        author="Kubani Team",
        capabilities=["metrics", "prometheus", "monitoring"],
        tags=["monitoring", "metrics"],
    ),
]


def get_default_registry() -> PluginRegistry:
    """Get a registry with built-in plugins."""
    registry = PluginRegistry()
    for plugin in BUILTIN_PLUGINS:
        registry.register(plugin)
    return registry
