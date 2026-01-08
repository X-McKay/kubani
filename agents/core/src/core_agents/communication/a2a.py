"""
Agent-to-Agent (A2A) Protocol Integration for Kubani Agents.

This module provides A2A (Agent-to-Agent) communication capabilities by
wrapping and extending Strands' built-in A2A support. It adds:
- Kubani-specific agent registry with well-known agents
- Service discovery for agent capabilities
- Temporal workflow integration helpers
- Integration with Kubernetes service discovery

Strands provides the core A2A protocol implementation (Google A2A spec):
- A2AServer: HTTP server exposing agents via A2A protocol
- StrandsA2AExecutor: Adapts Strands agents to A2A protocol

Usage:
    from strands import Agent
    from core_agents.a2a import (
        create_a2a_server,
        get_agent_registry,
        AgentCapability,
    )

    # Create a Strands agent
    agent = Agent(name="my-agent", description="My agent")

    # Expose it via A2A
    server = create_a2a_server(agent, port=9000)
    server.serve()  # Blocks, starts HTTP server

    # Or get the app for integration with existing server
    app = server.to_fastapi_app()

    # Service discovery
    registry = get_agent_registry()
    agent_info = registry.find_agent_for("pod-diagnosis")
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

# Re-export Strands A2A components for convenience
try:
    from strands.multiagent.a2a import A2AServer, StrandsA2AExecutor

    STRANDS_A2A_AVAILABLE = True
except ImportError:
    STRANDS_A2A_AVAILABLE = False
    A2AServer = None  # type: ignore
    StrandsA2AExecutor = None  # type: ignore

if TYPE_CHECKING:
    from a2a.types import AgentSkill
    from strands import Agent

logger = logging.getLogger(__name__)

# Re-export for convenience
__all__ = [
    # Strands A2A components
    "A2AServer",
    "StrandsA2AExecutor",
    "STRANDS_A2A_AVAILABLE",
    # Kubani components
    "AgentCapability",
    "AgentInfo",
    "AgentRegistry",
    "get_agent_registry",
    "register_agent_on_startup",
    "register_agent_on_startup_sync",
    "create_a2a_server",
    "get_a2a_endpoint",
    # A2A Client
    "A2AClient",
    "A2AClientConfig",
    "A2AQueryResult",
    "CircuitBreaker",
    "CircuitState",
    # Temporal integration
    "get_task_queue_for_agent",
]


@dataclass
class AgentCapability:
    """
    Describes a capability that an agent provides.

    Attributes:
        name: Capability name (e.g., "pod-diagnosis")
        description: Human-readable description
        input_schema: Expected input format (JSON Schema)
        output_schema: Expected output format (JSON Schema)
        tags: Tags for categorization
    """

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_a2a_skill(self) -> "AgentSkill":
        """Convert to A2A AgentSkill format."""
        from a2a.types import AgentSkill

        return AgentSkill(
            id=self.name,
            name=self.name,
            description=self.description,
            tags=self.tags,
        )


@dataclass
class AgentInfo:
    """
    Information about a registered agent.

    Attributes:
        id: Unique agent identifier (used as Temporal task queue)
        name: Human-readable name
        description: Agent description
        capabilities: List of capabilities this agent provides
        endpoint: How to reach this agent (URL or service name)
        version: Agent version
        metadata: Additional agent metadata
    """

    id: str
    name: str
    description: str
    capabilities: list[AgentCapability]
    endpoint: str
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)
    registered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def a2a_url(self) -> str:
        """Get the A2A protocol URL for this agent."""
        # In Kubernetes, endpoints are service names
        if "://" in self.endpoint:
            return self.endpoint
        # Default to HTTP on port 9000 (A2A default)
        return f"http://{self.endpoint}:9000/"

    def get_a2a_skills(self) -> list["AgentSkill"]:
        """Convert capabilities to A2A skills."""
        return [cap.to_a2a_skill() for cap in self.capabilities]


class AgentRegistry:
    """
    Service discovery registry for Kubani agents.

    Agents register their capabilities, and other agents can
    discover them to route requests appropriately.

    Agents are expected to self-register on startup using their
    agent_info module (e.g., k8s_monitor.agent_info.AGENT_INFO).

    In production, this is backed by:
    1. Self-registration via register_agent_on_startup()
    2. MCP registry ConfigMap for dynamic agents
    3. Kubernetes service discovery
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}
        self._capability_index: dict[str, list[str]] = {}

    def _rebuild_index(self) -> None:
        """Rebuild the capability-to-agent index."""
        self._capability_index = {}
        for agent_id, agent in self._agents.items():
            for cap in agent.capabilities:
                if cap.name not in self._capability_index:
                    self._capability_index[cap.name] = []
                self._capability_index[cap.name].append(agent_id)

    def register_agent(self, agent: AgentInfo) -> AgentInfo:
        """Register a new agent or update an existing one."""
        self._agents[agent.id] = agent
        self._rebuild_index()
        logger.info(f"Registered agent: {agent.id} with {len(agent.capabilities)} capabilities")
        return agent

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            self._rebuild_index()
            logger.info(f"Unregistered agent: {agent_id}")
            return True
        return False

    def get_agent(self, agent_id: str) -> AgentInfo | None:
        """Get agent info by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentInfo]:
        """List all registered agents."""
        return list(self._agents.values())

    def find_agents_for(self, capability: str) -> list[AgentInfo]:
        """Find agents that provide a specific capability."""
        agent_ids = self._capability_index.get(capability, [])
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def find_agent_for(self, capability: str) -> AgentInfo | None:
        """Find the first agent that provides a capability."""
        agents = self.find_agents_for(capability)
        return agents[0] if agents else None

    def get_capability(self, agent_id: str, capability_name: str) -> AgentCapability | None:
        """Get a specific capability from an agent."""
        agent = self.get_agent(agent_id)
        if agent:
            for cap in agent.capabilities:
                if cap.name == capability_name:
                    return cap
        return None


# Singleton registry
_agent_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry."""
    global _agent_registry
    if _agent_registry is None:
        _agent_registry = AgentRegistry()
    return _agent_registry


