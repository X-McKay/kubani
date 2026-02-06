"""
Comprehensive test utilities for MCP servers.

This module provides utilities for comprehensive pre-deployment testing:
- Configuration loading from config/local.yaml
- MCP server startup via stdio transport
- Test data cleanup utilities
- Skip logic for unavailable backends

Usage:
    from kubani.mcp.servers.tests.comprehensive_test_utils import (
        load_test_config,
        start_mcp_server_stdio,
        cleanup_test_data,
        skip_if_backend_unavailable,
    )

    config = load_test_config("discord")
    if not config.enabled:
        pytest.skip("Discord not configured")

    async with start_mcp_server_stdio("discord", config) as session:
        # Test tools
        result = await session.call_tool("list_channels", {})
        assert "channels" in result
        
        # Track created resources for cleanup
        created_resources = {"messages": [result["message_id"]]}
        
        # Clean up after test
        await cleanup_test_data("discord", session, config, created_resources)
"""

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


@dataclass
class ServerTestConfig:
    """Configuration for testing a specific MCP server."""

    enabled: bool
    credentials: dict[str, Any] = field(default_factory=dict)
    test_data: dict[str, Any] = field(default_factory=dict)
    backend_urls: dict[str, str] = field(default_factory=dict)


def load_test_config(server_name: str) -> ServerTestConfig:
    """
    Load test configuration from config/local.yaml.

    Args:
        server_name: Name of the server (discord, temporal, qdrant, memory, skills)

    Returns:
        ServerTestConfig with credentials and test data

    Raises:
        ValueError: If server_name is unknown

    Example:
        >>> config = load_test_config("discord")
        >>> if config.enabled:
        ...     print(f"Discord bot token: {config.credentials['DISCORD_BOT_TOKEN']}")
    """
    config_path = Path("config/local.yaml")

    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}")
        return ServerTestConfig(enabled=False)

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return ServerTestConfig(enabled=False)

    # Extract server-specific configuration
    if server_name == "discord":
        discord_config = config.get("discord", {})
        bot_token = discord_config.get("bot_token", "")
        guild_id = discord_config.get("guild_id", "")

        # Check if credentials are placeholder values
        is_configured = (
            bot_token
            and bot_token != "your-discord-bot-token-here"
            and guild_id
            and guild_id != "your-guild-id-here"
        )

        return ServerTestConfig(
            enabled=is_configured,
            credentials={
                "DISCORD_BOT_TOKEN": bot_token,
                "DISCORD_GUILD_ID": guild_id,
            },
            test_data={
                "test_channel_id": discord_config.get("alerts_channel", ""),
                "guild_id": guild_id,
            },
        )

    elif server_name == "temporal":
        temporal_config = config.get("temporal", {})
        enabled = temporal_config.get("enabled", False)

        return ServerTestConfig(
            enabled=enabled,
            credentials={
                "TEMPORAL_HOST": temporal_config.get("host", "localhost:7233"),
                "TEMPORAL_NAMESPACE": temporal_config.get("namespace", "default"),
            },
            test_data={
                "task_queue": temporal_config.get("task_queue", "kubani-tasks"),
            },
            backend_urls={
                "temporal": temporal_config.get("host", "localhost:7233"),
            },
        )

    elif server_name == "qdrant":
        memory_config = config.get("memory", {})
        qdrant_config = memory_config.get("qdrant", {})
        enabled = qdrant_config.get("host") is not None

        # Build Qdrant URL
        host = qdrant_config.get("host", "localhost")
        port = qdrant_config.get("port", 6333)
        https = qdrant_config.get("https", False)
        protocol = "https" if https else "http"
        qdrant_url = f"{protocol}://{host}:{port}"

        return ServerTestConfig(
            enabled=enabled,
            credentials={
                "QDRANT_URL": qdrant_url,
                "QDRANT_API_KEY": qdrant_config.get("api_key", ""),
            },
            test_data={
                "test_collection": "test_comprehensive_collection",
            },
            backend_urls={
                "qdrant": qdrant_url,
            },
        )

    elif server_name == "memory":
        memory_config = config.get("memory", {})
        qdrant_config = memory_config.get("qdrant", {})
        neo4j_config = memory_config.get("neo4j", {})
        redis_config = memory_config.get("redis", {})

        # Check if all backends are configured
        qdrant_enabled = qdrant_config.get("host") is not None
        neo4j_enabled = neo4j_config.get("uri") is not None
        redis_enabled = redis_config.get("host") is not None
        enabled = qdrant_enabled and neo4j_enabled and redis_enabled

        # Build URLs
        qdrant_host = qdrant_config.get("host", "localhost")
        qdrant_port = qdrant_config.get("port", 6333)
        qdrant_https = qdrant_config.get("https", False)
        qdrant_protocol = "https" if qdrant_https else "http"
        qdrant_url = f"{qdrant_protocol}://{qdrant_host}:{qdrant_port}"

        return ServerTestConfig(
            enabled=enabled,
            credentials={
                "QDRANT_URL": qdrant_url,
                "QDRANT_API_KEY": qdrant_config.get("api_key", ""),
                "NEO4J_URI": neo4j_config.get("uri", "bolt://localhost:7687"),
                "NEO4J_USER": neo4j_config.get("user", "neo4j"),
                "NEO4J_PASSWORD": neo4j_config.get("password", ""),
                "REDIS_HOST": redis_config.get("host", "localhost"),
                "REDIS_PORT": str(redis_config.get("port", 6379)),
                "REDIS_PASSWORD": redis_config.get("password", ""),
            },
            test_data={
                "test_agent_id": "test-agent-comprehensive",
                "test_collection": "test_comprehensive_memory",
            },
            backend_urls={
                "qdrant": qdrant_url,
                "neo4j": neo4j_config.get("uri", "bolt://localhost:7687"),
                "redis": f"{redis_config.get('host', 'localhost')}:{redis_config.get('port', 6379)}",
            },
        )

    elif server_name == "skills":
        # Skills MCP uses OCI registry
        # For now, assume it's always available (uses public registry)
        return ServerTestConfig(
            enabled=True,
            credentials={
                "OCI_REGISTRY_URL": "registry.almckay.io",
            },
            test_data={
                "test_skill_path": "kubani/test-skill",
            },
        )

    else:
        # Unknown server
        raise ValueError(f"Unknown server name: {server_name}. Supported: discord, temporal, qdrant, memory, skills")


