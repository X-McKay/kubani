"""
MCP Server Subprocess Manager.

Handles spawning, health checking, and lifecycle management of MCP servers
for local development. MCP servers connect to cluster backends (Qdrant, Redis,
Neo4j) via Tailscale DNS endpoints.
"""

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# Default ports for each MCP server
DEFAULT_PORTS: dict[str, int] = {
    "memory": 8083,
    "discord": 8084,
    "temporal": 8081,
    "qdrant": 8082,
}

# Script names vary per server - mapping from server name to script command
SERVER_SCRIPTS: dict[str, str] = {
    "memory": "memory-mcp",
    "discord": "discord-mcp-server",
    "temporal": "temporal-mcp",
    "qdrant": "qdrant-mcp",
    "skills": "skills-mcp-server",
}


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""

    name: str
    port: int
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class MCPServerProcess:
    """Tracks a running MCP server process."""

    name: str
    port: int
    process: subprocess.Popen
    url: str
    stderr_path: str | None = None  # Path to stderr log file for debugging


class MCPServerManager:
    """
    Manages MCP server subprocesses for local development.

    Handles:
    - Server startup with health check waiting
    - Environment variable configuration for backends
    - Graceful shutdown of all servers
    """

    def __init__(self):
        self.servers: dict[str, MCPServerProcess] = {}
        self.processes: list[subprocess.Popen] = []
        self._project_root = self._compute_project_root()

    @staticmethod
    def _compute_project_root() -> Path:
        """Find the project root by walking up looking for kubani/ and pyproject.toml."""
        current = Path(__file__).resolve()
        while current != current.parent:
            # Look for kubani directory and pyproject.toml at root
            if (current / "kubani").is_dir() and (current / "pyproject.toml").exists():
                return current
            current = current.parent

        # Fallback: assume we're in kubani/cli/
        return Path(__file__).parent.parent.parent

    def _find_project_root(self) -> Path:
        """Get the cached project root."""
        return self._project_root

    def _get_server_path(self, server_name: str) -> Path:
        """Get the path to an MCP server directory."""
        return self._find_project_root() / "kubani" / "mcp" / "servers" / server_name

    def _get_server_command(self, server_name: str) -> list[str]:
        """Get the command to run an MCP server."""
        script_name = SERVER_SCRIPTS.get(server_name, f"{server_name}-mcp")
        return ["uv", "run", script_name]

    def _build_server_env(self, config: Any) -> dict[str, str]:
        """
        Build environment variables for MCP servers from config.

        Parses service URLs from config and converts them to environment variables
        expected by the MCP servers.
        """
        env = os.environ.copy()

        if config is None:
            return env

        # Extract service URLs from config if available
        services = getattr(config, "services", None)
        if services:
            if hasattr(services, "qdrant_url"):
                env["QDRANT_URL"] = services.qdrant_url
            if hasattr(services, "redis_url"):
                env["REDIS_URL"] = services.redis_url
            if hasattr(services, "neo4j_uri"):
                env["NEO4J_URI"] = services.neo4j_uri
            if hasattr(services, "neo4j_user"):
                env["NEO4J_USER"] = services.neo4j_user
            if hasattr(services, "neo4j_password"):
                env["NEO4J_PASSWORD"] = services.neo4j_password

        # Extract LLM config for embedding services
        llm = getattr(config, "llm", None)
        if llm:
            if hasattr(llm, "embedding_api_url"):
                env["EMBEDDING_API_URL"] = llm.embedding_api_url
            if hasattr(llm, "embedding_model"):
                env["EMBEDDING_MODEL"] = llm.embedding_model

        # Discord config
        discord = getattr(config, "discord", None)
        if discord:
            if hasattr(discord, "bot_token"):
                env["DISCORD_BOT_TOKEN"] = discord.bot_token
            if hasattr(discord, "guild_id"):
                env["DISCORD_GUILD_ID"] = str(discord.guild_id)

        # Temporal config
        temporal = getattr(config, "temporal", None)
        if temporal:
            if hasattr(temporal, "host"):
                env["TEMPORAL_HOST"] = temporal.host
            if hasattr(temporal, "namespace"):
                env["TEMPORAL_NAMESPACE"] = temporal.namespace

        return env

    async def start_server(
        self,
        server_name: str,
        port: int | None = None,
        config: Any = None,
        timeout: float = 30.0,
    ) -> MCPServerProcess:
        """
        Start an MCP server and wait for it to be healthy.

        Args:
            server_name: Name of the server (memory, discord, temporal, qdrant)
            port: Port to run on (defaults to DEFAULT_PORTS)
            config: Configuration object for environment variables
            timeout: Seconds to wait for health check

        Returns:
            MCPServerProcess tracking the running server

        Raises:
            RuntimeError: If server fails to start or health check times out
        """
        if port is None:
            port = DEFAULT_PORTS.get(server_name, 8080 + len(self.servers))

        server_path = self._get_server_path(server_name)
        if not server_path.exists():
            raise RuntimeError(f"MCP server not found at {server_path}")

        cmd = self._get_server_command(server_name)
        env = self._build_server_env(config)
        env["PORT"] = str(port)

        logger.info(f"Starting {server_name} MCP server on port {port}")

        # Create a temp file to capture stderr for debugging
        stderr_file = tempfile.NamedTemporaryFile(
            mode="w",
            prefix=f"mcp_{server_name}_",
            suffix=".log",
            delete=False,
        )
        stderr_path = stderr_file.name

        process = subprocess.Popen(
            cmd,
            cwd=str(server_path),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=stderr_file,
        )

        url = f"http://localhost:{port}"

        # Wait for health check
        try:
            await self._wait_for_health(url, timeout)
        except TimeoutError as err:
            # Clean up the process properly before raising
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

            # Read stderr for debugging
            stderr_output = self._read_stderr_log(stderr_path)
            error_msg = f"MCP server {server_name} failed to become healthy within {timeout}s"
            if stderr_output:
                error_msg += f"\n\nServer stderr:\n{stderr_output}"

            # Clean up stderr file on failure
            try:
                os.unlink(stderr_path)
            except OSError:
                pass

            raise RuntimeError(error_msg) from err

        server_process = MCPServerProcess(
            name=server_name,
            port=port,
            process=process,
            url=url,
            stderr_path=stderr_path,
        )

        self.servers[server_name] = server_process
        self.processes.append(process)

        logger.info(f"MCP server {server_name} started successfully at {url}")
        return server_process

    async def _wait_for_health(self, url: str, timeout: float) -> None:
        """
        Poll the health endpoint until the server responds.

        Args:
            url: Base URL of the server
            timeout: Maximum seconds to wait

        Raises:
            TimeoutError: If server doesn't respond within timeout
        """
        health_url = f"{url}/health"
        start_time = asyncio.get_event_loop().time()

        async with httpx.AsyncClient() as client:
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    raise TimeoutError(f"Health check timed out after {timeout}s")

                try:
                    response = await client.get(health_url, timeout=2.0)
                    if response.status_code == 200:
                        return
                except (httpx.ConnectError, httpx.ReadTimeout):
                    pass

                await asyncio.sleep(0.5)

    @staticmethod
    def _read_stderr_log(stderr_path: str, max_lines: int = 50) -> str:
        """
        Read the last N lines from the stderr log file.

        Args:
            stderr_path: Path to the stderr log file
            max_lines: Maximum number of lines to return

        Returns:
            String containing the last N lines of stderr, or empty string on error
        """
        try:
            with open(stderr_path) as f:
                lines = f.readlines()
                # Return last max_lines lines
                return "".join(lines[-max_lines:]).strip()
        except OSError as e:
            logger.warning(f"Failed to read stderr log {stderr_path}: {e}")
            return ""

    async def start_servers(
        self,
        server_names: list[str],
        config: Any = None,
    ) -> dict[str, MCPServerProcess]:
        """
        Start multiple MCP servers.

        Args:
            server_names: List of server names to start
            config: Configuration object for environment variables

        Returns:
            Dict mapping server names to their process info

        Raises:
            RuntimeError: If any server fails to start. Already-started servers
                are cleaned up before raising.
        """
        started: list[str] = []
        try:
            for name in server_names:
                await self.start_server(name, config=config)
                started.append(name)
            return self.servers
        except Exception:
            # Clean up any servers that were started before the failure
            for name in started:
                self.stop_server(name)
            raise

    def stop_server(self, server_name: str) -> None:
        """
        Stop a specific MCP server.

        Args:
            server_name: Name of the server to stop
        """
        if server_name not in self.servers:
            logger.warning(f"Server {server_name} not found in running servers")
            return

        server = self.servers[server_name]
        logger.info(f"Stopping MCP server {server_name}")

        server.process.terminate()
        try:
            server.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.process.kill()

        # Clean up stderr log file
        if server.stderr_path:
            try:
                os.unlink(server.stderr_path)
            except OSError:
                pass

        if server.process in self.processes:
            self.processes.remove(server.process)
        del self.servers[server_name]

    def stop_all(self) -> None:
        """Stop all running MCP servers."""
        for name in list(self.servers.keys()):
            self.stop_server(name)

    def get_server_urls(self) -> dict[str, str]:
        """
        Get URLs for all running servers.

        Returns:
            Dict mapping server names to their URLs
        """
        return {name: server.url for name, server in self.servers.items()}
