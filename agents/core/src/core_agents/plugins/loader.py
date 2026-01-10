"""
Plugin Loaders - Load plugins from various sources.

Provides different loader implementations for:
- MCP servers (stdio, SSE, HTTP)
- Python modules
- Remote plugins
- Directory-based plugins
"""

import asyncio
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from core_agents.plugins.manager import PluginConfig

logger = logging.getLogger(__name__)


class PluginLoader(ABC):
    """Base class for plugin loaders."""

    @abstractmethod
    async def load(self, config: PluginConfig) -> dict[str, Any]:
        """
        Load a plugin.

        Args:
            config: Plugin configuration

        Returns:
            Dict with version, tools, and metadata
        """
        pass

    @abstractmethod
    async def unload(self, config: PluginConfig) -> None:
        """
        Unload a plugin.

        Args:
            config: Plugin configuration
        """
        pass


class MCPPluginLoader(PluginLoader):
    """
    Loader for MCP server plugins.

    Supports:
    - stdio: Local process with stdin/stdout communication
    - sse: Server-Sent Events over HTTP
    - http: HTTP/Streamable HTTP transport
    """

    def __init__(self):
        self._processes: dict[str, subprocess.Popen] = {}
        self._clients: dict[str, Any] = {}

    async def load(self, config: PluginConfig) -> dict[str, Any]:
        """Load an MCP server plugin."""
        transport = config.config.get("transport", "stdio")

        if transport == "stdio":
            return await self._load_stdio(config)
        elif transport in ("sse", "http"):
            return await self._load_http(config)
        else:
            raise ValueError(f"Unknown MCP transport: {transport}")

    async def _load_stdio(self, config: PluginConfig) -> dict[str, Any]:
        """Load an MCP server via stdio transport."""
        command = config.config.get("command")
        args = config.config.get("args", [])
        env = {**os.environ, **config.config.get("env", {})}

        if not command:
            raise ValueError("MCP stdio plugin requires 'command' in config")

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            # Create server parameters
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env,
            )

            # Connect to server
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    # Initialize
                    await session.initialize()

                    # List tools
                    tools_result = await session.list_tools()
                    tools = [
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "inputSchema": tool.inputSchema or {},
                        }
                        for tool in tools_result.tools
                    ]

                    return {
                        "version": "1.0.0",
                        "tools": tools,
                        "metadata": {"transport": "stdio"},
                    }

        except ImportError:
            logger.warning("MCP package not installed, using mock loader")
            return await self._mock_load(config)

    async def _load_http(self, config: PluginConfig) -> dict[str, Any]:
        """Load an MCP server via HTTP transport."""
        url = config.config.get("url") or config.source

        if not url:
            raise ValueError("MCP HTTP plugin requires 'url' in config")

        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            # Ensure URL ends with /mcp
            if not url.endswith("/mcp"):
                url = f"{url}/mcp"

            async with streamablehttp_client(url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    tools_result = await session.list_tools()
                    tools = [
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "inputSchema": tool.inputSchema or {},
                        }
                        for tool in tools_result.tools
                    ]

                    return {
                        "version": "1.0.0",
                        "tools": tools,
                        "metadata": {"transport": "http", "url": url},
                    }

        except ImportError:
            logger.warning("MCP package not installed, using mock loader")
            return await self._mock_load(config)

    async def _mock_load(self, config: PluginConfig) -> dict[str, Any]:
        """Mock loader for when MCP is not available."""
        return {
            "version": "mock",
            "tools": [],
            "metadata": {"mock": True},
        }

    async def unload(self, config: PluginConfig) -> None:
        """Unload an MCP plugin."""
        # Clean up any running processes
        if config.name in self._processes:
            proc = self._processes.pop(config.name)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

        # Clean up clients
        if config.name in self._clients:
            del self._clients[config.name]


class DirectoryPluginLoader(PluginLoader):
    """
    Loader for directory-based plugins.

    Expects plugin directories with:
    - plugin.yaml: Plugin configuration
    - Optional: Python modules, MCP server configs
    """

    def __init__(self):
        self._mcp_loader = MCPPluginLoader()

    async def load(self, config: PluginConfig) -> dict[str, Any]:
        """Load a plugin from a directory."""
        plugin_dir = Path(config.source)

        if not plugin_dir.exists():
            raise ValueError(f"Plugin directory not found: {plugin_dir}")

        # Check for MCP server config
        mcp_config = plugin_dir / "mcp.yaml"
        if mcp_config.exists():
            import yaml

            with open(mcp_config) as f:
                mcp_data = yaml.safe_load(f)

            mcp_plugin_config = PluginConfig(
                name=config.name,
                type="mcp",
                source=str(plugin_dir),
                config=mcp_data,
            )
            return await self._mcp_loader.load(mcp_plugin_config)

        # Check for Python module
        init_file = plugin_dir / "__init__.py"
        if init_file.exists():
            return await self._load_python_module(config, plugin_dir)

        # Return empty plugin
        return {
            "version": "1.0.0",
            "tools": [],
            "metadata": {"directory": str(plugin_dir)},
        }

    async def _load_python_module(
        self,
        config: PluginConfig,
        plugin_dir: Path,
    ) -> dict[str, Any]:
        """Load a Python module plugin."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            config.name,
            plugin_dir / "__init__.py",
        )
        if spec is None or spec.loader is None:
            raise ValueError(f"Could not load Python module from {plugin_dir}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Look for standard exports
        tools = getattr(module, "TOOLS", [])
        version = getattr(module, "VERSION", "1.0.0")
        metadata = getattr(module, "METADATA", {})

        return {
            "version": version,
            "tools": tools,
            "metadata": metadata,
        }

    async def unload(self, config: PluginConfig) -> None:
        """Unload a directory plugin."""
        await self._mcp_loader.unload(config)


class RemotePluginLoader(PluginLoader):
    """
    Loader for remote plugins.

    Fetches plugin configurations from a remote registry
    and loads them dynamically.
    """

    def __init__(self, registry_url: Optional[str] = None):
        self.registry_url = registry_url or os.getenv(
            "PLUGIN_REGISTRY_URL",
            "https://registry.kubani.io/plugins",
        )
        self._mcp_loader = MCPPluginLoader()

    async def load(self, config: PluginConfig) -> dict[str, Any]:
        """Load a plugin from remote registry."""
        import aiohttp

        # Fetch plugin manifest from registry
        async with aiohttp.ClientSession() as session:
            url = f"{self.registry_url}/{config.name}/manifest.json"
            async with session.get(url) as response:
                if response.status != 200:
                    raise ValueError(f"Plugin not found in registry: {config.name}")

                manifest = await response.json()

        # Load based on manifest type
        plugin_type = manifest.get("type", "mcp")

        if plugin_type == "mcp":
            mcp_config = PluginConfig(
                name=config.name,
                type="mcp",
                source=manifest.get("url", ""),
                config=manifest.get("config", {}),
            )
            return await self._mcp_loader.load(mcp_config)

        return {
            "version": manifest.get("version", "1.0.0"),
            "tools": manifest.get("tools", []),
            "metadata": manifest,
        }

    async def unload(self, config: PluginConfig) -> None:
        """Unload a remote plugin."""
        await self._mcp_loader.unload(config)
