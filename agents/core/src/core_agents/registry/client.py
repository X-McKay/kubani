"""Registry client for interacting with the centralized registry service."""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx

from .models import (
    AgentCapability,
    AgentInfo,
    Deployment,
    EffectivePolicy,
    Endpoint,
    HeartbeatResponse,
    MCPServer,
    Model,
    ResolvedEndpoint,
    SkillMetadata,
)

logger = logging.getLogger(__name__)

# Module-level singleton
_registry_client: "RegistryClient | None" = None


class RegistryClient:
    """Client for the centralized registry service.

    Provides methods for agent registration, heartbeats, and querying
    the registry for endpoints, models, MCP servers, etc.

    Example:
        ```python
        async with RegistryClient("http://registry:8000") as client:
            await client.register_agent(
                agent_id="k8s-monitor",
                name="K8s Monitor",
                task_queue="k8s-monitor",
            )
            await client.start_heartbeat()
        ```
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        heartbeat_interval: float = 30.0,
    ) -> None:
        """Initialize the registry client.

        Args:
            base_url: Base URL of the registry service (e.g., http://registry:8000)
            timeout: Request timeout in seconds
            heartbeat_interval: Interval between heartbeat updates in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.heartbeat_interval = heartbeat_interval
        self._client: httpx.AsyncClient | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._agent_id: str | None = None
        self._shutdown = False

    async def __aenter__(self) -> "RegistryClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Initialize the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
            logger.debug("Registry client connected to %s", self.base_url)

    async def close(self) -> None:
        """Close the client and stop heartbeat."""
        self._shutdown = True
        await self.stop_heartbeat()
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.debug("Registry client closed")

    def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure client is connected."""
        if self._client is None:
            raise RuntimeError("Registry client not connected. Call connect() first.")
        return self._client

    # -------------------------------------------------------------------------
    # Agent Registration
    # -------------------------------------------------------------------------

    async def register_agent(
        self,
        agent_id: str,
        name: str,
        description: str | None = None,
        version: str | None = None,
        endpoint: str | None = None,
        task_queue: str | None = None,
        metadata: dict | None = None,
        capabilities: list[AgentCapability] | None = None,
    ) -> AgentInfo:
        """Register an agent with the registry.

        Args:
            agent_id: Unique identifier for the agent
            name: Human-readable name
            description: Agent description
            version: Agent version
            endpoint: HTTP endpoint for direct communication
            task_queue: Temporal task queue name
            metadata: Additional metadata
            capabilities: List of agent capabilities

        Returns:
            The registered agent info
        """
        client = self._ensure_client()
        payload = {
            "id": agent_id,
            "name": name,
            "description": description,
            "version": version,
            "endpoint": endpoint,
            "task_queue": task_queue,
            "metadata": metadata or {},
            "capabilities": [c.model_dump() for c in (capabilities or [])],
        }

        response = await client.post("/api/v1/agents", json=payload)
        response.raise_for_status()
        self._agent_id = agent_id
        logger.info("Registered agent %s with registry", agent_id)
        return AgentInfo.model_validate(response.json())

    async def unregister_agent(self, agent_id: str | None = None) -> bool:
        """Unregister an agent from the registry.

        Args:
            agent_id: Agent ID to unregister (defaults to current agent)

        Returns:
            True if successfully unregistered
        """
        client = self._ensure_client()
        aid = agent_id or self._agent_id
        if not aid:
            raise ValueError("No agent_id provided and no agent registered")

        response = await client.delete(f"/api/v1/agents/{aid}")
        if response.status_code == 404:
            return False
        response.raise_for_status()
        if aid == self._agent_id:
            self._agent_id = None
        logger.info("Unregistered agent %s from registry", aid)
        return True

    async def heartbeat(self, agent_id: str | None = None) -> HeartbeatResponse:
        """Send a heartbeat for an agent.

        Args:
            agent_id: Agent ID (defaults to current agent)

        Returns:
            Heartbeat response with status
        """
        client = self._ensure_client()
        aid = agent_id or self._agent_id
        if not aid:
            raise ValueError("No agent_id provided and no agent registered")

        response = await client.put(f"/api/v1/agents/{aid}/heartbeat")
        response.raise_for_status()
        return HeartbeatResponse.model_validate(response.json())

    async def start_heartbeat(self, agent_id: str | None = None) -> None:
        """Start background heartbeat task.

        Args:
            agent_id: Agent ID to heartbeat for (defaults to current agent)
        """
        aid = agent_id or self._agent_id
        if not aid:
            raise ValueError("No agent_id provided and no agent registered")

        if self._heartbeat_task is not None:
            logger.warning("Heartbeat already running")
            return

        self._shutdown = False
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(aid), name=f"heartbeat-{aid}"
        )
        logger.info("Started heartbeat for agent %s (interval=%ss)", aid, self.heartbeat_interval)

    async def stop_heartbeat(self) -> None:
        """Stop the background heartbeat task."""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None
            logger.debug("Heartbeat task stopped")

    async def _heartbeat_loop(self, agent_id: str) -> None:
        """Background loop to send heartbeats."""
        while not self._shutdown:
            try:
                await self.heartbeat(agent_id)
                logger.debug("Heartbeat sent for %s", agent_id)
            except httpx.HTTPError as e:
                logger.warning("Heartbeat failed for %s: %s", agent_id, e)
            except Exception as e:
                logger.error("Unexpected heartbeat error for %s: %s", agent_id, e)

            await asyncio.sleep(self.heartbeat_interval)

    # -------------------------------------------------------------------------
    # Agent Queries
    # -------------------------------------------------------------------------

    async def get_agent(self, agent_id: str) -> AgentInfo | None:
        """Get agent info by ID.

        Args:
            agent_id: The agent ID

        Returns:
            Agent info or None if not found
        """
        client = self._ensure_client()
        response = await client.get(f"/api/v1/agents/{agent_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return AgentInfo.model_validate(response.json())

    async def list_agents(
        self,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AgentInfo]:
        """List registered agents.

        Args:
            status: Filter by status (optional)
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of agent info
        """
        client = self._ensure_client()
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if status:
            params["status"] = status

        response = await client.get("/api/v1/agents", params=params)
        response.raise_for_status()
        return [AgentInfo.model_validate(a) for a in response.json()]

    async def find_agents_by_capability(self, capability: str) -> list[AgentInfo]:
        """Find agents that have a specific capability.

        Args:
            capability: Capability name to search for

        Returns:
            List of agents with that capability
        """
        client = self._ensure_client()
        response = await client.get(f"/api/v1/agents/capability/{capability}")
        response.raise_for_status()
        return [AgentInfo.model_validate(a) for a in response.json()]

    # -------------------------------------------------------------------------
    # Endpoints
    # -------------------------------------------------------------------------

    async def register_endpoint(
        self,
        endpoint_id: str,
        name: str,
        service_type: str,
        internal_url: str | None = None,
        external_url: str | None = None,
        health_check_path: str = "/health",
        namespace: str | None = None,
        environment: str = "production",
        metadata: dict | None = None,
    ) -> Endpoint:
        """Register a service endpoint.

        Args:
            endpoint_id: Unique endpoint identifier
            name: Human-readable name
            service_type: Type (llm, embeddings, mcp, temporal, database)
            internal_url: Cluster-internal URL
            external_url: External URL (e.g., via Tailscale)
            health_check_path: Path for health checks
            namespace: Kubernetes namespace
            environment: Environment name
            metadata: Additional metadata

        Returns:
            The registered endpoint
        """
        client = self._ensure_client()
        payload = {
            "id": endpoint_id,
            "name": name,
            "service_type": service_type,
            "internal_url": internal_url,
            "external_url": external_url,
            "health_check_path": health_check_path,
            "namespace": namespace,
            "environment": environment,
            "metadata": metadata or {},
        }

        response = await client.post("/api/v1/endpoints", json=payload)
        response.raise_for_status()
        return Endpoint.model_validate(response.json())

    async def get_endpoint(self, endpoint_id: str) -> Endpoint | None:
        """Get endpoint by ID.

        Args:
            endpoint_id: The endpoint ID

        Returns:
            Endpoint or None if not found
        """
        client = self._ensure_client()
        response = await client.get(f"/api/v1/endpoints/{endpoint_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return Endpoint.model_validate(response.json())

    async def list_endpoints(
        self,
        service_type: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Endpoint]:
        """List service endpoints.

        Args:
            service_type: Filter by type
            status: Filter by status
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of endpoints
        """
        client = self._ensure_client()
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if service_type:
            params["service_type"] = service_type
        if status:
            params["status"] = status

        response = await client.get("/api/v1/endpoints", params=params)
        response.raise_for_status()
        return [Endpoint.model_validate(e) for e in response.json()]

    async def resolve_endpoint(
        self,
        endpoint_id: str,
        prefer_internal: bool = True,
    ) -> ResolvedEndpoint | None:
        """Resolve the best URL for an endpoint.

        Args:
            endpoint_id: The endpoint ID
            prefer_internal: Prefer internal URL if available

        Returns:
            Resolved endpoint with URL, or None if not found
        """
        client = self._ensure_client()
        params = {"prefer_internal": str(prefer_internal).lower()}
        response = await client.get(f"/api/v1/endpoints/resolve/{endpoint_id}", params=params)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return ResolvedEndpoint.model_validate(response.json())

    # -------------------------------------------------------------------------
    # Models
    # -------------------------------------------------------------------------

    async def register_model(
        self,
        model_id: str,
        name: str,
        model_type: str,
        provider: str | None = None,
        quantization: str | None = None,
        context_length: int | None = None,
        vram_required_gb: float | None = None,
        capabilities: dict | None = None,
        local_path: str | None = None,
        metadata: dict | None = None,
    ) -> Model:
        """Register an LLM model.

        Args:
            model_id: Unique model identifier
            name: Human-readable name
            model_type: Type (general, coding, embeddings, vision)
            provider: Model provider
            quantization: Quantization type
            context_length: Context window size
            vram_required_gb: VRAM requirement
            capabilities: Model capabilities
            local_path: Path on cluster storage
            metadata: Additional metadata

        Returns:
            The registered model
        """
        client = self._ensure_client()
        payload = {
            "id": model_id,
            "name": name,
            "model_type": model_type,
            "provider": provider,
            "quantization": quantization,
            "context_length": context_length,
            "vram_required_gb": vram_required_gb,
            "capabilities": capabilities or {},
            "local_path": local_path,
            "metadata": metadata or {},
        }

        response = await client.post("/api/v1/models", json=payload)
        response.raise_for_status()
        return Model.model_validate(response.json())

    async def get_model(self, model_id: str) -> Model | None:
        """Get model by ID.

        Args:
            model_id: The model ID

        Returns:
            Model or None if not found
        """
        client = self._ensure_client()
        response = await client.get(f"/api/v1/models/{model_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return Model.model_validate(response.json())

    async def list_models(
        self,
        model_type: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Model]:
        """List registered models.

        Args:
            model_type: Filter by type
            status: Filter by status
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of models
        """
        client = self._ensure_client()
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if model_type:
            params["model_type"] = model_type
        if status:
            params["status"] = status

        response = await client.get("/api/v1/models", params=params)
        response.raise_for_status()
        return [Model.model_validate(m) for m in response.json()]

    # -------------------------------------------------------------------------
    # MCP Servers
    # -------------------------------------------------------------------------

    async def register_mcp_server(
        self,
        server_id: str,
        name: str,
        transport: str,
        connection_config: dict,
        description: str | None = None,
        capabilities: list[str] | None = None,
        namespaces: list[str] | None = None,
        read_only: bool = False,
    ) -> MCPServer:
        """Register an MCP server.

        Args:
            server_id: Unique server identifier
            name: Human-readable name
            transport: Transport type (stdio, sse, streamable-http)
            connection_config: Connection configuration
            description: Server description
            capabilities: List of capability names
            namespaces: Allowed namespaces
            read_only: Whether server is read-only

        Returns:
            The registered MCP server
        """
        client = self._ensure_client()
        payload = {
            "id": server_id,
            "name": name,
            "transport": transport,
            "connection_config": connection_config,
            "description": description,
            "capabilities": capabilities or [],
            "namespaces": namespaces,
            "read_only": read_only,
        }

        response = await client.post("/api/v1/mcp/servers", json=payload)
        response.raise_for_status()
        return MCPServer.model_validate(response.json())

    async def list_mcp_servers(
        self,
        transport: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[MCPServer]:
        """List MCP servers.

        Args:
            transport: Filter by transport type
            status: Filter by status
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of MCP servers
        """
        client = self._ensure_client()
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if transport:
            params["transport"] = transport
        if status:
            params["status"] = status

        response = await client.get("/api/v1/mcp/servers", params=params)
        response.raise_for_status()
        return [MCPServer.model_validate(s) for s in response.json()]

    async def get_mcp_policy(self, agent_id: str) -> EffectivePolicy | None:
        """Get effective MCP policy for an agent.

        Args:
            agent_id: The agent ID

        Returns:
            Effective policy or None if agent not found
        """
        client = self._ensure_client()
        response = await client.get(f"/api/v1/mcp/policy/{agent_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return EffectivePolicy.model_validate(response.json())

    # -------------------------------------------------------------------------
    # Deployments
    # -------------------------------------------------------------------------

    async def record_deployment(
        self,
        agent_id: str,
        version: str,
        image_tag: str | None = None,
        git_sha: str | None = None,
        deployed_by: str | None = None,
        config_snapshot: dict | None = None,
    ) -> Deployment:
        """Record a deployment.

        Args:
            agent_id: The agent ID
            version: Version being deployed
            image_tag: Docker image tag
            git_sha: Git commit SHA
            deployed_by: Who initiated the deployment
            config_snapshot: Configuration at deployment time

        Returns:
            The deployment record
        """
        client = self._ensure_client()
        payload = {
            "agent_id": agent_id,
            "version": version,
            "image_tag": image_tag,
            "git_sha": git_sha,
            "deployed_by": deployed_by,
            "config_snapshot": config_snapshot,
        }

        response = await client.post("/api/v1/deployments", json=payload)
        response.raise_for_status()
        return Deployment.model_validate(response.json())

    async def list_deployments(
        self,
        agent_id: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Deployment]:
        """List deployments.

        Args:
            agent_id: Filter by agent
            status: Filter by status
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of deployments
        """
        client = self._ensure_client()
        if agent_id:
            response = await client.get(f"/api/v1/deployments/agent/{agent_id}")
        else:
            params: dict[str, Any] = {"skip": skip, "limit": limit}
            if status:
                params["status"] = status
            response = await client.get("/api/v1/deployments", params=params)

        response.raise_for_status()
        return [Deployment.model_validate(d) for d in response.json()]

    # -------------------------------------------------------------------------
    # Skills
    # -------------------------------------------------------------------------

    async def list_skills(
        self,
        domain: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[SkillMetadata]:
        """List skill metadata.

        Args:
            domain: Filter by domain
            status: Filter by status
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of skill metadata
        """
        client = self._ensure_client()
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if domain:
            params["domain"] = domain
        if status:
            params["status"] = status

        response = await client.get("/api/v1/skills", params=params)
        response.raise_for_status()
        return [SkillMetadata.model_validate(s) for s in response.json()]

    async def record_skill_outcome(
        self,
        skill_id: str,
        success: bool,
    ) -> SkillMetadata | None:
        """Record outcome of skill execution.

        Args:
            skill_id: The skill ID
            success: Whether execution was successful

        Returns:
            Updated skill metadata or None if not found
        """
        client = self._ensure_client()
        payload = {"success": success}
        response = await client.put(f"/api/v1/skills/{skill_id}/outcome", json=payload)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return SkillMetadata.model_validate(response.json())

    # -------------------------------------------------------------------------
    # Health
    # -------------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Check if registry service is healthy.

        Returns:
            True if service is healthy
        """
        client = self._ensure_client()
        try:
            response = await client.get("/health")
            return response.status_code == 200
        except httpx.HTTPError:
            return False


def get_registry_client(
    base_url: str | None = None,
    timeout: float = 30.0,
    heartbeat_interval: float = 30.0,
) -> RegistryClient:
    """Get the singleton registry client.

    Args:
        base_url: Registry service URL (uses KUBANI_REGISTRY_URL env if not provided)
        timeout: Request timeout in seconds
        heartbeat_interval: Heartbeat interval in seconds

    Returns:
        The registry client singleton
    """
    global _registry_client

    if _registry_client is None:
        import os

        url = base_url or os.environ.get(
            "KUBANI_REGISTRY_URL", "http://registry.ai-agents.svc:8000"
        )
        interval = float(os.environ.get("KUBANI_HEARTBEAT_INTERVAL", str(heartbeat_interval)))
        _registry_client = RegistryClient(
            base_url=url,
            timeout=timeout,
            heartbeat_interval=interval,
        )

    return _registry_client


@asynccontextmanager
async def registry_context(
    base_url: str | None = None,
    timeout: float = 30.0,
    heartbeat_interval: float = 30.0,
):
    """Context manager for registry client.

    Example:
        ```python
        async with registry_context() as client:
            await client.register_agent(...)
            await client.start_heartbeat()
            # Do work...
        # Client automatically closed
        ```
    """
    client = get_registry_client(base_url, timeout, heartbeat_interval)
    await client.connect()
    try:
        yield client
    finally:
        await client.close()
