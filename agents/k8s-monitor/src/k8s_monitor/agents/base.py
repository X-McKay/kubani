"""
K8s-monitor agent utilities.

Wraps core_agents utilities and adds Kubernetes-specific functionality
like MCP client setup and safety hooks.
"""

import logging
import os
from typing import Any

from mcp import StdioServerParameters, stdio_client
from strands import Agent
from strands.models.openai import OpenAIModel
from strands.tools.mcp import MCPClient

from core_agents import create_model as core_create_model
from core_agents import create_observability_hooks
from k8s_monitor.hooks import create_default_hooks

logger = logging.getLogger(__name__)

# MCP transport modes
MCP_TRANSPORT_STDIO = "stdio"
MCP_TRANSPORT_SSE = "sse"


def create_model() -> OpenAIModel:
    """
    Create the LLM model provider for k8s-monitor agents.

    Uses vLLM with OpenAI-compatible API.

    Returns:
        Configured OpenAIModel instance
    """
    vllm_url = os.environ.get("VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1")
    vllm_model = os.environ.get("VLLM_MODEL", "Qwen/Qwen3-14B-FP8")

    logger.info(f"Creating vLLM model provider: {vllm_model} at {vllm_url}")

    return core_create_model(base_url=vllm_url, model_id=vllm_model)


def get_mcp_transport() -> str:
    """
    Determine which MCP transport to use.

    Environment variables:
        MCP_TRANSPORT: Force a specific transport (stdio or sse)
        KUBERNETES_MCP_SERVER_URL: If set, use SSE transport

    Returns:
        Transport mode: "stdio" or "sse"
    """
    explicit = os.environ.get("MCP_TRANSPORT", "").lower()
    if explicit in (MCP_TRANSPORT_STDIO, MCP_TRANSPORT_SSE):
        return explicit

    # If SSE URL is configured, use SSE
    if os.environ.get("KUBERNETES_MCP_SERVER_URL"):
        return MCP_TRANSPORT_SSE

    # Default to stdio for local/development
    return MCP_TRANSPORT_STDIO


def create_mcp_client_stdio() -> MCPClient:
    """
    Create MCP client using stdio transport.

    Runs kubernetes-mcp-server as a subprocess.
    Suitable for local development and testing.

    Returns:
        MCPClient using stdio transport
    """
    command = os.environ.get("MCP_K8S_COMMAND", "npx")
    args_str = os.environ.get("MCP_K8S_ARGS", "-y,@anthropics/kubernetes-mcp-server@latest")
    args = args_str.split(",")

    # Build environment for MCP server
    env = dict(os.environ)

    # Ensure KUBECONFIG is set
    if "KUBECONFIG" not in env:
        kubeconfig_paths = [
            "/etc/kubernetes/kubeconfig",
            os.path.expanduser("~/.kube/config"),
        ]
        for path in kubeconfig_paths:
            if os.path.exists(path):
                env["KUBECONFIG"] = path
                break

    params = StdioServerParameters(command=command, args=args, env=env)
    logger.info(f"Creating MCP client (stdio): {command} {' '.join(args)}")

    return MCPClient(lambda: stdio_client(params))


def create_mcp_client_sse() -> MCPClient:
    """
    Create MCP client using SSE transport.

    Connects to a running kubernetes-mcp-server service.
    Suitable for in-cluster deployment.

    Returns:
        MCPClient using SSE transport
    """
    from mcp.client.sse import sse_client

    url = os.environ.get(
        "KUBERNETES_MCP_SERVER_URL",
        "http://kubernetes-mcp-server.ai-agents.svc.cluster.local:8080/sse",
    )
    # Configure timeouts for SSE connections
    # timeout: Initial connection timeout (default 5s is too short for K8s operations)
    # sse_read_timeout: How long to wait for SSE events (default 300s is fine)
    timeout = float(os.environ.get("MCP_SSE_TIMEOUT", "30"))
    sse_read_timeout = float(os.environ.get("MCP_SSE_READ_TIMEOUT", "300"))

    logger.info(
        f"Creating MCP client (sse): {url} (timeout={timeout}s, sse_read={sse_read_timeout}s)"
    )

    return MCPClient(lambda: sse_client(url, timeout=timeout, sse_read_timeout=sse_read_timeout))


def create_mcp_client() -> MCPClient | None:
    """
    Create MCP client for kubernetes-mcp-server.

    Automatically selects transport based on environment:
    - stdio: For local development (runs npx kubernetes-mcp-server)
    - sse: For in-cluster deployment (connects to running server)

    Returns:
        MCPClient instance or None if creation fails
    """
    transport = get_mcp_transport()

    try:
        if transport == MCP_TRANSPORT_STDIO:
            return create_mcp_client_stdio()
        else:
            return create_mcp_client_sse()
    except Exception as e:
        logger.error(f"Failed to create MCP client ({transport}): {e}")
        return None


def get_mcp_tools(client: MCPClient) -> list[Any]:
    """
    Get all tools from an MCP client.

    Args:
        client: Active MCPClient

    Returns:
        List of MCP tools
    """
    return client.list_tools_sync()


def create_agent(
    name: str,
    description: str,
    system_prompt: str,
    tools: list,
    enable_mcp: bool = False,
    mcp_client: MCPClient | None = None,
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
        mcp_client: Pre-configured MCP client (used if enable_mcp=True)
        enable_safety: Enable safety hooks to block dangerous operations
        enable_observability: Enable logging and metrics hooks

    Returns:
        Configured Strands Agent
    """
    agent_tools = list(tools)

    # Add MCP client if enabled
    if enable_mcp:
        client = mcp_client or create_mcp_client()
        if client:
            agent_tools.append(client)

    # Create hooks - combine local hooks with core observability
    hooks = create_default_hooks(
        enable_safety=enable_safety,
        enable_observability=enable_observability,
        enable_discord=False,  # Discord streaming handled by DiscordNotifierAgent
    )

    # Add core observability hooks if enabled
    if enable_observability:
        obs_hooks = create_observability_hooks(enable_debug_logging=False)
        hooks.append(obs_hooks)

    return Agent(
        model=create_model(),
        name=name,
        description=description,
        system_prompt=system_prompt,
        tools=agent_tools,
        hooks=hooks,
    )
