"""
Core reusable agents and utilities for multi-agent systems.

This package provides shared components for building AI agents:

Subpackages:
    agents/          - Reusable agent implementations (DiscordAgent, MemoryAgent)
    memory/          - Memory systems (hierarchical, preferences, mem0 config)
    communication/   - A2A protocol, saga patterns, signal channels
    intelligence/    - Pattern detection and analysis
    integrations/    - External service integrations (Discord, Temporal, MCP)
    observability/   - Metrics, hooks, Prometheus metrics, and monitoring
    skills/          - Voyager-inspired skill library (knowledge about MCP tools)
    events/          - Redis Streams event bus for cross-agent communication
    approvals/       - Discord-based approval flow for dangerous actions

Root module:
    base.py          - create_agent(), create_model() factory functions

Usage:
    # Simple imports from root (re-exported for convenience)
    from core_agents import DiscordAgent, HierarchicalMemory, create_agent

    # Or import from subpackages for clarity
    from core_agents.memory import HierarchicalMemory
    from core_agents.communication import Saga, create_a2a_server
    from core_agents.integrations import get_temporal_client

    # New federated architecture modules
    from core_agents.skills import Skill, get_skill_library
    from core_agents.events import EventType, get_event_bus
    from core_agents.approvals import DiscordApprover
"""

# Base utilities (stay at root level)
# Re-export from config/ (Centralized Configuration Management)
# Re-export from agents/
from core_agents.agents import (
    DISCORD_AGENT_PROMPT,
    MEMORY_AGENT_PROMPT,
    DiscordAgent,
    MemoryAgent,
    discord_notify,
)

# Re-export from approvals/ (Discord-based approval flow)
from core_agents.approvals import (
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
    Approver,
    DiscordApprover,
)
from core_agents.base import create_agent, create_model

# Re-export from communication/
from core_agents.communication import (
    STRANDS_A2A_AVAILABLE,
    AgentCapability,
    AgentInfo,
    AgentRegistry,
    Saga,
    SagaResult,
    SagaStatus,
    SagaStep,
    SignalChannelRegistry,
    SignalMessage,
    StepResult,
    create_a2a_server,
    create_saga_workflow_id,
    create_signal_workflow_id,
    get_a2a_endpoint,
    get_agent_registry,
    get_signal_registry,
    get_task_queue_for_agent,
    register_agent_on_startup,
    register_agent_on_startup_sync,
)
from core_agents.config import (
    ApprovalConfig,
    CoreConfig,
    EmbeddingsConfig,
    EventBusConfig,
    GraphMemoryConfig,
    LLMConfig,
    ObservabilityConfig,
    RegistryConfig,
    SkillLibraryConfig,
    TemporalConfig,
    get_config,
    get_model_id,
    get_qdrant_url,
    get_redis_url,
    get_registry_url,
    get_temporal_url,
    get_vllm_url,
    is_debug_enabled,
    is_registry_enabled,
    reset_config,
)

# Re-export from events/ (Redis Streams event bus)
from core_agents.events import (
    DeploymentEvent,
    Event,
    EventBus,
    EventType,
    ImagePushedEvent,
    RedisEventBus,
    get_event_bus,
)

# Re-export from factory/ (AgentFactory pattern)
from core_agents.factory import (
    AgentConfig,
    AgentFactory,
    ModelConfig,
    SwarmConfig,
    get_agent_factory,
    quick_agent,
)

# Re-export from integrations/
from core_agents.integrations import (
    AgentPolicy,
    Colors,
    DeploymentResult,
    DiscordEmbed,
    FluxStatus,
    GitOpsAgent,
    GitOpsConfig,
    GitOpsManager,
    MCPRegistry,
    MCPServerConfig,
    get_local_temporal_client,
    get_mcp_server_config,
    get_registry,
    get_temporal_client,
    post_discord_message,
    quick_deploy,
    send_discord_message,
    send_discord_message_sync,
)

# Re-export from intelligence/
from core_agents.intelligence import (
    AlertSeverity,
    AnomalyAlert,
    AnomalyDetector,
    AnomalyType,
    CapacityForecast,
    CapacityPlanner,
    CapacityRecommendation,
    IssueRecord,
    MetricBaseline,
    MetricThreshold,
    PatternMatcher,
    PatternType,
    RecommendationType,
    RecurrencePattern,
    ResourceType,
    ResourceUsage,
    Severity,
    Urgency,
    check_metric,
    get_anomaly_detector,
    get_capacity_planner,
    get_pattern_matcher,
    get_patterns,
    record_issue,
    record_node_usage,
    suggest_prevention,
)

# Re-export from memory/
from core_agents.memory import (
    VLLM_MODEL_DIMENSIONS,
    EngagementType,
    ExtractedFacts,
    HierarchicalMemory,
    HierarchicalMemoryConfig,
    MemoryTier,
    TopicPreference,
    UserPreferences,
    UserPreferencesConfig,
    WorkingMemoryItem,
    extract_facts,
    extract_facts_sync,
    get_graph_mem0_config,
    get_mem0_config,
)