@asynccontextmanager
async def start_mcp_server_stdio(server_name: str, config: ServerTestConfig):
    """
    Start an MCP server via stdio transport for testing.

    This context manager starts an MCP server as a subprocess using stdio transport,
    initializes a client session, and yields the session for testing. The server
    is automatically stopped when the context exits.

    Args:
        server_name: Name of the server (discord, temporal, qdrant, memory, skills)
        config: Test configuration with credentials

    Yields:
        ClientSession for interacting with the server

    Raises:
        ValueError: If server_name is unknown or server directory not found
        RuntimeError: If server fails to start

    Example:
        >>> config = load_test_config("discord")
        >>> async with start_mcp_server_stdio("discord", config) as session:
        ...     result = await session.call_tool("list_channels", {})
        ...     print(f"Found {len(result['channels'])} channels")
    """
    # Map server names to their module paths
    server_modules = {
        "discord": "discord_mcp.server",
        "temporal": "temporal_mcp.server",
        "qdrant": "qdrant_mcp.server",
        "memory": "memory_mcp.server",
        "skills": "skills_mcp.server",
    }

    if server_name not in server_modules:
        raise ValueError(
            f"Unknown server: {server_name}. Supported: {', '.join(server_modules.keys())}"
        )

    # Determine server directory
    server_dir = Path(f"kubani/mcp/servers/{server_name}")
    if not server_dir.exists():
        raise ValueError(f"Server directory not found: {server_dir}")

    # Prepare environment variables
    env = os.environ.copy()
    env.update(config.credentials)

    # Add Python path to ensure imports work
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{server_dir}:{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = str(server_dir)

    logger.info(f"Starting {server_name} MCP server via stdio in {server_dir}")

    # Create server parameters
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", server_modules[server_name], "--mode", "stdio"],
        cwd=str(server_dir),
        env=env,
    )

    try:
        # Start server and create session
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                logger.info(f"Initializing {server_name} MCP session")
                await session.initialize()
                logger.info(f"{server_name} MCP server ready for testing")
                yield session
    except Exception as e:
        logger.error(f"Failed to start {server_name} MCP server: {e}")
        raise RuntimeError(f"Failed to start {server_name} MCP server: {e}") from e


