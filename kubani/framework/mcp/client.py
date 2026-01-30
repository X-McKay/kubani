"""
MCP Client for Agent Integration.

Provides a unified interface for agents to interact with MCP servers.
Uses MCP SDK's SSE transport for all communication.

Usage:
    from framework.mcp import MCPClient, get_mcp_client

    # Get pre-configured client
    client = get_mcp_client()

    # Use Temporal MCP
    workflows = await client.temporal.list_workflows(status="running")

    # Use Memory MCP
    await client.memory.store_learning(
        agent_id="k8s-monitor",
        content="OOM kills indicate memory pressure",
        confidence=0.85,
    )

    # Use Qdrant MCP
    results = await client.qdrant.search_vectors(
        collection="skills",
        query_vector=embedding,
        limit=5,
    )
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import CallToolResult

from kubani.framework.config import MCPServerConfig, get_config

logger = logging.getLogger(__name__)


@dataclass
class MCPResponse:
    """Response from an MCP tool call."""

    success: bool
    data: Any
    error: str | None = None


class MCPServerClient:
    """Client for a single MCP server using SSE transport.

    Uses the MCP SDK's SSE client for proper protocol communication.
    Each call creates a fresh connection since SSE connections are stateful.
    """

    def __init__(self, name: str, url: str, timeout: float = 30.0):
        self.name = name
        # Ensure URL ends with /sse for SSE transport
        self.url = url.rstrip("/")
        if not self.url.endswith("/sse"):
            self.url = f"{self.url}/sse"
        self.timeout = timeout

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[ClientSession]:
        """Create an SSE connection to the MCP server.

        Yields:
            ClientSession ready for tool calls.
        """
        async with sse_client(self.url, timeout=self.timeout) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    async def call_tool(self, tool_name: str, **kwargs: Any) -> MCPResponse:
        """
        Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call
            **kwargs: Tool arguments

        Returns:
            MCPResponse with the result
        """
        try:
            async with self._connect() as session:
                result: CallToolResult = await session.call_tool(tool_name, arguments=kwargs)

                if result.isError:
                    # Extract error message from content
                    error_msg = self._extract_text_from_content(result.content)
                    logger.error(f"MCP {self.name} tool {tool_name} returned error: {error_msg}")
                    return MCPResponse(success=False, data=None, error=error_msg)

                # Parse content into Python data
                data = self._parse_content(result.content)
                return MCPResponse(success=True, data=data)

        except Exception as e:
            logger.error(f"MCP {self.name} tool {tool_name} error: {e}")
            return MCPResponse(success=False, data=None, error=str(e))

    def _extract_text_from_content(self, content: list) -> str:
        """Extract text from MCP content blocks."""
        texts = []
        for block in content:
            if hasattr(block, "text"):
                texts.append(block.text)
        return " ".join(texts) if texts else "Unknown error"

    def _parse_content(self, content: list) -> Any:
        """Parse MCP content blocks into Python data.

        MCP returns content as [TextContent(type="text", text="{...json...}")].
        When a tool returns a list, FastMCP may serialize each item as a
        separate TextContent block. This method handles both cases:
        - Single block: Parse and return the value (dict, list, or scalar)
        - Multiple blocks: Parse each block and return as a list
        """
        if not content:
            return None

        # Single block - parse directly (preserves original behavior)
        if len(content) == 1:
            first_block = content[0]
            if hasattr(first_block, "text"):
                text = first_block.text
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return text
            return content[0]

        # Multiple blocks - parse each and return as list
        # This handles FastMCP's serialization of list return types
        results = []
        for block in content:
            if hasattr(block, "text"):
                try:
                    results.append(json.loads(block.text))
                except (json.JSONDecodeError, TypeError):
                    results.append(block.text)
            else:
                results.append(block)
        return results

    def _extract_data(self, response: MCPResponse) -> Any:
        """Extract clean data from an MCPResponse.

        Raises:
            RuntimeError: If the MCP call failed.
        """
        if not response.success:
            raise RuntimeError(response.error or "MCP call failed")
        return response.data

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools on the MCP server."""
        try:
            async with self._connect() as session:
                result = await session.list_tools()
                return [
                    {"name": tool.name, "description": tool.description} for tool in result.tools
                ]
        except Exception as e:
            logger.error(f"Failed to list tools for {self.name}: {e}")
            return []

    async def health_check(self) -> bool:
        """Check if the MCP server is healthy by attempting to list tools."""
        try:
            tools = await self.list_tools()
            return len(tools) > 0
        except Exception:
            return False

    async def close(self) -> None:
        """No-op for SSE client (connections are per-call)."""
        pass


