"""
Kubernetes monitoring agent using Strands SDK.

This agent analyzes cluster health using the Kubernetes tools
and generates human-readable summaries with recommendations.
"""

import os
import sys
from typing import Any

from strands import Agent

from k8s_monitor.tools import ALL_TOOLS

# Add agent_platform to path if running standalone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

try:
    from agent_platform.llm_client import create_vllm_model_provider
except ImportError:
    # Fallback for when agent_platform is not installed
    from strands.models.openai import OpenAIModel

    def create_vllm_model_provider(**kwargs: Any) -> OpenAIModel:
        return OpenAIModel(
            client_args={
                "base_url": os.environ.get(
                    "VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1"
                ),
                "api_key": "not-needed",
            },
            model_id=os.environ.get("VLLM_MODEL", "openai/gpt-oss-20b"),
        )


SYSTEM_PROMPT = """You are a Kubernetes cluster health monitoring assistant. Analyze the cluster and produce a concise summary.

DISCORD FORMATTING RULES:
- Use **bold** for section names and emphasis
- Use `backticks` for inline values
- For tables, use triple backticks (```) to create code blocks with ASCII tables
- Use simple bullet points with • or -
- Keep total response under 1500 characters

EXAMPLE TABLE FORMAT (inside code block):
```
Node         Status   CPU    Memory
────────────────────────────────────
master-1     Ready    45%    62%
worker-1     Ready    78%    54%
```

OUTPUT STRUCTURE:
**Status:** Healthy / Warning / Critical

**Summary:** One sentence overview

**Key Metrics:** (use code block for table if helpful)

**Issues:** (bullet list, only if problems exist)

**Recommendation:** One actionable sentence

Be concise. Focus on actionable information."""


def create_monitoring_agent() -> Agent:
    """
    Create a Strands agent configured for Kubernetes monitoring.

    Returns:
        Configured Agent instance with K8s tools and vLLM backend.
    """
    model = create_vllm_model_provider()

    return Agent(
        model=model,
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


def analyze_cluster() -> str:
    """
    Run cluster analysis and return a summary.

    This function creates the agent, runs the analysis, and returns
    the formatted summary string.

    Returns:
        String containing the cluster health summary.
    """
    agent = create_monitoring_agent()

    # Run the agent with a prompt to analyze the cluster
    result = agent(
        """Check cluster health using the available tools (nodes, pods, events, deployments).
        Provide a concise Discord-friendly summary. Use code blocks for any tables."""
    )

    # Extract the final response from the agent
    return str(result)


if __name__ == "__main__":
    # Allow running directly for testing
    print(analyze_cluster())
