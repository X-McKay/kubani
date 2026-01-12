"""
Agent Discovery Service.

Automatically discovers and tracks all deployed agents via:
- Registry API queries
- Kubernetes label-based discovery
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredAgent:
    """A discovered agent with its metadata."""

    agent_id: str
    name: str
    version: str
    task_queue: str | None = None
    endpoint: str | None = None
    status: str = "unknown"
    last_heartbeat: datetime | None = None
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_healthy(self) -> bool:
        """Check if agent is considered healthy."""
        return self.status == "healthy"

    @property
    def is_stale(self) -> bool:
        """Check if agent hasn't reported in recently."""
        if not self.last_heartbeat:
            return True
        age = datetime.now(UTC) - self.last_heartbeat
        return age.total_seconds() > 300  # 5 minutes


class AgentDiscoveryService:
    """
    Discovers and tracks all deployed agents.

    Uses the metadata registry as primary source, with optional
    Kubernetes API fallback for additional discovery.
    """

    def __init__(
        self,
        registry_url: str = "http://metadata-registry.ai-agents.svc:8000",
        http_client: httpx.AsyncClient | None = None,
    ):
        """
        Initialize the discovery service.

        Args:
            registry_url: URL of the metadata registry API
            http_client: Optional shared HTTP client
        """
        self.registry_url = registry_url.rstrip("/")
        self._client = http_client
        self._owns_client = http_client is None
        self._cache: dict[str, DiscoveredAgent] = {}
        self._last_refresh: datetime | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        """Close HTTP client if we own it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def discover_agents(self, force_refresh: bool = False) -> list[DiscoveredAgent]:
        """
        Discover all registered agents.

        Args:
            force_refresh: If True, bypass cache and query registry

        Returns:
            List of discovered agents
        """
        # Check cache freshness (5 minute TTL)
        if not force_refresh and self._last_refresh:
            age = datetime.now(UTC) - self._last_refresh
            if age.total_seconds() < 300:
                return list(self._cache.values())

        try:
            client = await self._get_client()
            response = await client.get(f"{self.registry_url}/api/v1/agents")
            response.raise_for_status()

            agents_data = response.json()
            agents = []

            for agent_data in agents_data:
                agent = self._parse_agent(agent_data)
                agents.append(agent)
                self._cache[agent.agent_id] = agent

            self._last_refresh = datetime.now(UTC)
            logger.info(f"Discovered {len(agents)} agents from registry")
            return agents

        except httpx.HTTPError as e:
            logger.warning(f"Failed to query registry: {e}")
            # Return cached data on error
            return list(self._cache.values())

    async def get_agent(self, agent_id: str) -> DiscoveredAgent | None:
        """
        Get a specific agent by ID.

        Args:
            agent_id: The agent identifier

        Returns:
            DiscoveredAgent if found, None otherwise
        """
        # Check cache first
        if agent_id in self._cache:
            return self._cache[agent_id]

        try:
            client = await self._get_client()
            response = await client.get(f"{self.registry_url}/api/v1/agents/{agent_id}")

            if response.status_code == 404:
                return None

            response.raise_for_status()
            agent_data = response.json()
            agent = self._parse_agent(agent_data)
            self._cache[agent.agent_id] = agent
            return agent

        except httpx.HTTPError as e:
            logger.warning(f"Failed to get agent {agent_id}: {e}")
            return self._cache.get(agent_id)

    async def get_healthy_agents(self) -> list[DiscoveredAgent]:
        """Get only healthy agents."""
        agents = await self.discover_agents()
        return [a for a in agents if a.is_healthy]

    async def get_agents_with_task_queue(self) -> list[DiscoveredAgent]:
        """Get agents that have a Temporal task queue configured."""
        agents = await self.discover_agents()
        return [a for a in agents if a.task_queue]

    def _parse_agent(self, data: dict[str, Any]) -> DiscoveredAgent:
        """Parse agent data from registry response."""
        last_heartbeat = None
        if data.get("last_heartbeat"):
            try:
                last_heartbeat = datetime.fromisoformat(
                    data["last_heartbeat"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        capabilities = []
        if data.get("capabilities"):
            capabilities = [c.get("name", "") for c in data["capabilities"] if c.get("name")]

        return DiscoveredAgent(
            agent_id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", "unknown"),
            task_queue=data.get("task_queue"),
            endpoint=data.get("endpoint"),
            status=data.get("status", "unknown"),
            last_heartbeat=last_heartbeat,
            capabilities=capabilities,
            metadata=data.get("metadata_", {}) or data.get("metadata", {}),
        )

    def get_cached_agents(self) -> list[DiscoveredAgent]:
        """Get currently cached agents without querying registry."""
        return list(self._cache.values())

    def clear_cache(self) -> None:
        """Clear the agent cache."""
        self._cache.clear()
        self._last_refresh = None
