"""
Kubani Registry MCP Server.

Provides MCP tools and resources for interacting with the Kubani Registry
from Claude Code or any MCP client.

Usage:
    # Stdio transport (local development)
    uv run registry-mcp

    # The FastAPI service also exposes an SSE endpoint for cluster access
"""

import json
import logging
import os

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Registry service URL
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8000")

# Create MCP server
server = Server("kubani-registry")


def get_client() -> httpx.Client:
    """Get HTTP client for registry API."""
    return httpx.Client(base_url=REGISTRY_URL, timeout=30.0)


# =============================================================================
# MCP Tools
# =============================================================================


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="list_agents",
            description="List all registered agents with their status and capabilities",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status (healthy, unhealthy, unknown)",
                    }
                },
            },
        ),
        Tool(
            name="get_agent",
            description="Get detailed information about a specific agent",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Agent ID"},
                },
                "required": ["agent_id"],
            },
        ),
        Tool(
            name="list_endpoints",
            description="List all service endpoints with their health status",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_type": {
                        "type": "string",
                        "description": "Filter by service type (llm, embeddings, mcp, temporal)",
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by status (healthy, unhealthy, unknown)",
                    },
                },
            },
        ),
        Tool(
            name="get_endpoint",
            description="Get details for a specific endpoint and resolve its URL",
            inputSchema={
                "type": "object",
                "properties": {
                    "endpoint_id": {"type": "string", "description": "Endpoint ID"},
                    "prefer_internal": {
                        "type": "boolean",
                        "description": "Prefer internal cluster URL",
                        "default": True,
                    },
                },
                "required": ["endpoint_id"],
            },
        ),
        Tool(
            name="list_models",
            description="List all registered LLM models with their capabilities",
            inputSchema={
                "type": "object",
                "properties": {
                    "model_type": {
                        "type": "string",
                        "description": "Filter by type (general, coding, embeddings, vision)",
                    },
                },
            },
        ),
        Tool(
            name="get_model",
            description="Get detailed information about a specific model",
            inputSchema={
                "type": "object",
                "properties": {
                    "model_id": {"type": "string", "description": "Model ID"},
                },
                "required": ["model_id"],
            },
        ),
        Tool(
            name="list_mcp_servers",
            description="List all registered MCP servers",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_mcp_policy",
            description="Get the effective MCP policy for an agent",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Agent ID"},
                },
                "required": ["agent_id"],
            },
        ),
        Tool(
            name="list_deployments",
            description="List recent deployments across all agents",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Filter by agent ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of results (default 20)",
                        "default": 20,
                    },
                },
            },
        ),
        Tool(
            name="list_skills",
            description="List skills with their confidence scores and status",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Filter by domain (K8S, NEWS, GENERAL)",
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category (DIAGNOSTIC, REMEDIATION, etc.)",
                    },
                    "min_confidence": {
                        "type": "number",
                        "description": "Minimum confidence score (0.0-1.0)",
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute an MCP tool."""
    try:
        with get_client() as client:
            if name == "list_agents":
                params = {}
                if arguments.get("status"):
                    params["status_filter"] = arguments["status"]
                response = client.get("/api/v1/agents", params=params)
                response.raise_for_status()
                agents = response.json()
                return [TextContent(type="text", text=format_agents(agents))]

            elif name == "get_agent":
                agent_id = arguments["agent_id"]
                response = client.get(f"/api/v1/agents/{agent_id}")
                response.raise_for_status()
                agent = response.json()
                return [TextContent(type="text", text=format_agent_detail(agent))]

            elif name == "list_endpoints":
                params = {}
                if arguments.get("service_type"):
                    params["service_type"] = arguments["service_type"]
                if arguments.get("status"):
                    params["status_filter"] = arguments["status"]
                response = client.get("/api/v1/endpoints", params=params)
                response.raise_for_status()
                endpoints = response.json()
                return [TextContent(type="text", text=format_endpoints(endpoints))]

            elif name == "get_endpoint":
                endpoint_id = arguments["endpoint_id"]
                prefer_internal = arguments.get("prefer_internal", True)
                response = client.get(
                    f"/api/v1/endpoints/resolve/{endpoint_id}",
                    params={"prefer_internal": prefer_internal},
                )
                response.raise_for_status()
                resolved = response.json()
                return [TextContent(type="text", text=format_resolved_endpoint(resolved))]

            elif name == "list_models":
                params = {}
                if arguments.get("model_type"):
                    params["model_type"] = arguments["model_type"]
                response = client.get("/api/v1/models", params=params)
                response.raise_for_status()
                models = response.json()
                return [TextContent(type="text", text=format_models(models))]

            elif name == "get_model":
                model_id = arguments["model_id"]
                response = client.get(f"/api/v1/models/{model_id}")
                response.raise_for_status()
                model = response.json()
                return [TextContent(type="text", text=format_model_detail(model))]

            elif name == "list_mcp_servers":
                response = client.get("/api/v1/mcp/servers")
                response.raise_for_status()
                servers = response.json()
                return [TextContent(type="text", text=format_mcp_servers(servers))]

            elif name == "get_mcp_policy":
                agent_id = arguments["agent_id"]
                response = client.get(f"/api/v1/mcp/policy/{agent_id}")
                response.raise_for_status()
                policy = response.json()
                return [TextContent(type="text", text=format_mcp_policy(policy))]

            elif name == "list_deployments":
                params = {"limit": arguments.get("limit", 20)}
                if arguments.get("agent_id"):
                    params["agent_id"] = arguments["agent_id"]
                response = client.get("/api/v1/deployments", params=params)
                response.raise_for_status()
                deployments = response.json()
                return [TextContent(type="text", text=format_deployments(deployments))]

            elif name == "list_skills":
                params = {}
                if arguments.get("domain"):
                    params["domain"] = arguments["domain"]
                if arguments.get("category"):
                    params["category"] = arguments["category"]
                if arguments.get("min_confidence"):
                    params["min_confidence"] = arguments["min_confidence"]
                response = client.get("/api/v1/skills", params=params)
                response.raise_for_status()
                skills = response.json()
                return [TextContent(type="text", text=format_skills(skills))]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except httpx.HTTPStatusError as e:
        return [
            TextContent(
                type="text",
                text=f"Registry API error: {e.response.status_code} - {e.response.text}",
            )
        ]
    except httpx.RequestError as e:
        return [TextContent(type="text", text=f"Failed to connect to registry: {e}")]


# =============================================================================
# MCP Resources
# =============================================================================


@server.list_resources()
async def list_resources() -> list[Resource]:
    """List available MCP resources."""
    resources = []

    try:
        with get_client() as client:
            # List agents as resources
            response = client.get("/api/v1/agents")
            if response.is_success:
                for agent in response.json():
                    resources.append(
                        Resource(
                            uri=f"agent://{agent['id']}",
                            name=agent["name"],
                            description=agent.get("description", ""),
                            mimeType="application/json",
                        )
                    )

            # List endpoints as resources
            response = client.get("/api/v1/endpoints")
            if response.is_success:
                for endpoint in response.json():
                    resources.append(
                        Resource(
                            uri=f"endpoint://{endpoint['id']}",
                            name=endpoint["name"],
                            description=f"{endpoint['service_type']} - {endpoint['status']}",
                            mimeType="application/json",
                        )
                    )

            # List models as resources
            response = client.get("/api/v1/models")
            if response.is_success:
                for model in response.json():
                    resources.append(
                        Resource(
                            uri=f"model://{model['id']}",
                            name=model["name"],
                            description=f"{model['model_type']} - {model['status']}",
                            mimeType="application/json",
                        )
                    )

    except Exception as e:
        logger.warning(f"Failed to list resources: {e}")

    return resources


@server.read_resource()
async def read_resource(uri: str) -> str:
    """Read an MCP resource."""
    try:
        with get_client() as client:
            if uri.startswith("agent://"):
                agent_id = uri.replace("agent://", "")
                response = client.get(f"/api/v1/agents/{agent_id}")
                response.raise_for_status()
                return json.dumps(response.json(), indent=2)

            elif uri.startswith("endpoint://"):
                endpoint_id = uri.replace("endpoint://", "")
                response = client.get(f"/api/v1/endpoints/{endpoint_id}")
                response.raise_for_status()
                return json.dumps(response.json(), indent=2)

            elif uri.startswith("model://"):
                model_id = uri.replace("model://", "")
                response = client.get(f"/api/v1/models/{model_id}")
                response.raise_for_status()
                return json.dumps(response.json(), indent=2)

            elif uri.startswith("deployment://"):
                # deployment://{agent_id}/latest
                parts = uri.replace("deployment://", "").split("/")
                if len(parts) == 2 and parts[1] == "latest":
                    agent_id = parts[0]
                    response = client.get(f"/api/v1/deployments/agent/{agent_id}/latest")
                    response.raise_for_status()
                    return json.dumps(response.json(), indent=2)

            return f"Unknown resource URI: {uri}"

    except httpx.HTTPStatusError as e:
        return f"Registry API error: {e.response.status_code} - {e.response.text}"
    except httpx.RequestError as e:
        return f"Failed to connect to registry: {e}"


# =============================================================================
# Formatters
# =============================================================================


def format_agents(agents: list) -> str:
    """Format agent list for display."""
    if not agents:
        return "No agents registered."

    lines = ["# Registered Agents\n"]
    for agent in agents:
        status_emoji = {"healthy": "✓", "unhealthy": "✗", "unknown": "?"}.get(agent["status"], "?")
        lines.append(f"## {agent['name']} ({agent['id']})")
        lines.append(f"- Status: {status_emoji} {agent['status']}")
        lines.append(f"- Version: {agent.get('version', 'unknown')}")
        if agent.get("capabilities"):
            caps = ", ".join(c["name"] for c in agent["capabilities"])
            lines.append(f"- Capabilities: {caps}")
        lines.append("")

    return "\n".join(lines)


def format_agent_detail(agent: dict) -> str:
    """Format detailed agent info."""
    lines = [
        f"# Agent: {agent['name']}",
        f"- ID: {agent['id']}",
        f"- Status: {agent['status']}",
        f"- Version: {agent.get('version', 'unknown')}",
        f"- Endpoint: {agent.get('endpoint', 'N/A')}",
        f"- Task Queue: {agent.get('task_queue', 'N/A')}",
        f"- Last Heartbeat: {agent.get('last_heartbeat', 'never')}",
        "",
        "## Capabilities",
    ]
    for cap in agent.get("capabilities", []):
        lines.append(f"- **{cap['name']}**: {cap.get('description', '')}")

    if agent.get("metadata"):
        lines.append("\n## Metadata")
        lines.append(f"```json\n{json.dumps(agent['metadata'], indent=2)}\n```")

    return "\n".join(lines)


def format_endpoints(endpoints: list) -> str:
    """Format endpoint list."""
    if not endpoints:
        return "No endpoints registered."

    lines = ["# Service Endpoints\n"]
    for ep in endpoints:
        status_emoji = {"healthy": "✓", "unhealthy": "✗", "unknown": "?"}.get(ep["status"], "?")
        lines.append(f"## {ep['name']} ({ep['id']})")
        lines.append(f"- Type: {ep['service_type']}")
        lines.append(f"- Status: {status_emoji} {ep['status']}")
        if ep.get("internal_url"):
            lines.append(f"- Internal: {ep['internal_url']}")
        if ep.get("external_url"):
            lines.append(f"- External: {ep['external_url']}")
        lines.append("")

    return "\n".join(lines)


def format_resolved_endpoint(resolved: dict) -> str:
    """Format resolved endpoint."""
    return f"""# Resolved Endpoint: {resolved['endpoint_id']}
- URL: {resolved['url']}
- Internal: {resolved['is_internal']}
- Status: {resolved['status']}"""


def format_models(models: list) -> str:
    """Format model list."""
    if not models:
        return "No models registered."

    lines = ["# LLM Models\n"]
    for model in models:
        lines.append(f"## {model['name']}")
        lines.append(f"- ID: {model['id']}")
        lines.append(f"- Type: {model['model_type']}")
        lines.append(f"- Status: {model['status']}")
        if model.get("quantization"):
            lines.append(f"- Quantization: {model['quantization']}")
        if model.get("context_length"):
            lines.append(f"- Context Length: {model['context_length']}")
        if model.get("vram_required_gb"):
            lines.append(f"- VRAM Required: {model['vram_required_gb']} GB")
        lines.append("")

    return "\n".join(lines)


def format_model_detail(model: dict) -> str:
    """Format detailed model info."""
    lines = [
        f"# Model: {model['name']}",
        f"- ID: {model['id']}",
        f"- Type: {model['model_type']}",
        f"- Provider: {model.get('provider', 'unknown')}",
        f"- Status: {model['status']}",
        f"- Quantization: {model.get('quantization', 'N/A')}",
        f"- Context Length: {model.get('context_length', 'N/A')}",
        f"- VRAM Required: {model.get('vram_required_gb', 'N/A')} GB",
        f"- Local Path: {model.get('local_path', 'N/A')}",
    ]

    if model.get("capabilities"):
        lines.append("\n## Capabilities")
        lines.append(f"```json\n{json.dumps(model['capabilities'], indent=2)}\n```")

    return "\n".join(lines)


def format_mcp_servers(servers: list) -> str:
    """Format MCP server list."""
    if not servers:
        return "No MCP servers registered."

    lines = ["# MCP Servers\n"]
    for srv in servers:
        lines.append(f"## {srv['name']} ({srv['id']})")
        lines.append(f"- Transport: {srv['transport']}")
        lines.append(f"- Status: {srv['status']}")
        lines.append(f"- Read-only: {srv['read_only']}")
        if srv.get("capabilities"):
            lines.append(f"- Capabilities: {', '.join(srv['capabilities'])}")
        lines.append("")

    return "\n".join(lines)


def format_mcp_policy(policy: dict) -> str:
    """Format MCP policy."""
    lines = [f"# MCP Policy for {policy['agent_id']}\n"]

    if policy.get("servers"):
        lines.append("## Allowed Servers")
        for srv in policy["servers"]:
            lines.append(f"- {srv['name']} ({srv['id']})")

    if policy.get("policies"):
        lines.append("\n## Policies")
        for p in policy["policies"]:
            lines.append(f"- Pattern: `{p['agent_pattern']}` -> {p['server_id']}")
            if p.get("allowed_tools"):
                lines.append(f"  - Allowed tools: {', '.join(p['allowed_tools'])}")
            if p.get("require_approval"):
                lines.append(f"  - Require approval: {', '.join(p['require_approval'])}")

    return "\n".join(lines)


def format_deployments(deployments: list) -> str:
    """Format deployment list."""
    if not deployments:
        return "No deployments recorded."

    lines = ["# Recent Deployments\n"]
    for d in deployments:
        lines.append(f"## {d['agent_id']} v{d['version']}")
        lines.append(f"- Deployed: {d['deployed_at']}")
        lines.append(f"- Status: {d['status']}")
        if d.get("image_tag"):
            lines.append(f"- Image: {d['image_tag']}")
        if d.get("deployed_by"):
            lines.append(f"- By: {d['deployed_by']}")
        if d.get("rollback_from"):
            lines.append(f"- Rollback from: #{d['rollback_from']}")
        lines.append("")

    return "\n".join(lines)


def format_skills(skills: list) -> str:
    """Format skill list."""
    if not skills:
        return "No skills registered."

    lines = ["# Skills\n"]
    for s in skills:
        conf_bar = "█" * int(s["confidence"] * 10) + "░" * (10 - int(s["confidence"] * 10))
        lines.append(f"## {s['name']} ({s['id']})")
        lines.append(f"- Domain: {s['domain']}")
        lines.append(f"- Category: {s['category']}")
        lines.append(f"- Status: {s['status']}")
        lines.append(f"- Confidence: [{conf_bar}] {s['confidence']:.2f}")
        lines.append(f"- Success/Fail: {s['success_count']}/{s['failure_count']}")
        if s.get("requires_approval"):
            lines.append("- ⚠️ Requires approval")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# Entry Point
# =============================================================================


def main() -> None:
    """Run the MCP server with stdio transport."""
    import asyncio

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
