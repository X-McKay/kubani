"""
Agent-to-Agent (A2A) Protocol Module.

Provides A2A communication capabilities using Strands SDK's built-in support,
with Kubani-specific extensions for service discovery and resilience.

Example:
    from strands import Agent
    from kubani.framework.a2a import (
        create_a2a_server,
        get_agent_registry,
        A2AClient,
    )

    # Create and expose an agent via A2A
    agent = Agent(name="my-agent")
    server = create_a2a_server(agent, port=9000)

    # Query other agents
    client = A2AClient()
    result = await client.query("sentinel", "classify_event", {"event": event})
"""

from kubani.framework.a2a.protocol import (
    STRANDS_A2A_AVAILABLE,
    A2AClient,
    A2AClientConfig,
    A2AQueryResult,
    AgentCapability,
    AgentInfo,
    AgentRegistry,
    CircuitBreaker,
    CircuitState,
    create_a2a_server,
    get_a2a_endpoint,
    get_agent_registry,
    get_task_queue_for_agent,
    register_agent_on_startup,
    register_agent_on_startup_sync,
)

# Re-export Strands A2A components if available
if STRANDS_A2A_AVAILABLE:
    from kubani.framework.a2a.protocol import A2AServer, StrandsA2AExecutor

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
        "get_task_queue_for_agent",
        # A2A Client
        "A2AClient",
        "A2AClientConfig",
        "A2AQueryResult",
        "CircuitBreaker",
        "CircuitState",
    ]
else:
    __all__ = [
        "STRANDS_A2A_AVAILABLE",
        # Kubani components
        "AgentCapability",
        "AgentInfo",
        "AgentRegistry",
        "get_agent_registry",
        "register_agent_on_startup",
        "register_agent_on_startup_sync",
        "get_a2a_endpoint",
        "get_task_queue_for_agent",
        # A2A Client
        "A2AClient",
        "A2AClientConfig",
        "A2AQueryResult",
        "CircuitBreaker",
        "CircuitState",
    ]