async def register_agent_on_startup(agent_info: AgentInfo) -> AgentInfo:
    """
    Register an agent with the global registry on startup.

    This should be called during agent worker initialization to make
    the agent discoverable by other agents.

    Args:
        agent_info: Agent information including capabilities

    Returns:
        The registered AgentInfo (may have updated fields like registered_at)

    Example:
        from k8s_monitor.agent_info import AGENT_INFO
        from core_agents.communication import register_agent_on_startup

        async def main():
            await register_agent_on_startup(AGENT_INFO)
            # Continue with worker startup...
    """
    registry = get_agent_registry()
    return registry.register_agent(agent_info)


def register_agent_on_startup_sync(agent_info: AgentInfo) -> AgentInfo:
    """
    Synchronous version of register_agent_on_startup.

    For use in non-async contexts.
    """
    registry = get_agent_registry()
    return registry.register_agent(agent_info)


def create_a2a_server(
    agent: "Agent",
    *,
    host: str = "0.0.0.0",
    port: int = 9000,
    http_url: str | None = None,
    version: str | None = None,
    skills: list["AgentSkill"] | None = None,
) -> "A2AServer":
    """
    Create an A2A server for a Strands agent.

    This wraps Strands' A2AServer with Kubani-specific defaults.

    Args:
        agent: The Strands Agent to expose via A2A
        host: Hostname to bind to (default: 0.0.0.0 for container use)
        port: Port to bind to (default: 9000, A2A default)
        http_url: Public URL for the agent (for load balancer scenarios)
        version: Agent version (default: from environment or 1.0.0)
        skills: A2A skills list (default: derived from agent tools)

    Returns:
        Configured A2AServer instance

    Raises:
        ImportError: If strands A2A support is not available

    Example:
        from strands import Agent
        from core_agents.a2a import create_a2a_server

        agent = Agent(name="my-agent", description="My agent")
        server = create_a2a_server(agent, port=9000)
        server.serve()  # Start HTTP server
    """
    if not STRANDS_A2A_AVAILABLE:
        raise ImportError(
            "Strands A2A support not available. Install with: pip install strands-agents[a2a]"
        )

    # Get version from environment or use default
    agent_version = version or os.environ.get("AGENT_VERSION", "1.0.0")

    return A2AServer(
        agent,
        host=host,
        port=port,
        http_url=http_url,
        version=agent_version,
        skills=skills,
    )


