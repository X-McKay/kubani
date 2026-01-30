"""
Kubani Dev Command - Local agent/syndicate development runner.

Provides a streamlined workflow for running agents and syndicates locally
during development. Handles MCP server lifecycle, config loading, and
result display.

Usage:
    kubani dev feed-collector           # Run an agent
    kubani dev news-digest              # Run a syndicate
    kubani dev feed-collector --no-mcp  # Skip MCP servers
    kubani dev news-digest --publish    # Actually publish to Discord
"""

import importlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from kubani.cli.mcp_manager import MCPServerManager
from kubani.cli.ui import (
    console,
    create_table,
    error,
    header,
    info,
    muted,
    print_divider,
    print_panel,
    print_table,
    success,
    warning,
)
from kubani.framework.config import KubaniConfig, reload_config

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class DevSession:
    """Tracks state for a development session."""

    target_name: str
    target_type: str  # "agent" or "syndicate"
    target_path: Path
    config: KubaniConfig
    mcp_manager: MCPServerManager
    dry_run: bool = True
    results: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Project and Config Functions
# =============================================================================


def find_project_root() -> Path:
    """Find the kubani project root directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / "kubani").is_dir() and (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return Path.cwd()


def load_config(project_root: Path) -> KubaniConfig:
    """
    Load configuration using the framework's unified config system.

    Uses get_config() which loads in order (later overrides earlier):
    1. Default values defined in model fields
    2. config/default.yaml
    3. config/{environment}.yaml
    4. Environment variables (KUBANI_ prefix)
    5. config/local.yaml (gitignored)

    Args:
        project_root: Project root directory (used to set KUBANI_CONFIG_DIR)

    Returns:
        KubaniConfig instance with all settings loaded
    """
    # Set config directory so framework knows where to find YAML files
    config_dir = project_root / "config"
    if config_dir.exists():
        os.environ.setdefault("KUBANI_CONFIG_DIR", str(config_dir))

    # Reload to pick up any new environment variables
    return reload_config()


# =============================================================================
# Target Detection
# =============================================================================


def detect_target(name: str, project_root: Path) -> tuple[str, Path]:
    """
    Detect if target is an agent or syndicate.

    Args:
        name: Target name (e.g., "feed-collector", "news-digest")
        project_root: Project root directory

    Returns:
        Tuple of (target_type, target_path)

    Raises:
        ValueError: If target not found
    """
    # Convert hyphens to underscores for directory names
    dir_name = name.replace("-", "_")

    # Check agents first
    agent_path = project_root / "kubani" / "agents" / dir_name
    if agent_path.exists() and (agent_path / "agent.py").exists():
        return "agent", agent_path

    # Check syndicates
    syndicate_path = project_root / "kubani" / "syndicates" / dir_name
    if syndicate_path.exists() and (syndicate_path / "config.yaml").exists():
        return "syndicate", syndicate_path

    # Try with original name (no underscore conversion)
    agent_path = project_root / "kubani" / "agents" / name
    if agent_path.exists() and (agent_path / "agent.py").exists():
        return "agent", agent_path

    syndicate_path = project_root / "kubani" / "syndicates" / name
    if syndicate_path.exists() and (syndicate_path / "config.yaml").exists():
        return "syndicate", syndicate_path

    raise ValueError(
        f"Target '{name}' not found. "
        f"Looked for agent at kubani/agents/{dir_name}/ "
        f"and syndicate at kubani/syndicates/{dir_name}/"
    )


# =============================================================================
# MCP Server Detection
# =============================================================================


def get_required_mcp_servers(target_type: str, target_path: Path) -> list[str]:
    """
    Determine which MCP servers are required for a target.

    Reads mcp_servers from agent config.yaml or syndicate config.yaml.

    Args:
        target_type: "agent" or "syndicate"
        target_path: Path to target directory

    Returns:
        List of MCP server names (e.g., ["discord", "memory"])
    """
    config_file = target_path / "config.yaml"
    if not config_file.exists():
        return []

    with open(config_file) as f:
        config = yaml.safe_load(f) or {}

    mcp_servers = []

    if target_type == "agent":
        # Agent config has mcp_servers list
        raw_servers = config.get("mcp_servers", [])
        for server in raw_servers:
            # Convert server names like "discord-mcp-server" to "discord"
            name = server.replace("-mcp-server", "").replace("-mcp", "")
            mcp_servers.append(name)

    elif target_type == "syndicate":
        # Syndicate: collect from all agents
        agents = config.get("agents", [])
        for agent_name in agents:
            agent_dir = agent_name.replace("-", "_")
            agent_path = target_path.parent.parent / "agents" / agent_dir
            agent_servers = get_required_mcp_servers("agent", agent_path)
            for s in agent_servers:
                if s not in mcp_servers:
                    mcp_servers.append(s)

    return mcp_servers


def set_environment_from_config(config: KubaniConfig, mcp_urls: dict[str, str]) -> None:
    """
    Set environment variables from config for agent/syndicate use.

    Args:
        config: KubaniConfig instance with typed settings
        mcp_urls: Dict of MCP server names to URLs
    """
    # LLM configuration
    if config.llm.api_url:
        os.environ["VLLM_API_URL"] = config.llm.api_url
    if config.llm.model:
        os.environ["VLLM_MODEL"] = config.llm.model

    # Embeddings configuration
    if config.embeddings.api_url:
        os.environ["EMBEDDING_API_URL"] = config.embeddings.api_url
    if config.embeddings.model:
        os.environ["EMBEDDING_MODEL"] = config.embeddings.model

    # MCP server URLs from running servers
    for name, url in mcp_urls.items():
        env_name = f"MCP_{name.upper()}_URL"
        os.environ[env_name] = url

    # Also set from config if not from running servers
    if config.mcp.discord_url:
        os.environ.setdefault("MCP_DISCORD_URL", config.mcp.discord_url)
    if config.mcp.memory_url:
        os.environ.setdefault("MCP_MEMORY_URL", config.mcp.memory_url)
    if config.mcp.temporal_url:
        os.environ.setdefault("MCP_TEMPORAL_URL", config.mcp.temporal_url)
    if config.mcp.qdrant_url:
        os.environ.setdefault("MCP_QDRANT_URL", config.mcp.qdrant_url)

    # Discord configuration
    if config.discord.bot_token:
        os.environ["DISCORD_BOT_TOKEN"] = config.discord.bot_token.get_secret_value()
    if config.discord.guild_id:
        os.environ["DISCORD_GUILD_ID"] = config.discord.guild_id
    if config.discord.digest_channel:
        os.environ["DISCORD_DIGEST_CHANNEL"] = config.discord.digest_channel
    if config.discord.breaking_news_channel:
        os.environ["DISCORD_BREAKING_CHANNEL"] = config.discord.breaking_news_channel

    # Memory backends (Qdrant)
    if config.memory.qdrant.url:
        os.environ["QDRANT_URL"] = config.memory.qdrant.url
    if config.memory.qdrant.api_key:
        os.environ["QDRANT_API_KEY"] = config.memory.qdrant.api_key.get_secret_value()

    # Memory backends (Redis)
    if config.memory.redis.url:
        os.environ["REDIS_URL"] = config.memory.redis.url


# =============================================================================
# Agent Execution
# =============================================================================


async def run_agent(agent_name: str, agent_path: Path, method: str | None = None) -> dict[str, Any]:
    """
    Run an agent's primary method directly.

    Args:
        agent_name: Name of the agent
        agent_path: Path to agent directory
        method: Specific method to call (defaults to detecting primary method)

    Returns:
        Dict with results from agent execution

    Raises:
        ValueError: If agent doesn't have expected method
    """
    # Convert directory name to module name
    module_name = agent_path.name
    import_path = f"kubani.agents.{module_name}.agent"

    logger.info(f"Loading agent from {import_path}")

    try:
        module = importlib.import_module(import_path)
    except ImportError as e:
        raise ValueError(f"Failed to import agent module: {e}") from e

    # Find the agent class (look for *Agent class)
    agent_class = None
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and name.endswith("Agent") and name != "KubaniAgent":
            agent_class = obj
            break

    if agent_class is None:
        raise ValueError(f"No Agent class found in {import_path}")

    logger.info(f"Instantiating {agent_class.__name__}")
    agent = agent_class()

    # Determine which method to call
    if method:
        method_name = method
    else:
        # Auto-detect primary method based on agent type
        method_name = _detect_agent_method(agent_class.__name__)

    if not hasattr(agent, method_name):
        raise ValueError(
            f"Agent {agent_class.__name__} does not have method '{method_name}'. "
            f"Available methods: {[m for m in dir(agent) if not m.startswith('_')]}"
        )

    logger.info(f"Calling {agent_class.__name__}.{method_name}()")

    method_func = getattr(agent, method_name)
    result = await method_func()

    # Clean up agent if it has a close method
    if hasattr(agent, "close"):
        await agent.close()

    # Convert result to dict if needed
    if hasattr(result, "__dataclass_fields__"):
        return _dataclass_to_dict(result)
    elif hasattr(result, "to_dict"):
        return result.to_dict()
    elif isinstance(result, dict):
        return result
    else:
        return {"result": result}


def _detect_agent_method(class_name: str) -> str:
    """Detect the primary method for an agent based on its class name."""
    method_map = {
        "FeedCollectorAgent": "collect",
        "ContentAnalystAgent": "full_analysis",
        "DigestPublisherAgent": "compose_and_publish",
        "CriticAgent": "evaluate_recent_executions",
        "ReflectionAgent": "reflect",
        "SkillSynthesizerAgent": "synthesize_skills",
        "EventClassifierAgent": "classify",
        "RemediatorAgent": "remediate",
        "ResearchCollectorAgent": "collect",
        "ResearchAnalystAgent": "analyze",
        "TrendAnalystAgent": "analyze_trends",
    }
    return method_map.get(class_name, "run")


def _dataclass_to_dict(obj: Any) -> dict[str, Any]:
    """Convert a dataclass to a serializable dict."""
    from dataclasses import fields, is_dataclass

    if not is_dataclass(obj):
        return obj

    result = {}
    for f in fields(obj):
        value = getattr(obj, f.name)
        if is_dataclass(value):
            result[f.name] = _dataclass_to_dict(value)
        elif isinstance(value, list):
            result[f.name] = [
                _dataclass_to_dict(v) if is_dataclass(v) else _serialize_value(v) for v in value
            ]
        else:
            result[f.name] = _serialize_value(value)
    return result


def _serialize_value(value: Any) -> Any:
    """Serialize a value to JSON-compatible format."""
    from datetime import datetime

    if isinstance(value, datetime):
        return value.isoformat()
    elif hasattr(value, "__dict__"):
        return {k: _serialize_value(v) for k, v in value.__dict__.items() if not k.startswith("_")}
    return value


# =============================================================================
# Syndicate Execution
# =============================================================================


async def run_syndicate(
    syndicate_name: str, syndicate_path: Path, dry_run: bool = True
) -> dict[str, Any]:
    """
    Run a syndicate's agents in sequence.

    For news-digest, runs:
    1. feed-collector.collect()
    2. content-analyst.full_analysis(articles)
    3. digest-publisher.compose_and_publish(articles, trends)

    Args:
        syndicate_name: Name of the syndicate
        syndicate_path: Path to syndicate directory
        dry_run: If True, skip actual publishing

    Returns:
        Combined results from all agents
    """
    config_file = syndicate_path / "config.yaml"
    with open(config_file) as f:
        syndicate_config = yaml.safe_load(f) or {}

    agents = syndicate_config.get("agents", [])
    if not agents:
        raise ValueError(f"Syndicate {syndicate_name} has no agents defined")

    project_root = find_project_root()
    results: dict[str, Any] = {"syndicate": syndicate_name, "agents": {}, "dry_run": dry_run}

    # Run agents in sequence with handoffs
    previous_result: dict[str, Any] = {}

    for agent_name in agents:
        agent_dir = agent_name.replace("-", "_")
        agent_path = project_root / "kubani" / "agents" / agent_dir

        if not agent_path.exists():
            logger.warning(f"Agent {agent_name} not found at {agent_path}")
            continue

        logger.info(f"Running agent: {agent_name}")

        try:
            # Determine method and args based on agent type and previous results
            if agent_name == "feed-collector":
                result = await run_agent(agent_name, agent_path, "collect")
                previous_result = {"articles": result.get("articles", [])}

            elif agent_name == "content-analyst":
                # Need articles from collector
                articles = previous_result.get("articles", [])
                if not articles:
                    logger.warning("No articles to analyze")
                    result = {"processed_articles": [], "trends": []}
                else:
                    result = await _run_analyst_with_articles(agent_path, articles)
                previous_result = {
                    "processed_articles": result.get("processed_articles", []),
                    "trends": result.get("trends", []),
                }

            elif agent_name == "digest-publisher":
                # Need processed articles and trends
                articles = previous_result.get("processed_articles", [])
                trends = previous_result.get("trends", [])
                if not articles:
                    logger.warning("No articles to publish")
                    result = {"success": False, "reason": "No articles"}
                else:
                    result = await _run_publisher(agent_path, articles, trends, dry_run)
                previous_result = {}

            else:
                # Generic agent run
                result = await run_agent(agent_name, agent_path)

            results["agents"][agent_name] = result

        except Exception as e:
            logger.error(f"Agent {agent_name} failed: {e}")
            results["agents"][agent_name] = {"error": str(e)}
            # Continue with other agents but don't hand off failed results

    return results


async def _run_analyst_with_articles(
    agent_path: Path, articles: list[dict[str, Any]]
) -> dict[str, Any]:
    """Run content analyst with provided articles."""
    import_path = f"kubani.agents.{agent_path.name}.agent"
    module = importlib.import_module(import_path)

    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and name.endswith("Agent") and name != "KubaniAgent":
            agent = obj()
            result = await agent.full_analysis(articles)

            if hasattr(result, "__dataclass_fields__"):
                return _dataclass_to_dict(result)
            return result

    raise ValueError("ContentAnalystAgent not found")


async def _run_publisher(
    agent_path: Path,
    articles: list[dict[str, Any]],
    trends: list[dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    """Run digest publisher with provided articles and trends."""
    import_path = f"kubani.agents.{agent_path.name}.agent"
    module = importlib.import_module(import_path)

    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and name.endswith("Agent") and name != "KubaniAgent":
            agent = obj()

            # Convert articles to serializable format if needed
            serializable_articles = []
            for article in articles:
                if hasattr(article, "__dataclass_fields__"):
                    serializable_articles.append(_dataclass_to_dict(article))
                else:
                    serializable_articles.append(article)

            serializable_trends = []
            for trend in trends:
                if hasattr(trend, "__dataclass_fields__"):
                    serializable_trends.append(_dataclass_to_dict(trend))
                else:
                    serializable_trends.append(trend)

            if dry_run:
                # Compose but don't publish
                digest, formatted = agent._compose_digest(
                    serializable_articles, serializable_trends
                )
                return {
                    "digest_id": digest.digest_id,
                    "total_articles": digest.total_articles,
                    "formatted_content": formatted,
                    "dry_run": True,
                    "would_publish_to": agent._get_discord_channel(),
                }
            else:
                result = await agent.compose_and_publish(serializable_articles, serializable_trends)
                if hasattr(result, "__dataclass_fields__"):
                    return _dataclass_to_dict(result)
                return result

    raise ValueError("DigestPublisherAgent not found")


# =============================================================================
# Display Functions
# =============================================================================


def display_session_header(session: DevSession) -> None:
    """Display header for dev session."""
    console.print()
    header(f"Kubani Dev - {session.target_name}")
    print_divider()

    info(f"Type: {session.target_type}")
    info(f"Path: {session.target_path}")
    info(f"Dry run: {session.dry_run}")

    if session.mcp_manager.servers:
        info(f"MCP servers: {', '.join(session.mcp_manager.servers.keys())}")
    else:
        muted("No MCP servers running")

    print_divider()
    console.print()


def display_agent_results(agent_name: str, result: dict[str, Any], dry_run: bool) -> None:
    """Display results from an agent run."""
    console.print()
    header(f"Results: {agent_name}")
    print_divider()

    if "error" in result:
        error(f"Agent failed: {result['error']}")
        return

    # Dispatch to specific display function based on result content
    if "articles" in result and "total_collected" in result:
        display_collection_results(result)
    elif "processed_articles" in result:
        display_analysis_results(result)
    elif "digest_id" in result or "success" in result:
        display_digest_results(result, dry_run)
    else:
        # Generic result display
        display_generic_results(result)


def display_collection_results(result: dict[str, Any]) -> None:
    """Display feed collection results."""
    success(f"Collected {result.get('total_collected', 0)} articles")

    table = create_table(
        title="Collection Stats",
        columns=["Metric", "Value"],
    )
    table.add_row("Total Collected", str(result.get("total_collected", 0)))
    table.add_row("Sources Fetched", str(result.get("sources_fetched", 0)))
    table.add_row("Duplicates Filtered", str(result.get("seen_filtered", 0)))
    table.add_row("Failed Feeds", str(result.get("failed_feeds", 0)))
    print_table(table)

    # Show sample articles
    articles = result.get("articles", [])
    if articles:
        console.print()
        info(f"Sample articles (showing {min(5, len(articles))} of {len(articles)}):")
        for article in articles[:5]:
            title = article.get("title", "Untitled")[:60]
            source = article.get("source", "Unknown")
            muted(f"  - [{source}] {title}...")


def display_analysis_results(result: dict[str, Any]) -> None:
    """Display content analysis results."""
    processed = result.get("processed_articles", [])
    trends = result.get("trends", [])
    breaking = result.get("breaking_articles", [])

    success(f"Analyzed {result.get('articles_analyzed', len(processed))} articles")

    table = create_table(
        title="Analysis Stats",
        columns=["Metric", "Value"],
    )
    table.add_row("Articles Processed", str(len(processed)))
    table.add_row("Breaking News", str(len(breaking)))
    table.add_row("Trends Identified", str(len(trends)))
    table.add_row("Failed", str(result.get("articles_failed", 0)))
    table.add_row("Duplicates Filtered", str(result.get("duplicates_filtered", 0)))
    print_table(table)

    # Show top articles by importance
    if processed:
        console.print()
        info("Top articles by importance:")
        sorted_articles = sorted(
            processed, key=lambda a: a.get("importance_score", 0), reverse=True
        )
        for article in sorted_articles[:5]:
            score = article.get("importance_score", 0)
            title = article.get("title", "Untitled")[:50]
            console.print(f"  [{score}/10] {title}...")

    # Show trends
    if trends:
        console.print()
        info("Trending topics:")
        for trend in trends[:5]:
            topic = trend.get("topic", "Unknown")
            status = trend.get("status", "rising")
            count = trend.get("article_count", 0)
            console.print(f"  - {topic} ({status}, {count} articles)")

    # Highlight breaking news
    if breaking:
        console.print()
        warning(f"BREAKING NEWS ({len(breaking)} articles):")
        for article in breaking:
            title = article.get("title", "Untitled")
            console.print(f"  [bold red]! {title}[/bold red]")


def display_digest_results(result: dict[str, Any], dry_run: bool) -> None:
    """Display digest publishing results."""
    if result.get("dry_run"):
        warning("DRY RUN - Digest was composed but not published")
        info(f"Would publish to: #{result.get('would_publish_to', 'unknown')}")
        info(f"Digest ID: {result.get('digest_id', 'unknown')}")
        info(f"Total articles: {result.get('total_articles', 0)}")

        # Show formatted content preview
        content = result.get("formatted_content", "")
        if content:
            console.print()
            print_panel(
                content[:1500] + ("..." if len(content) > 1500 else ""),
                title="Digest Preview",
                style="cyan",
            )
    elif result.get("success"):
        success("Digest published successfully!")
        info(f"Channel: #{result.get('channel', 'unknown')}")
        info(f"Chunks sent: {result.get('chunks_sent', 0)}")
        if result.get("message_id"):
            info(f"Message ID: {result['message_id']}")
    else:
        error(f"Failed to publish: {result.get('error', 'Unknown error')}")


def display_generic_results(result: dict[str, Any]) -> None:
    """Display generic results as formatted JSON."""
    # Filter out large/complex fields for display
    display_result = {}
    for key, value in result.items():
        if isinstance(value, list) and len(value) > 10:
            display_result[key] = f"[{len(value)} items]"
        elif isinstance(value, str) and len(value) > 500:
            display_result[key] = value[:500] + "..."
        else:
            display_result[key] = value

    console.print_json(json.dumps(display_result, indent=2, default=str))


def display_syndicate_results(results: dict[str, Any], dry_run: bool) -> None:
    """Display combined syndicate results."""
    console.print()
    header(f"Syndicate Results: {results.get('syndicate', 'unknown')}")
    print_divider()

    if results.get("dry_run"):
        warning("DRY RUN - No actual publishing occurred")

    agent_results = results.get("agents", {})
    for agent_name, result in agent_results.items():
        display_agent_results(agent_name, result, dry_run)


# =============================================================================
# Main Entry Point
# =============================================================================


async def run_dev_session(
    target: str,
    workflow: bool,
    publish: bool,
    mcp_servers: list[str] | None,
    no_mcp: bool,
    json_output: bool,
) -> int:
    """
    Run a development session for an agent or syndicate.

    Args:
        target: Agent or syndicate name
        workflow: Run full Temporal workflow (not implemented yet)
        publish: Actually publish to Discord (default is dry run)
        mcp_servers: Specific MCP servers to run (overrides auto-detect)
        no_mcp: Skip MCP server startup entirely
        json_output: Output results as JSON

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    project_root = find_project_root()
    mcp_manager = MCPServerManager()

    try:
        # Load configuration
        config = load_config(project_root)

        # Detect target type and path
        try:
            target_type, target_path = detect_target(target, project_root)
        except ValueError as e:
            if json_output:
                console.print_json(json.dumps({"error": str(e)}, indent=2))
            else:
                error(str(e))
            return 1

        # Create session
        session = DevSession(
            target_name=target,
            target_type=target_type,
            target_path=target_path,
            config=config,
            mcp_manager=mcp_manager,
            dry_run=not publish,
        )

        # Determine which MCP servers to start
        if no_mcp:
            servers_to_start: list[str] = []
        elif mcp_servers:
            servers_to_start = mcp_servers
        else:
            servers_to_start = get_required_mcp_servers(target_type, target_path)

        # Start MCP servers
        mcp_urls: dict[str, str] = {}
        if servers_to_start:
            if not json_output:
                info(f"Starting MCP servers: {', '.join(servers_to_start)}")

            try:
                await mcp_manager.start_servers(servers_to_start, config=None)
                mcp_urls = mcp_manager.get_server_urls()
            except Exception as e:
                if not json_output:
                    warning(f"Failed to start some MCP servers: {e}")
                    warning("Continuing without local MCP servers...")

        # Set environment variables
        set_environment_from_config(config, mcp_urls)

        # Display session header
        if not json_output:
            display_session_header(session)

        # Run the target
        if workflow:
            error("Temporal workflow mode not yet implemented")
            return 1

        if target_type == "agent":
            results = await run_agent(target, target_path)
        else:
            results = await run_syndicate(target, target_path, dry_run=session.dry_run)

        session.results = results

        # Display results
        if json_output:
            console.print_json(json.dumps(results, indent=2, default=str))
        else:
            if target_type == "agent":
                display_agent_results(target, results, session.dry_run)
            else:
                display_syndicate_results(results, session.dry_run)

            console.print()
            success("Dev session complete")

        return 0

    except Exception as e:
        logger.exception("Dev session failed")
        if json_output:
            console.print_json(json.dumps({"error": str(e)}, indent=2))
        else:
            error(f"Dev session failed: {e}")
        return 1

    finally:
        # Clean up MCP servers
        mcp_manager.stop_all()
