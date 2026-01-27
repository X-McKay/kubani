"""
Transport mode utilities for MCP servers.

Provides consistent argument parsing and transport configuration
across all MCP servers.
"""

import argparse
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

import anyio
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)


class TransportMode(Enum):
    """Supported MCP transport modes."""

    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


@dataclass
class TransportConfig:
    """Configuration for MCP transport."""

    mode: TransportMode = TransportMode.STDIO
    host: str = "0.0.0.0"
    port: int = 8080
    allowed_hosts: list[str] = field(default_factory=lambda: ["localhost:*", "127.0.0.1:*"])

    @classmethod
    def from_args(cls, args: list[str] | None = None) -> "TransportConfig":
        """
        Parse transport config from command line arguments.

        Args:
            args: Command line arguments (defaults to sys.argv[1:])

        Returns:
            TransportConfig instance
        """
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument(
            "--mode",
            choices=["stdio", "sse", "http"],
            default="stdio",
            help="Transport mode",
        )
        parser.add_argument(
            "--host",
            default="0.0.0.0",
            help="Host to bind to",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8080,
            help="Port to bind to",
        )
        parser.add_argument(
            "--allowed-hosts",
            default="",
            help="Comma-separated list of allowed hosts",
        )

        parsed, _ = parser.parse_known_args(args)

        allowed_hosts = ["localhost:*", "127.0.0.1:*"]
        if parsed.allowed_hosts:
            allowed_hosts.extend(h.strip() for h in parsed.allowed_hosts.split(",") if h.strip())

        return cls(
            mode=TransportMode(parsed.mode),
            host=parsed.host,
            port=parsed.port,
            allowed_hosts=allowed_hosts,
        )

    @classmethod
    def from_env(cls) -> "TransportConfig":
        """
        Load transport config from environment variables.

        Environment variables:
            MCP_TRANSPORT: Transport mode (stdio, sse, http)
            MCP_HOST: Host to bind to
            MCP_PORT: Port to bind to
            MCP_ALLOWED_HOSTS: Comma-separated allowed hosts

        Returns:
            TransportConfig instance
        """
        mode_str = os.environ.get("MCP_TRANSPORT", "stdio")
        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8080"))

        allowed_hosts = ["localhost:*", "127.0.0.1:*"]
        allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
        if allowed_hosts_env:
            allowed_hosts.extend(h.strip() for h in allowed_hosts_env.split(",") if h.strip())

        return cls(
            mode=TransportMode(mode_str),
            host=host,
            port=port,
            allowed_hosts=allowed_hosts,
        )


async def run_server_async(
    mcp: FastMCP,
    config: TransportConfig,
    startup_hook: Callable[[], None] | None = None,
    shutdown_hook: Callable[[], None] | None = None,
) -> None:
    """
    Run the MCP server with the specified transport configuration.

    Args:
        mcp: The FastMCP server instance
        config: Transport configuration
        startup_hook: Optional async function to call before serving
        shutdown_hook: Optional async function to call on shutdown
    """
    try:
        if startup_hook:
            await startup_hook()

        if config.mode == TransportMode.STDIO:
            await mcp.run_stdio_async()
        elif config.mode == TransportMode.SSE:
            logger.info(f"Starting SSE server on {config.host}:{config.port}")
            mcp.settings.host = config.host
            mcp.settings.port = config.port
            await mcp.run_sse_async()
        elif config.mode == TransportMode.HTTP:
            logger.info(f"Starting HTTP server on {config.host}:{config.port}")
            mcp.settings.host = config.host
            mcp.settings.port = config.port
            await mcp.run_streamable_http_async()
    finally:
        if shutdown_hook:
            await shutdown_hook()


def run_server(
    mcp: FastMCP,
    config: TransportConfig,
    startup_hook: Callable[[], None] | None = None,
    shutdown_hook: Callable[[], None] | None = None,
) -> None:
    """
    Run the MCP server synchronously.

    This is a convenience wrapper around run_server_async.

    Args:
        mcp: The FastMCP server instance
        config: Transport configuration
        startup_hook: Optional async function to call before serving
        shutdown_hook: Optional async function to call on shutdown
    """
    anyio.run(
        run_server_async,
        mcp,
        config,
        startup_hook,
        shutdown_hook,
    )
