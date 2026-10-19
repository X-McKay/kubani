"""Official MCP transport, with no credential persistence or dynamic tool registration."""

import asyncio
import os

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ENDPOINT = "https://mcp.almckay.io/kubernetes/mcp"
NAMESPACE = "zetra-poc-fixtures"
TOOLS = {"pods_list_in_namespace", "pods_get", "events_list"}


class KubernetesMcp:
    async def call(self, tool: str, arguments: dict) -> dict:
        if tool not in TOOLS or arguments.get("namespace") != NAMESPACE:
            raise ValueError("MCP call is outside the reviewed investigation scope")
        token = os.environ.get("MCP_ACCESS_TOKEN")
        if not token:
            raise ValueError("MCP_ACCESS_TOKEN must be supplied by the credential provider")
        async with asyncio.timeout(20):
            async with (
                httpx2.AsyncClient(
                    headers={"Authorization": "Bearer " + token}, timeout=15, follow_redirects=False
                ) as http,
                streamable_http_client(
                    os.environ.get("MCP_ENDPOINT", ENDPOINT), http_client=http
                ) as streams,
                ClientSession(*streams, read_timeout_seconds=15) as client,
            ):
                await client.initialize()
                result = await client.call_tool(tool, arguments)
        if result.is_error:
            raise ValueError("read-only MCP server returned an error")
        text = "\n".join(part.text for part in result.content if part.type == "text")
        if len(text.encode()) > 16_000:
            raise ValueError("MCP observation exceeded the bounded result size")
        return {"tool": tool, "namespace": NAMESPACE, "text": text}
