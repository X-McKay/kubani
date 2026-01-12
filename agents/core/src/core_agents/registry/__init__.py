"""
Registry client for Kubani agents.

Provides a client library for agents to interact with the centralized
registry service for self-registration, heartbeats, and service discovery.

Example:
    from core_agents.registry import get_registry_client, AgentInfo, AgentCapability

    # Get the singleton client
    client = get_registry_client()

    # Register an agent
    agent_info = AgentInfo(
        id="my-agent",
        name="My Agent",
        capabilities=[
            AgentCapability(name="diagnose", description="Diagnose issues")
        ],
    )
    await client.register_agent(agent_info)

    # Start heartbeat
    await client.start_heartbeat("my-agent")

    # Discover other agents
    agents = await client.find_agents_by_capability("analyze")
"""

from .client import RegistryClient, get_registry_client, registry_context
from .sync import (
    AgentManifest,
    ModelDiscovery,
    RegistrySynchronizer,
    SkillManifest,
    SkillScanner,
    SyncDirection,
    SyncResult,
    SyncStatus,
)
from .models import (
    AgentCapability,
    AgentInfo,
    Deployment,
    EffectivePolicy,
    Endpoint,
    HeartbeatResponse,
    MCPPolicy,
    MCPServer,
    Model,
    ResolvedEndpoint,
    SkillMetadata,
)

__all__ = [
    "AgentCapability",
    "AgentInfo",
    "Deployment",
    "EffectivePolicy",
    "Endpoint",
    "HeartbeatResponse",
    "MCPPolicy",
    "MCPServer",
    "Model",
    "RegistryClient",
    "ResolvedEndpoint",
    "SkillMetadata",
    "get_registry_client",
    "registry_context",
    # Sync
    "RegistrySynchronizer",
    "SkillScanner",
    "SkillManifest",
    "AgentManifest",
    "ModelDiscovery",
    "SyncResult",
    "SyncStatus",
    "SyncDirection",
]