class TemporalMCPClient(MCPServerClient):
    """Client for Temporal MCP server."""

    async def list_workflows(
        self,
        status: str | None = None,
        workflow_type: str | None = None,
        limit: int = 100,
    ) -> MCPResponse:
        """List Temporal workflows."""
        return await self.call_tool(
            "list_workflows",
            status=status,
            workflow_type=workflow_type,
            limit=limit,
        )

    async def get_workflow(self, workflow_id: str, run_id: str | None = None) -> MCPResponse:
        """Get workflow details."""
        return await self.call_tool(
            "get_workflow",
            workflow_id=workflow_id,
            run_id=run_id,
        )

    async def start_workflow(
        self,
        workflow_type: str,
        workflow_id: str,
        task_queue: str,
        args: list[Any] | None = None,
    ) -> MCPResponse:
        """Start a new workflow."""
        return await self.call_tool(
            "start_workflow",
            workflow_type=workflow_type,
            workflow_id=workflow_id,
            task_queue=task_queue,
            args=args or [],
        )

    async def signal_workflow(
        self,
        workflow_id: str,
        signal_name: str,
        args: list[Any] | None = None,
    ) -> MCPResponse:
        """Send a signal to a workflow."""
        return await self.call_tool(
            "signal_workflow",
            workflow_id=workflow_id,
            signal_name=signal_name,
            args=args or [],
        )

    async def cancel_workflow(self, workflow_id: str) -> MCPResponse:
        """Cancel a workflow."""
        return await self.call_tool("cancel_workflow", workflow_id=workflow_id)

    async def list_schedules(self, limit: int = 100) -> MCPResponse:
        """List Temporal schedules."""
        return await self.call_tool("list_schedules", limit=limit)


class QdrantMCPClient(MCPServerClient):
    """Client for Qdrant MCP server."""

    async def list_collections(self) -> MCPResponse:
        """List all collections."""
        return await self.call_tool("list_collections")

    async def create_collection(
        self,
        name: str,
        vector_size: int,
        distance: str = "Cosine",
    ) -> MCPResponse:
        """Create a new collection."""
        return await self.call_tool(
            "create_collection",
            name=name,
            vector_size=vector_size,
            distance=distance,
        )

    async def search_vectors(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filter_conditions: dict[str, Any] | None = None,
    ) -> MCPResponse:
        """Search for similar vectors."""
        return await self.call_tool(
            "search_vectors",
            collection=collection,
            query_vector=query_vector,
            limit=limit,
            filter=filter_conditions,
        )

    async def upsert_vectors(
        self,
        collection: str,
        points: list[dict[str, Any]],
    ) -> MCPResponse:
        """Insert or update vectors."""
        return await self.call_tool(
            "upsert_vectors",
            collection=collection,
            points=points,
        )

    async def delete_points(
        self,
        collection: str,
        point_ids: list[str | int],
    ) -> MCPResponse:
        """Delete points from a collection."""
        return await self.call_tool(
            "delete_points",
            collection=collection,
            point_ids=point_ids,
        )