# Re-export from observability/
from core_agents.observability import (
    MetricsAggregator,
    ObservabilityHooks,
    RequestMetrics,
    TokenUsage,
    ToolCallMetric,
    create_observability_hooks,
    get_metric,
    record_agent_request,
    record_approval_completed,
    record_approval_request,
    record_event_processed,
    record_event_published,
    record_mcp_call,
    record_skill_execution,
    set_agent_info,
    start_metrics_server,
    update_skill_confidence,
)

# Re-export from skills/ (Voyager-inspired skill library)
from core_agents.skills import (
    MCPToolReference,
    QdrantSkillLibrary,
    Skill,
    SkillAction,
    SkillCategory,
    SkillDomain,
    SkillLibrary,
    SkillOutcome,
    get_skill_library,
)

# Re-export from worker/ (Generic Temporal worker)
from core_agents.worker import (
    AgentCapabilityConfig,
    AgentWorker,
    AgentWorkerConfig,
    CommandConfig,
    ScheduledWorkflowConfig,
    setup_logging,
)

__all__ = [
    # Configuration (Centralized Configuration Management)
    "CoreConfig",
    "LLMConfig",
    "EmbeddingsConfig",
    "EventBusConfig",
    "SkillLibraryConfig",
    "GraphMemoryConfig",
    "ApprovalConfig",
    "ObservabilityConfig",
    "RegistryConfig",
    "TemporalConfig",
    "get_config",
    "reset_config",
    "get_vllm_url",
    "get_model_id",
    "get_redis_url",
    "get_qdrant_url",
    "get_registry_url",
    "get_temporal_url",
    "is_debug_enabled",
    "is_registry_enabled",
    # Base utilities
    "create_agent",
    "create_model",
    # Agents
    "DiscordAgent",
    "MemoryAgent",
    "discord_notify",
    "DISCORD_AGENT_PROMPT",
    "MEMORY_AGENT_PROMPT",
    # Memory
    "get_mem0_config",
    "get_graph_mem0_config",
    "VLLM_MODEL_DIMENSIONS",
    "HierarchicalMemory",
    "HierarchicalMemoryConfig",
    "MemoryTier",
    "WorkingMemoryItem",
    "UserPreferences",
    "UserPreferencesConfig",
    "TopicPreference",
    "EngagementType",
    "ExtractedFacts",
    "extract_facts",
    "extract_facts_sync",
    # Communication
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
    # Intelligence - Pattern Detection
    "PatternMatcher",
    "PatternType",
    "RecurrencePattern",
    "IssueRecord",
    "Severity",
    "get_pattern_matcher",
    "get_patterns",
    "record_issue",
    "suggest_prevention",
    # Intelligence - Anomaly Detection
    "AnomalyDetector",
    "AnomalyAlert",
    "AnomalyType",
    "AlertSeverity",
    "MetricBaseline",
    "MetricThreshold",
    "get_anomaly_detector",
    "check_metric",
    # Intelligence - Capacity Planning
    "CapacityPlanner",
    "CapacityForecast",
    "CapacityRecommendation",
    "ResourceUsage",
    "ResourceType",
    "RecommendationType",
    "Urgency",
    "get_capacity_planner",
    "record_node_usage",
    # Integrations
    "get_temporal_client",
    "get_local_temporal_client",
    "send_discord_message",
    "send_discord_message_sync",
    "post_discord_message",
    "DiscordEmbed",
    "Colors",
    "MCPRegistry",
    "MCPServerConfig",
    "AgentPolicy",
    "get_registry",
    "get_mcp_server_config",
    # GitOps
    "GitOpsAgent",
    "GitOpsManager",
    "GitOpsConfig",
    "DeploymentResult",
    "FluxStatus",
    "quick_deploy",
    # Observability
    "create_observability_hooks",
    "ObservabilityHooks",
    "MetricsAggregator",
    "RequestMetrics",
    "ToolCallMetric",
    "TokenUsage",
    # Observability - Prometheus metrics
    "get_metric",
    "record_agent_request",
    "record_skill_execution",
    "update_skill_confidence",
    "record_mcp_call",
    "record_event_published",
    "record_event_processed",
    "record_approval_request",
    "record_approval_completed",
    "set_agent_info",
    "start_metrics_server",
    # Skills (Voyager-inspired skill library)
    "Skill",
    "SkillAction",
    "SkillCategory",
    "SkillDomain",
    "SkillOutcome",
    "MCPToolReference",
    "SkillLibrary",
    "QdrantSkillLibrary",
    "get_skill_library",
    # Events (Redis Streams event bus)
    "Event",
    "EventType",
    "EventBus",
    "RedisEventBus",
    "get_event_bus",
    "ImagePushedEvent",
    "DeploymentEvent",
    # Approvals (Discord-based approval flow)
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalStatus",
    "Approver",
    "DiscordApprover",
    # Worker (Generic Temporal worker)
    "AgentCapabilityConfig",
    "AgentWorker",
    "AgentWorkerConfig",
    "CommandConfig",
    "ScheduledWorkflowConfig",
    "setup_logging",
    # Factory (AgentFactory pattern)
    "AgentFactory",
    "AgentConfig",
    "ModelConfig",
    "SwarmConfig",
    "get_agent_factory",
    "quick_agent",
]
