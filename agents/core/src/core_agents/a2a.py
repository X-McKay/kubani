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

    In production, this is backed by:
    1. Well-known agents defined in code (KNOWN_AGENTS)
    2. MCP registry ConfigMap for dynamic agents
    3. Kubernetes service discovery
    """

    # Well-known Kubani agents
    KNOWN_AGENTS = {
        "k8s-monitor": AgentInfo(
            id="k8s-monitor",
            name="Kubernetes Monitor",
            description="Monitors Kubernetes cluster health and performs automated remediation",
            endpoint="k8s-monitor.ai-agents.svc.cluster.local",
            capabilities=[
                AgentCapability(
                    name="cluster-health",
                    description="Check overall cluster health including nodes, pods, and services",
                    input_schema={},
                    output_schema={"status": "string", "issues": "array"},
                    tags=["kubernetes", "monitoring", "health"],
                ),
                AgentCapability(
                    name="pod-diagnosis",
                    description="Diagnose issues with a specific pod",
                    input_schema={"namespace": "string", "pod": "string"},
                    output_schema={"diagnosis": "string", "evidence": "array"},
                    tags=["kubernetes", "diagnosis", "pod"],
                ),
                AgentCapability(
                    name="remediation",
                    description="Attempt automated remediation of a detected issue",
                    input_schema={"issue_id": "string"},
                    output_schema={"success": "boolean", "action": "string"},
                    tags=["kubernetes", "remediation", "automation"],
                ),
            ],
        ),
        "news-monitor": AgentInfo(
            id="news-monitor",
            name="AI News Monitor",
            description="Monitors AI/ML news and generates trend analysis",
            endpoint="news-monitor.ai-agents.svc.cluster.local",
            capabilities=[
                AgentCapability(
                    name="news-digest",
                    description="Generate a curated news digest for specified topics",
                    input_schema={"topics": "array"},
                    output_schema={"articles": "array", "trends": "array"},
                    tags=["news", "ai", "digest"],
                ),
                AgentCapability(
                    name="trend-analysis",
                    description="Analyze trends in AI/ML news over a time period",
                    input_schema={"days": "integer"},
                    output_schema={"trends": "array"},
                    tags=["news", "ai", "trends", "analysis"],
                ),
            ],
        ),
    }

    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = dict(self.KNOWN_AGENTS)
        self._capability_index: dict[str, list[str]] = {}
        self._rebuild_index()

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
            "Strands A2A support not available. "
            "Install with: pip install strands-agents[a2a]"
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
