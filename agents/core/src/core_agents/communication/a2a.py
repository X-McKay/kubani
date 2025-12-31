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