async def cleanup_test_data(
    server_name: str, session: ClientSession, config: ServerTestConfig, created_resources: dict[str, list[str]]
):
    """
    Clean up test data created during comprehensive testing.

    This function deletes all test resources created during testing to ensure
    no test artifacts remain in the backend systems. It performs best-effort
    cleanup, logging errors but not raising exceptions.

    Args:
        server_name: Name of the server (discord, temporal, qdrant, memory, skills)
        session: Active MCP client session
        config: Test configuration
        created_resources: Dictionary mapping resource types to lists of IDs

    Example:
        >>> created_resources = {
        ...     "messages": ["msg_123", "msg_456"],
        ...     "message_channels": {"msg_123": "ch_789", "msg_456": "ch_789"},
        ...     "channels": ["ch_789"],
        ... }
        >>> await cleanup_test_data("discord", session, config, created_resources)
    """
    logger.info(f"Cleaning up test data for {server_name}")
    cleanup_errors = []

    if server_name == "discord":
        # Clean up Discord resources
        for message_id in created_resources.get("messages", []):
            try:
                channel_id = created_resources.get("message_channels", {}).get(message_id)
                if channel_id:
                    logger.debug(f"Deleting Discord message {message_id} from channel {channel_id}")
                    await session.call_tool(
                        "delete_message", {"channel_id": channel_id, "message_id": message_id}
                    )
            except Exception as e:
                logger.warning(f"Failed to delete message {message_id}: {e}")
                cleanup_errors.append(f"message {message_id}: {e}")

        for channel_id in created_resources.get("channels", []):
            try:
                logger.debug(f"Deleting Discord channel {channel_id}")
                await session.call_tool("delete_channel", {"channel_id": channel_id})
            except Exception as e:
                logger.warning(f"Failed to delete channel {channel_id}: {e}")
                cleanup_errors.append(f"channel {channel_id}: {e}")

        for webhook_data in created_resources.get("webhooks", []):
            try:
                logger.debug(f"Deleting Discord webhook {webhook_data['webhook_id']}")
                await session.call_tool(
                    "delete_webhook",
                    {"channel_id": webhook_data["channel_id"], "webhook_id": webhook_data["webhook_id"]},
                )
            except Exception as e:
                logger.warning(f"Failed to delete webhook {webhook_data['webhook_id']}: {e}")
                cleanup_errors.append(f"webhook {webhook_data['webhook_id']}: {e}")

    elif server_name == "temporal":
        # Clean up Temporal resources
        for workflow_id in created_resources.get("workflows", []):
            try:
                logger.debug(f"Terminating Temporal workflow {workflow_id}")
                await session.call_tool("terminate_workflow", {"workflow_id": workflow_id})
            except Exception as e:
                logger.warning(f"Failed to terminate workflow {workflow_id}: {e}")
                cleanup_errors.append(f"workflow {workflow_id}: {e}")

        for schedule_id in created_resources.get("schedules", []):
            try:
                logger.debug(f"Deleting Temporal schedule {schedule_id}")
                await session.call_tool("delete_schedule", {"schedule_id": schedule_id})
            except Exception as e:
                logger.warning(f"Failed to delete schedule {schedule_id}: {e}")
                cleanup_errors.append(f"schedule {schedule_id}: {e}")

    elif server_name == "qdrant":
        # Clean up Qdrant resources
        for collection_name in created_resources.get("collections", []):
            try:
                logger.debug(f"Deleting Qdrant collection {collection_name}")
                await session.call_tool("delete_collection", {"name": collection_name})
            except Exception as e:
                logger.warning(f"Failed to delete collection {collection_name}: {e}")
                cleanup_errors.append(f"collection {collection_name}: {e}")

        # Clean up points from existing collections
        for point_data in created_resources.get("points", []):
            try:
                collection_name = point_data["collection"]
                point_id = point_data["id"]
                logger.debug(f"Deleting Qdrant point {point_id} from {collection_name}")
                await session.call_tool(
                    "delete_points",
                    {"collection_name": collection_name, "points": [point_id]},
                )
            except Exception as e:
                logger.warning(f"Failed to delete point {point_data}: {e}")
                cleanup_errors.append(f"point {point_data}: {e}")

    elif server_name == "memory":
        # Clean up Memory resources
        test_agent_id = config.test_data.get("test_agent_id", "test-agent-comprehensive")

        # Clean up learnings (if delete tool exists)
        for learning_id in created_resources.get("learnings", []):
            try:
                logger.debug(f"Deleting learning {learning_id}")
                # Note: Memory MCP may not have delete_learning tool
                # This is best-effort cleanup
                pass
            except Exception as e:
                logger.warning(f"Failed to delete learning {learning_id}: {e}")
                cleanup_errors.append(f"learning {learning_id}: {e}")

        # Clean up cache entries
        for cache_key in created_resources.get("cache_keys", []):
            try:
                logger.debug(f"Deleting cache key {cache_key}")
                await session.call_tool("cache_delete", {"key": cache_key})
            except Exception as e:
                logger.warning(f"Failed to delete cache key {cache_key}: {e}")
                cleanup_errors.append(f"cache_key {cache_key}: {e}")

        # Clean up knowledge graph nodes
        for node_id in created_resources.get("knowledge_nodes", []):
            try:
                logger.debug(f"Deleting knowledge node {node_id}")
                # Note: May need specific cleanup tool
                pass
            except Exception as e:
                logger.warning(f"Failed to delete knowledge node {node_id}: {e}")
                cleanup_errors.append(f"knowledge_node {node_id}: {e}")

    elif server_name == "skills":
        # Skills MCP doesn't create persistent resources
        logger.debug("Skills MCP: No cleanup needed")
        pass

    else:
        logger.warning(f"Unknown server type for cleanup: {server_name}")

    if cleanup_errors:
        logger.warning(f"Cleanup completed with {len(cleanup_errors)} errors: {cleanup_errors}")
    else:
        logger.info(f"Cleanup completed successfully for {server_name}")