def get_a2a_endpoint(agent_id: str) -> str | None:
    """
    Get the A2A endpoint URL for an agent.

    Args:
        agent_id: Agent identifier

    Returns:
        A2A endpoint URL or None if agent not found
    """
    registry = get_agent_registry()
    agent = registry.get_agent(agent_id)
    return agent.a2a_url if agent else None


# Temporal workflow integration helpers


def get_task_queue_for_agent(agent_id: str) -> str:
    """
    Get the Temporal task queue name for an agent.

    By convention, Kubani agents use their ID as their Temporal task queue name.
    This allows routing workflow activities to the correct agent worker.

    Args:
        agent_id: Agent identifier

    Returns:
        Temporal task queue name
    """
    return agent_id


# =============================================================================
# A2A Client - For making queries TO other agents
# =============================================================================

import asyncio  # noqa: E402
import time  # noqa: E402
from enum import Enum  # noqa: E402

import httpx  # noqa: E402


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"  # Failure threshold exceeded, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for resilient A2A communication.

    Prevents cascading failures by stopping requests to failing services.
    """

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1

    # State
    state: CircuitState = field(default=CircuitState.CLOSED)
    failure_count: int = field(default=0)
    last_failure_time: float | None = field(default=None)
    half_open_calls: int = field(default=0)

    def record_success(self) -> None:
        """Record a successful call."""
        if self.state == CircuitState.HALF_OPEN:
            # Recovery confirmed, close the circuit
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.half_open_calls = 0
            logger.info("Circuit breaker closed - service recovered")
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Recovery failed, reopen the circuit
            self.state = CircuitState.OPEN
            self.half_open_calls = 0
            logger.warning("Circuit breaker reopened - recovery failed")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker opened - {self.failure_count} failures exceeded threshold"
            )

    def can_execute(self) -> bool:
        """Check if a request can be executed."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time is None:
                return False
            elapsed = time.time() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit breaker half-open - testing recovery")
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls < self.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False

        return False


@dataclass
class A2AClientConfig:
    """Configuration for A2A client."""

    default_timeout: float = 5.0  # Fast timeout for synchronous calls
    max_retries: int = 3
    retry_backoff: float = 0.5
    circuit_breaker_threshold: int = 5
    circuit_breaker_recovery: float = 30.0


@dataclass
class A2AQueryResult:
    """Result of an A2A query."""

    success: bool
    data: Any = None
    error: str | None = None
    latency_ms: float = 0.0
    agent_id: str | None = None
    retries: int = 0


