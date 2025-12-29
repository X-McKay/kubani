"""
Core reusable agents and utilities for multi-agent systems.

This package provides shared components for building AI agents:

Subpackages:
    agents/          - Reusable agent implementations (DiscordAgent, MemoryAgent)
    memory/          - Memory systems (hierarchical, preferences, mem0 config)
    communication/   - A2A protocol, saga patterns, signal channels
    intelligence/    - Pattern detection and analysis
    integrations/    - External service integrations (Discord, Temporal, MCP)
    observability/   - Metrics, hooks, and monitoring

Root module:
    base.py          - create_agent(), create_model() factory functions

Usage:
    # Simple imports from root (re-exported for convenience)
    from core_agents import DiscordAgent, HierarchicalMemory, create_agent

    # Or import from subpackages for clarity
    from core_agents.memory import HierarchicalMemory
    from core_agents.communication import Saga, create_a2a_server
    from core_agents.integrations import get_temporal_client
"""

# Base utilities (stay at root level)
# Re-export from agents/
from core_agents.agents import (
    DISCORD_AGENT_PROMPT,
    MEMORY_AGENT_PROMPT,
    DiscordAgent,
    MemoryAgent,
    discord_notify,
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
)

# Re-export from integrations/
from core_agents.integrations import (
    AgentPolicy,
    Colors,
    DiscordEmbed,
    MCPRegistry,
    MCPServerConfig,
    get_local_temporal_client,
    get_mcp_server_config,
    get_registry,
    get_temporal_client,
    post_discord_message,
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
    K8S_GRAPH_PROMPT,
    NEWS_GRAPH_PROMPT,
    VLLM_MODEL_DIMENSIONS,
    EngagementType,
    HierarchicalMemory,
    HierarchicalMemoryConfig,
    MemoryTier,
    TopicPreference,
    UserPreferences,
    UserPreferencesConfig,
    WorkingMemoryItem,
    get_graph_mem0_config,
    get_k8s_graph_mem0_config,
    get_mem0_config,
    get_news_graph_mem0_config,
)

# Re-export from observability/
from core_agents.observability import (
    MetricsAggregator,
    ObservabilityHooks,
    RequestMetrics,
    TokenUsage,
    ToolCallMetric,
    create_observability_hooks,
)

__all__ = [
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
    "get_k8s_graph_mem0_config",
    "get_news_graph_mem0_config",
    "K8S_GRAPH_PROMPT",
    "NEWS_GRAPH_PROMPT",
    "VLLM_MODEL_DIMENSIONS",
    "HierarchicalMemory",
    "HierarchicalMemoryConfig",
    "MemoryTier",
    "WorkingMemoryItem",
    "UserPreferences",
    "UserPreferencesConfig",
    "TopicPreference",
    "EngagementType",
    # Communication
    "STRANDS_A2A_AVAILABLE",
    "AgentCapability",
    "AgentInfo",
    "AgentRegistry",
    "get_agent_registry",
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
    # Observability
    "create_observability_hooks",
    "ObservabilityHooks",
    "MetricsAggregator",
    "RequestMetrics",
    "ToolCallMetric",
    "TokenUsage",
]
