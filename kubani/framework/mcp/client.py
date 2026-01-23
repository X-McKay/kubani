"""
MCP Client for Agent Integration.

Provides a unified interface for agents to interact with MCP servers.
Supports both stdio and HTTP/SSE transports.

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
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from framework.config import MCPServerConfig, get_config

logger = logging.getLogger(__name__)


@dataclass
class MCPResponse:
    """Response from an MCP tool call."""

    success: bool
    data: Any
    error: str | None = None


class MCPServerClient:
    """Client for a single MCP server."""

    def __init__(self, name: str, url: str, timeout: float = 30.0):
        self.name = name
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.url,
                timeout=self.timeout,
            )
        return self._client

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
            client = await self._get_client()
            response = await client.post(
                "/tools/call",
                json={
                    "name": tool_name,
                    "arguments": kwargs,
                },
            )
            response.raise_for_status()
            result = response.json()
            return MCPResponse(
                success=True,
                data=result.get("content", result),
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"MCP {self.name} tool {tool_name} failed: {e}")
            return MCPResponse(
                success=False,
                data=None,
                error=str(e),
            )
        except Exception as e:
            logger.error(f"MCP {self.name} tool {tool_name} error: {e}")
            return MCPResponse(
                success=False,
                data=None,
                error=str(e),
            )

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools on the MCP server."""
        try:
            client = await self._get_client()
            response = await client.get("/tools/list")
            response.raise_for_status()
            return response.json().get("tools", [])
        except Exception as e:
            logger.error(f"Failed to list tools for {self.name}: {e}")
            return []

    async def health_check(self) -> bool:
        """Check if the MCP server is healthy."""
        try:
            client = await self._get_client()
            response = await client.get("/health")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


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
    """Client for Memory MCP server (unified memory interface)."""

    async def store_learning(
        self,
        agent_id: str,
        learning_type: str,
        content: str,
        confidence: float,
        context: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> MCPResponse:
        """Store an agent learning."""
        return await self.call_tool(
            "store_learning",
            agent_id=agent_id,
            learning_type=learning_type,
            content=content,
            confidence=confidence,
            context=context or {},
            tags=tags or [],
        )

    async def query_learnings(
        self,
        query: str,
        agent_id: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> MCPResponse:
        """Query learnings by semantic similarity."""
        return await self.call_tool(
            "query_learnings",
            query=query,
            agent_id=agent_id,
            min_confidence=min_confidence,
            limit=limit,
        )

    async def store_knowledge(
        self,
        topic: str,
        content: str,
        related_topics: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MCPResponse:
        """Store domain knowledge."""
        return await self.call_tool(
            "store_knowledge",
            topic=topic,
            content=content,
            related_topics=related_topics or [],
            metadata=metadata or {},
        )

    async def get_knowledge_graph(
        self,
        topic: str,
        depth: int = 2,
    ) -> MCPResponse:
        """Get knowledge graph around a topic."""
        return await self.call_tool(
            "get_knowledge_graph",
            topic=topic,
            depth=depth,
        )

    async def cache_get(self, key: str) -> MCPResponse:
        """Get a cached value."""
        return await self.call_tool("cache_get", key=key)

    async def cache_set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> MCPResponse:
        """Set a cached value."""
        return await self.call_tool(
            "cache_set",
            key=key,
            value=value,
            ttl_seconds=ttl_seconds,
        )


class DiscordMCPClient(MCPServerClient):
    """Client for Discord MCP server."""

    async def send_message(
        self,
        channel_id: str,
        content: str,
    ) -> MCPResponse:
        """Send a message to a channel."""
        return await self.call_tool(
            "send_message",
            channel_id=channel_id,
            content=content,
        )

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
