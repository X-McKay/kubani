"""
K8s-monitor agent utilities.

Wraps core_agents utilities and adds Kubernetes-specific functionality
like MCP client setup and safety hooks.
"""

import logging
import os

from strands import Agent
from strands.models.openai import OpenAIModel
from strands.tools.mcp import MCPClient

from core_agents import create_model as core_create_model

from k8s_monitor.hooks import create_default_hooks

logger = logging.getLogger(__name__)


def create_model() -> OpenAIModel:
    """
    Create the LLM model provider for k8s-monitor agents.

    Uses vLLM with OpenAI-compatible API.

    Returns:
        Configured OpenAIModel instance
    """
    vllm_url = os.environ.get("VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1")
    vllm_model = os.environ.get("VLLM_MODEL", "Qwen/Qwen3-30B-A3B")

    logger.info(f"Creating vLLM model provider: {vllm_model} at {vllm_url}")

    return core_create_model(base_url=vllm_url, model_id=vllm_model)


def create_mcp_client() -> MCPClient | None:
    """
    Create MCP client for kubernetes-mcp-server.

    The kubernetes-mcp-server provides native K8s operations via MCP protocol.

    Returns:
        MCPClient instance or None if not configured
    """
    mcp_server_url = os.environ.get(
        "KUBERNETES_MCP_SERVER_URL",
        "http://kubernetes-mcp-server.ai-agents.svc.cluster.local:8080/sse",
    )

    if not mcp_server_url:
        logger.warning("KUBERNETES_MCP_SERVER_URL not set, MCP tools unavailable")
        return None

    try:
        from mcp.client.sse import sse_client

        logger.info(f"Creating MCP client for: {mcp_server_url}")
        return MCPClient(lambda: sse_client(mcp_server_url))
    except Exception as e:
        logger.error(f"Failed to create MCP client: {e}")
        return None


def create_agent(
    name: str,
    description: str,
    system_prompt: str,
    tools: list,
    enable_mcp: bool = False,
    enable_safety: bool = True,
    enable_observability: bool = True,
) -> Agent:
    """
    Create a Strands agent with standard configuration.

    Args:
        name: Agent name (used for identification in swarm)
        description: Brief description of agent's role
        system_prompt: The agent's system prompt
        tools: List of tools available to this agent
        enable_mcp: Whether to add MCP client for K8s operations
        enable_safety: Enable safety hooks to block dangerous operations
        enable_observability: Enable logging and metrics hooks

    Returns:
        Configured Strands Agent
    """
    agent_tools = list(tools)

    # Add MCP client if enabled
    if enable_mcp:
        mcp_client = create_mcp_client()
        if mcp_client:
            agent_tools.append(mcp_client)

    # Create hooks
    hooks = create_default_hooks(
        enable_safety=enable_safety,
        enable_observability=enable_observability,
        enable_discord=False,  # Discord streaming handled by DiscordNotifierAgent
    )

    return Agent(
        model=create_model(),
        name=name,
        description=description,
        system_prompt=system_prompt,
        tools=agent_tools,
        hooks=hooks,
    )