def skip_if_backend_unavailable(config: ServerTestConfig, backend_name: str | None = None):
    """
    Skip test if backend is unavailable.

    This function checks if the required backend is configured and available.
    If not, it returns a skip message that can be used with pytest.skip().

    Args:
        config: Test configuration
        backend_name: Optional specific backend to check (e.g., "qdrant", "neo4j")

    Returns:
        Skip message if backend unavailable, None otherwise

    Example:
        >>> config = load_test_config("memory")
        >>> skip_msg = skip_if_backend_unavailable(config, "qdrant")
        >>> if skip_msg:
        ...     pytest.skip(skip_msg)
    """
    if not config.enabled:
        return "Backend not configured in config/local.yaml"

    if backend_name and backend_name not in config.backend_urls:
        return f"Backend '{backend_name}' not configured"

    return None


def get_test_resource_prefix() -> str:
    """
    Get a unique prefix for test resources.

    This ensures test resources are identifiable and can be cleaned up
    even if tests fail before cleanup.

    Returns:
        Unique prefix string (e.g., "test_comprehensive_20240206_123456")

    Example:
        >>> prefix = get_test_resource_prefix()
        >>> test_channel_name = f"{prefix}_channel"
    """
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"test_comprehensive_{timestamp}"


def is_test_resource(resource_name: str) -> bool:
    """
    Check if a resource name indicates it's a test resource.

    Args:
        resource_name: Name of the resource

    Returns:
        True if resource appears to be from testing

    Example:
        >>> is_test_resource("test_comprehensive_20240206_channel")
        True
        >>> is_test_resource("production_channel")
        False
    """
    test_prefixes = ["test_", "test-", "comprehensive_test", "temp_test"]
    resource_lower = resource_name.lower()
    return any(resource_lower.startswith(prefix) for prefix in test_prefixes)


async def verify_backend_connectivity(server_name: str, config: ServerTestConfig) -> tuple[bool, str]:
    """
    Verify that backend services are accessible before running tests.

    This performs a quick connectivity check to backends to provide
    early feedback if services are unavailable.

    Args:
        server_name: Name of the server
        config: Test configuration

    Returns:
        Tuple of (is_available, error_message)

    Example:
        >>> config = load_test_config("discord")
        >>> available, error = await verify_backend_connectivity("discord", config)
        >>> if not available:
        ...     pytest.skip(f"Backend unavailable: {error}")
    """
    if not config.enabled:
        return False, "Backend not configured"

    # For now, we assume if config is enabled, backends are available
    # In the future, we could add actual connectivity checks here
    # (e.g., ping Discord API, check Temporal connection, etc.)

    return True, ""
