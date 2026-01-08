"""
Agent communication and workflow coordination.

Provides A2A (Agent-to-Agent) protocol integration via Strands,
saga patterns for distributed transactions, and signal channels
for cross-workflow coordination.

Modules:
    a2a: A2A protocol integration (Strands A2AServer, AgentRegistry)
    saga: Saga patterns with compensation and signal channels
"""

from core_agents.communication.a2a import (
    STRANDS_A2A_AVAILABLE,
    # A2A Client
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
from core_agents.communication.saga import (
    Saga,
    SagaResult,
    SagaStatus,
    SagaStep,
    SignalChannelRegistry,
    SignalMessage,
    StepResult,
    create_saga_workflow_id,
    create_signal_workflow_id,
    get_signal_registry,
)

__all__ = [
    # A2A Protocol
    "STRANDS_A2A_AVAILABLE",
    "AgentCapability",
    "AgentInfo",
    "AgentRegistry",
    "get_agent_registry",
    "register_agent_on_startup",
    "register_agent_on_startup_sync",
    "get_a2a_endpoint",
    "get_task_queue_for_agent",
    "create_a2a_server",
    # A2A Client
    "A2AClient",
    "A2AClientConfig",
    "A2AQueryResult",
    "CircuitBreaker",
    "CircuitState",
    # Saga patterns
    "Saga",
    "SagaStep",
    "SagaResult",
    "SagaStatus",
    "StepResult",
    "SignalMessage",
    "SignalChannelRegistry",
    "get_signal_registry",
    "create_saga_workflow_id",
    "create_signal_workflow_id",
]
