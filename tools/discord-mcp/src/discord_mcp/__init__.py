"""
Discord MCP Server for Kubani.

Provides bidirectional Discord integration via the Model Context Protocol,
enabling AI agents to send messages, read responses, manage reactions,
channels, and webhooks.
"""

from discord_mcp.server import create_server, main

__all__ = ["create_server", "main"]
__version__ = "0.1.0"
