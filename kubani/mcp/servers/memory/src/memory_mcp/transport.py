"""
Transport mode utilities for MCP servers.

Provides consistent argument parsing and transport configuration.
Inlined from kubani.framework.mcp.server.transport for standalone deployment.
"""

import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

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
        """Parse transport config from command line arguments."""
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


async def run_server_async(
    mcp: FastMCP,
    config: TransportConfig,
    startup_hook: Callable[[], None] | None = None,
    shutdown_hook: Callable[[], None] | None = None,
) -> None:
    """Run the MCP server with the specified transport configuration."""
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