class A2AClient:
    """
    Client for making synchronous queries to other agents via A2A protocol.

    Provides:
    - Direct agent queries with fast timeouts
    - Circuit breaker for resilience
    - Automatic retries with backoff
    - Service discovery via AgentRegistry

    Example:
        from core_agents.communication import A2AClient

        client = A2AClient()

        # Query an agent directly
        result = await client.query(
            agent="world_model",
            query="get_pod_details",
            params={"namespace": "production", "pod": "api-server"},
            timeout=2.0,
        )

        if result.success:
            print(result.data)
    """

    def __init__(
        self,
        config: A2AClientConfig | None = None,
        registry: AgentRegistry | None = None,
    ):
        self.config = config or A2AClientConfig()
        self._registry = registry
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._http_client: httpx.AsyncClient | None = None

    @property
    def registry(self) -> AgentRegistry:
        """Get the agent registry (lazy initialization)."""
        if self._registry is None:
            self._registry = get_agent_registry()
        return self._registry

    def _get_circuit_breaker(self, agent_id: str) -> CircuitBreaker:
        """Get or create a circuit breaker for an agent."""
        if agent_id not in self._circuit_breakers:
            self._circuit_breakers[agent_id] = CircuitBreaker(
                failure_threshold=self.config.circuit_breaker_threshold,
                recovery_timeout=self.config.circuit_breaker_recovery,
            )
        return self._circuit_breakers[agent_id]

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.default_timeout),
            )
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def query(
        self,
        agent: str,
        query: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> A2AQueryResult:
        """
        Query an agent via A2A protocol.

        Args:
            agent: Agent ID or name to query
            query: Query type/method to invoke
            params: Parameters for the query
            timeout: Request timeout in seconds (default: config.default_timeout)

        Returns:
            A2AQueryResult with success status and data/error
        """
        start_time = time.time()
        timeout = timeout or self.config.default_timeout

        # Get agent info from registry
        agent_info = self.registry.get_agent(agent)
        if not agent_info:
            return A2AQueryResult(
                success=False,
                error=f"Agent '{agent}' not found in registry",
                latency_ms=(time.time() - start_time) * 1000,
            )

        # Check circuit breaker
        circuit_breaker = self._get_circuit_breaker(agent)
        if not circuit_breaker.can_execute():
            return A2AQueryResult(
                success=False,
                error=f"Circuit breaker open for agent '{agent}'",
                agent_id=agent,
                latency_ms=(time.time() - start_time) * 1000,
            )

        # Make the request with retries
        retries = 0
        last_error: str | None = None

        while retries <= self.config.max_retries:
            try:
                result = await self._execute_query(
                    agent_info=agent_info,
                    query=query,
                    params=params or {},
                    timeout=timeout,
                )

                circuit_breaker.record_success()
                return A2AQueryResult(
                    success=True,
                    data=result,
                    agent_id=agent,
                    latency_ms=(time.time() - start_time) * 1000,
                    retries=retries,
                )

            except Exception as e:
                last_error = str(e)
                retries += 1

                if retries <= self.config.max_retries:
                    await asyncio.sleep(self.config.retry_backoff * retries)
                    logger.warning(f"A2A query to {agent} failed, retry {retries}: {e}")

        # All retries failed
        circuit_breaker.record_failure()
        return A2AQueryResult(
            success=False,
            error=last_error,
            agent_id=agent,
            latency_ms=(time.time() - start_time) * 1000,
            retries=retries - 1,
        )

    async def _execute_query(
        self,
        agent_info: AgentInfo,
        query: str,
        params: dict[str, Any],
        timeout: float,
    ) -> Any:
        """Execute a single query to an agent."""
        client = await self._get_http_client()
        url = f"{agent_info.a2a_url}query"

        request_body = {
            "query": query,
            "params": params,
        }

        response = await client.post(
            url,
            json=request_body,
            timeout=timeout,
        )
        response.raise_for_status()

        return response.json()

    async def health_check(self, agent: str, timeout: float = 2.0) -> bool:
        """
        Check if an agent is healthy and reachable.

        Args:
            agent: Agent ID to check
            timeout: Health check timeout

        Returns:
            True if agent is healthy, False otherwise
        """
        agent_info = self.registry.get_agent(agent)
        if not agent_info:
            return False

        try:
            client = await self._get_http_client()
            url = f"{agent_info.a2a_url}health"
            response = await client.get(url, timeout=timeout)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Health check failed for {agent}: {e}")
            return False

    def get_circuit_state(self, agent: str) -> CircuitState:
        """Get the circuit breaker state for an agent."""
        if agent in self._circuit_breakers:
            return self._circuit_breakers[agent].state
        return CircuitState.CLOSED

    def reset_circuit_breaker(self, agent: str) -> None:
        """Reset the circuit breaker for an agent."""
        if agent in self._circuit_breakers:
            self._circuit_breakers[agent] = CircuitBreaker(
                failure_threshold=self.config.circuit_breaker_threshold,
                recovery_timeout=self.config.circuit_breaker_recovery,
            )
            logger.info(f"Reset circuit breaker for agent {agent}")
