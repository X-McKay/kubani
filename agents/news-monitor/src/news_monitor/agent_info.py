"""
Agent information for news-monitor.

Defines capabilities and metadata for self-registration with the agent registry.
"""

import os

from core_agents.communication import AgentCapability, AgentInfo

# Agent version from environment or default
AGENT_VERSION = os.environ.get("AGENT_VERSION", "0.3.3")

# News-monitor agent capabilities
AGENT_INFO = AgentInfo(
    id="news-monitor",
    name="AI News Monitor",
    description="Monitors AI/ML news and generates trend analysis digests",
    endpoint=os.environ.get("AGENT_ENDPOINT", "news-monitor.ai-agents.svc.cluster.local"),
    version=AGENT_VERSION,
    capabilities=[
        AgentCapability(
            name="news-digest",
            description="Generate a curated news digest for AI/ML topics",
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
        AgentCapability(
            name="breaking-news",
            description="Detect and report breaking AI/ML news",
            input_schema={},
            output_schema={"articles": "array", "alert_level": "string"},
            tags=["news", "ai", "breaking", "alerts"],
        ),
    ],
    metadata={
        "task_queue": "news-monitor",
        "discord_channel": "ai-news",
    },
)