class MemoryMCPClient(MCPServerClient):
    """Client for Memory MCP server (unified memory interface).

    All methods return parsed data (dicts/lists) rather than MCPResponse,
    raising RuntimeError on failure. This allows activities to use the
    return values directly without unwrapping.
    """

    async def store_learning(
        self,
        agent_id: str,
        learning_type: str,
        content: str,
        confidence: float,
        context: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Store an agent learning. Returns dict with learning_id, etc."""
        response = await self.call_tool(
            "store_learning",
            agent_id=agent_id,
            learning_type=learning_type,
            content=content,
            confidence=confidence,
            context=context or {},
            tags=tags or [],
        )
        return self._extract_data(response)

    async def query_learnings(
        self,
        query: str,
        agent_id: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Query learnings by semantic similarity. Returns dict with learnings list."""
        response = await self.call_tool(
            "query_learnings",
            query=query,
            agent_id=agent_id,
            min_confidence=min_confidence,
            limit=limit,
        )
        return self._extract_data(response)

    async def store_knowledge(
        self,
        topic: str,
        content: str,
        source: str,
        related_topics: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store domain knowledge. Returns dict with knowledge_id, etc."""
        response = await self.call_tool(
            "store_knowledge",
            topic=topic,
            content=content,
            source=source,
            related_topics=related_topics or [],
            metadata=metadata or {},
        )
        return self._extract_data(response)

    async def get_knowledge_graph(
        self,
        topic: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        """Get knowledge graph around a topic."""
        response = await self.call_tool(
            "get_knowledge_graph",
            topic=topic,
            depth=depth,
        )
        return self._extract_data(response)

    async def cache_get(self, key: str) -> dict[str, Any]:
        """Get a cached value. Returns dict with found, value."""
        response = await self.call_tool("cache_get", key=key)
        return self._extract_data(response)

    async def cache_set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Set a cached value."""
        response = await self.call_tool(
            "cache_set",
            key=key,
            value=value,
            ttl_seconds=ttl_seconds,
        )
        return self._extract_data(response)

    async def query_knowledge(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Query knowledge entries by semantic similarity.

        Args:
            query: Semantic search query
            limit: Maximum results to return

        Returns:
            List of knowledge entry dicts with topic, content, source, etc.
        """
        response = await self.call_tool(
            "query_knowledge",
            query=query,
            limit=limit,
        )
        return self._extract_data(response)


class DiscordMCPClient(MCPServerClient):
    """Client for Discord MCP server."""

    async def send_message(
        self,
        channel_id: str,
        content: str,
        embed: dict[str, Any] | None = None,
    ) -> MCPResponse:
        """Send a message to a channel by ID."""
        kwargs: dict[str, Any] = {
            "channel_id": channel_id,
            "content": content,
        }
        if embed:
            kwargs["embed"] = embed
        return await self.call_tool("send_message", **kwargs)

    async def send_message_to_channel_name(
        self,
        channel_name: str,
        content: str,
        embed: dict[str, Any] | None = None,
    ) -> MCPResponse:
        """Send a message to a channel by name."""
        kwargs: dict[str, Any] = {
            "channel_name": channel_name,
            "content": content,
        }
        if embed:
            kwargs["embed"] = embed
        return await self.call_tool("send_message_to_channel_name", **kwargs)

    async def send_embed(
        self,
        channel_id: str,
        title: str,
        description: str,
        color: int | None = None,
        fields: list[dict[str, Any]] | None = None,
    ) -> MCPResponse:
        """Send an embed message."""
        return await self.call_tool(
            "send_embed",
            channel_id=channel_id,
            title=title,
            description=description,
            color=color,
            fields=fields or [],
        )

    async def add_reaction(
        self,
        channel_id: str,
        message_id: str,
        emoji: str,
    ) -> MCPResponse:
        """Add a reaction to a message."""
        return await self.call_tool(
            "add_reaction",
            channel_id=channel_id,
            message_id=message_id,
            emoji=emoji,
        )

    async def get_reactions(
        self,
        channel_id: str,
        message_id: str,
    ) -> MCPResponse:
        """Get reactions on a message."""
        return await self.call_tool(
            "get_reactions",
            channel_id=channel_id,
            message_id=message_id,
        )

    async def wait_for_reaction(
        self,
        channel_id: str,
        message_id: str,
        allowed_emojis: list[str],
        timeout_seconds: int = 300,
    ) -> MCPResponse:
        """Wait for a specific reaction."""
        return await self.call_tool(
            "wait_for_reaction",
            channel_id=channel_id,
            message_id=message_id,
            allowed_emojis=allowed_emojis,
            timeout_seconds=timeout_seconds,
        )


class RegistryMCPClient(MCPServerClient):
    """Client for Registry MCP server."""

    async def register_agent(
        self,
        agent_id: str,
        name: str,
        version: str,
        capabilities: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> MCPResponse:
        """Register an agent."""
        return await self.call_tool(
            "register_agent",
            agent_id=agent_id,
            name=name,
            version=version,
            capabilities=capabilities,
            metadata=metadata or {},
        )

    async def heartbeat(self, agent_id: str) -> MCPResponse:
        """Send agent heartbeat."""
        return await self.call_tool("heartbeat", agent_id=agent_id)

    async def list_agents(self, status: str | None = None) -> MCPResponse:
        """List registered agents."""
        return await self.call_tool("list_agents", status=status)

    async def list_skills(self, agent_id: str | None = None) -> MCPResponse:
        """List available skills."""
        return await self.call_tool("list_skills", agent_id=agent_id)

    async def sync_skills(self, skills_path: str) -> MCPResponse:
        """Sync skills from a directory."""
        return await self.call_tool("sync_skills", skills_path=skills_path)


class SkillsMCPClient(MCPServerClient):
    """Client for Skills MCP server."""

    async def list_skills(
        self,
        domain: str | None = None,
        category: str | None = None,
    ) -> MCPResponse:
        """List available skills."""
        return await self.call_tool(
            "list_skills",
            domain=domain,
            category=category,
        )

    async def get_skill(self, skill_path: str) -> MCPResponse:
        """Get skill details."""
        return await self.call_tool("get_skill", skill_path=skill_path)

    async def execute_skill(
        self,
        skill_path: str,
        context: dict[str, Any],
        timeout: float | None = None,
    ) -> MCPResponse:
        """Execute a skill."""
        return await self.call_tool(
            "execute_skill",
            skill_path=skill_path,
            context=context,
            timeout=timeout,
        )


class MCPClient:
    """
    Unified MCP client for all MCP servers.

    Provides typed access to all MCP servers with automatic configuration
    from the unified config system.
    """

    def __init__(self, config: MCPServerConfig | None = None):
        self._config = config or get_config().mcp
        self._temporal: TemporalMCPClient | None = None
        self._qdrant: QdrantMCPClient | None = None
        self._memory: MemoryMCPClient | None = None
        self._discord: DiscordMCPClient | None = None
        self._registry: RegistryMCPClient | None = None
        self._skills: SkillsMCPClient | None = None

    @property
    def temporal(self) -> TemporalMCPClient:
        """Get Temporal MCP client."""
        if self._temporal is None:
            self._temporal = TemporalMCPClient("temporal", self._config.temporal_url)
        return self._temporal

    @property
    def qdrant(self) -> QdrantMCPClient:
        """Get Qdrant MCP client."""
        if self._qdrant is None:
            self._qdrant = QdrantMCPClient("qdrant", self._config.qdrant_url)
        return self._qdrant

    @property
    def memory(self) -> MemoryMCPClient:
        """Get Memory MCP client."""
        if self._memory is None:
            self._memory = MemoryMCPClient("memory", self._config.memory_url)
        return self._memory

    @property
    def discord(self) -> DiscordMCPClient:
        """Get Discord MCP client."""
        if self._discord is None:
            self._discord = DiscordMCPClient("discord", self._config.discord_url)
        return self._discord

    @property
    def registry(self) -> RegistryMCPClient:
        """Get Registry MCP client."""
        if self._registry is None:
            self._registry = RegistryMCPClient("registry", self._config.registry_url)
        return self._registry

    @property
    def skills(self) -> SkillsMCPClient:
        """Get Skills MCP client."""
        if self._skills is None:
            self._skills = SkillsMCPClient("skills", self._config.skills_url)
        return self._skills

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of all MCP servers."""
        results = {}
        if self._config.temporal_enabled:
            results["temporal"] = await self.temporal.health_check()
        if self._config.qdrant_enabled:
            results["qdrant"] = await self.qdrant.health_check()
        if self._config.memory_enabled:
            results["memory"] = await self.memory.health_check()
        if self._config.discord_enabled:
            results["discord"] = await self.discord.health_check()
        if self._config.registry_enabled:
            results["registry"] = await self.registry.health_check()
        if self._config.skills_enabled:
            results["skills"] = await self.skills.health_check()
        return results

    async def close(self) -> None:
        """Close all MCP clients."""
        clients = [
            self._temporal,
            self._qdrant,
            self._memory,
            self._discord,
            self._registry,
            self._skills,
        ]
        await asyncio.gather(
            *[c.close() for c in clients if c is not None],
            return_exceptions=True,
        )


# Global MCP client instance
_mcp_client: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    """Get the global MCP client instance."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client


async def close_mcp_client() -> None:
    """Close the global MCP client."""
    global _mcp_client
    if _mcp_client is not None:
        await _mcp_client.close()
        _mcp_client = None
