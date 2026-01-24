"""
Skills MCP Server.

Discovers and executes Kubani skills with sandboxed isolation.
"""

from skills_mcp.server import create_server, main

__all__ = ["create_server", "main"]
__version__ = "0.1.0"
