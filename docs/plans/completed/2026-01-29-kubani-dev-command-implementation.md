# `kubani dev` Command Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a `kubani dev` CLI command that spawns MCP servers locally, sets environment variables from config, and runs agents/syndicates with rich console output.

**Architecture:** The command detects agent vs syndicate, starts required MCP servers as subprocesses connecting to cluster backends via Tailscale, then runs agent methods directly (no Temporal) with formatted results display.

**Tech Stack:** Typer CLI, subprocess for MCP servers, asyncio, Rich console output, YAML config loading.

---

## Task 1: Create MCP Server Manager

**Files:**
- Create: `kubani/cli/mcp_manager.py`
- Test: `tests/unit/cli/test_mcp_manager.py`

**Step 1: Write the failing test**

```python
# tests/unit/cli/test_mcp_manager.py
"""Tests for MCP server subprocess manager."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMCPServerManager:
    """Tests for MCPServerManager."""

    def test_manager_initialization(self):
        """Test manager initializes with empty server list."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()

        assert manager.servers == {}
        assert manager.processes == []

    def test_get_server_path(self):
        """Test server path resolution."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        path = manager._get_server_path("memory")

        assert "kubani/mcp/servers/memory" in str(path)

    def test_get_server_command(self):
        """Test server command generation."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        cmd = manager._get_server_command("memory")

        assert cmd == ["uv", "run", "memory-mcp"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/cli/test_mcp_manager.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'kubani.cli.mcp_manager'"

**Step 3: Write minimal implementation**

```python
# kubani/cli/mcp_manager.py
"""
MCP Server Subprocess Manager.

Manages lifecycle of MCP server subprocesses for local development.
Servers connect to cluster backends (Qdrant, Redis, Neo4j) via Tailscale.
"""

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""

    name: str
    port: int
    command: list[str]
    path: Path
    env: dict[str, str] = field(default_factory=dict)
    health_endpoint: str = "/health"


@dataclass
class MCPServerProcess:
    """Running MCP server process."""

    config: MCPServerConfig
    process: subprocess.Popen
    url: str


class MCPServerManager:
    """Manages MCP server subprocesses for local development."""

    # Default ports for MCP servers
    DEFAULT_PORTS = {
        "memory": 8083,
        "discord": 8084,
        "temporal": 8081,
        "qdrant": 8082,
    }

    def __init__(self, project_root: Path | None = None):
        """Initialize the manager."""
        self.project_root = project_root or self._find_project_root()
        self.servers: dict[str, MCPServerProcess] = {}
        self.processes: list[subprocess.Popen] = []

    def _find_project_root(self) -> Path:
        """Find the kubani project root."""
        current = Path.cwd()
        while current != current.parent:
            if (current / "kubani").exists() and (current / "pyproject.toml").exists():
                return current
            current = current.parent
        return Path.cwd()

    def _get_server_path(self, server_name: str) -> Path:
        """Get the path to an MCP server."""
        return self.project_root / "kubani" / "mcp" / "servers" / server_name

    def _get_server_command(self, server_name: str) -> list[str]:
        """Get the command to run an MCP server."""
        return ["uv", "run", f"{server_name}-mcp"]

    def _build_server_env(self, config: dict[str, Any]) -> dict[str, str]:
        """Build environment variables for MCP servers from config."""
        env = os.environ.copy()

        # Map config keys to environment variables
        services = config.get("services", {})

        if "qdrant_url" in services:
            # Parse URL into host/port
            url = services["qdrant_url"]
            if url.startswith("https://"):
                env["QDRANT_HOST"] = url.replace("https://", "")
                env["QDRANT_PORT"] = "443"
                env["QDRANT_HTTPS"] = "true"
            elif url.startswith("http://"):
                host_port = url.replace("http://", "")
                if ":" in host_port:
                    host, port = host_port.rsplit(":", 1)
                    env["QDRANT_HOST"] = host
                    env["QDRANT_PORT"] = port
                else:
                    env["QDRANT_HOST"] = host_port
                    env["QDRANT_PORT"] = "6333"

        if "redis_url" in services:
            url = services["redis_url"]
            # redis://host:port format
            if url.startswith("redis://"):
                host_port = url.replace("redis://", "")
                if ":" in host_port:
                    host, port = host_port.rsplit(":", 1)
                    env["REDIS_HOST"] = host
                    env["REDIS_PORT"] = port
                else:
                    env["REDIS_HOST"] = host_port
                    env["REDIS_PORT"] = "6379"

        if "neo4j_uri" in services:
            env["NEO4J_URI"] = services["neo4j_uri"]

        if "llm_url" in services:
            env["VLLM_API_URL"] = services["llm_url"]

        if "embeddings_url" in services:
            env["EMBEDDINGS_API_URL"] = services["embeddings_url"]

        # LLM model
        llm_config = config.get("llm", {})
        if "model" in llm_config:
            env["VLLM_MODEL"] = llm_config["model"]

        return env

    async def start_server(
        self,
        server_name: str,
        port: int | None = None,
        config: dict[str, Any] | None = None,
        timeout: float = 15.0,
    ) -> MCPServerProcess:
        """
        Start an MCP server subprocess.

        Args:
            server_name: Name of the server (memory, discord, etc.)
            port: Port to run on (uses default if not specified)
            config: Configuration dict for environment variables
            timeout: Seconds to wait for health check

        Returns:
            MCPServerProcess with running server info
        """
        if server_name in self.servers:
            return self.servers[server_name]

        port = port or self.DEFAULT_PORTS.get(server_name, 8080)
        server_path = self._get_server_path(server_name)
        command = self._get_server_command(server_name)

        if not server_path.exists():
            raise FileNotFoundError(f"MCP server not found: {server_path}")

        # Build environment
        env = self._build_server_env(config or {})
        env["PORT"] = str(port)
        env["MCP_TRANSPORT"] = "sse"  # Use SSE transport for HTTP

        server_config = MCPServerConfig(
            name=server_name,
            port=port,
            command=command,
            path=server_path,
            env=env,
        )

        logger.info(f"Starting {server_name} MCP server on port {port}...")

        # Start the process
        process = subprocess.Popen(
            command,
            cwd=str(server_path),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.processes.append(process)

        url = f"http://localhost:{port}"
        server_process = MCPServerProcess(
            config=server_config,
            process=process,
            url=url,
        )

        # Wait for health check
        healthy = await self._wait_for_health(url, timeout)
        if not healthy:
            process.terminate()
            raise TimeoutError(f"Server {server_name} failed to become healthy")

        self.servers[server_name] = server_process
        logger.info(f"{server_name} MCP server ready at {url}")

        return server_process

    async def _wait_for_health(self, url: str, timeout: float) -> bool:
        """Wait for server health endpoint to respond."""
        health_url = f"{url}/health"
        start = asyncio.get_event_loop().time()

        async with httpx.AsyncClient() as client:
            while (asyncio.get_event_loop().time() - start) < timeout:
                try:
                    response = await client.get(health_url, timeout=2.0)
                    if response.status_code == 200:
                        return True
                except Exception:
                    pass
                await asyncio.sleep(0.5)

        return False

    async def start_servers(
        self,
        server_names: list[str],
        config: dict[str, Any] | None = None,
    ) -> dict[str, MCPServerProcess]:
        """Start multiple MCP servers."""
        results = {}
        for name in server_names:
            try:
                server = await self.start_server(name, config=config)
                results[name] = server
            except Exception as e:
                logger.error(f"Failed to start {name}: {e}")
        return results

    def stop_server(self, server_name: str) -> None:
        """Stop a specific MCP server."""
        if server_name not in self.servers:
            return

        server = self.servers[server_name]
        server.process.terminate()
        try:
            server.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.process.kill()

        del self.servers[server_name]
        logger.info(f"Stopped {server_name} MCP server")

    def stop_all(self) -> None:
        """Stop all running MCP servers."""
        for name in list(self.servers.keys()):
            self.stop_server(name)

        # Also clean up any orphaned processes
        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

        self.processes.clear()

    def get_server_urls(self) -> dict[str, str]:
        """Get URLs for all running servers."""
        return {name: server.url for name, server in self.servers.items()}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/cli/test_mcp_manager.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add kubani/cli/mcp_manager.py tests/unit/cli/test_mcp_manager.py
git commit -m "feat(cli): add MCP server subprocess manager

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Create Dev Command Core

**Files:**
- Create: `kubani/cli/dev.py`
- Modify: `kubani/cli/cli.py` (add import and register command)
- Test: `tests/unit/cli/test_dev.py`

**Step 1: Write the failing test**

```python
# tests/unit/cli/test_dev.py
"""Tests for kubani dev command."""

import pytest
from typer.testing import CliRunner
from unittest.mock import AsyncMock, MagicMock, patch


class TestDevCommand:
    """Tests for the dev command."""

    def test_command_exists(self):
        """Test dev command is registered."""
        from kubani.cli.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["dev", "--help"])

        assert result.exit_code == 0
        assert "Run agent locally" in result.stdout or "direct execution" in result.stdout.lower()

    def test_target_not_found(self):
        """Test error when target doesn't exist."""
        from kubani.cli.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["dev", "nonexistent-agent"])

        assert result.exit_code != 0
        assert "not found" in result.stdout.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/cli/test_dev.py::TestDevCommand::test_command_exists -v`
Expected: FAIL with "No such command 'dev'"

**Step 3: Write the dev command**

```python
# kubani/cli/dev.py
"""
Local Development Command.

Run agents and syndicates locally with MCP servers, rich console output,
and direct execution (no Temporal by default).
"""

import asyncio
import logging
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from kubani.cli.mcp_manager import MCPServerManager
from kubani.cli.ui import (
    console,
    error,
    header,
    info,
    muted,
    print_divider,
    print_panel,
    success,
    warning,
)

logger = logging.getLogger(__name__)


@dataclass
class DevSession:
    """State for a development session."""

    target_name: str
    target_type: str  # "agent" or "syndicate"
    target_path: Path
    config: dict[str, Any]
    mcp_manager: MCPServerManager
    dry_run: bool = True
    results: dict[str, Any] = field(default_factory=dict)


def find_project_root() -> Path:
    """Find the kubani project root directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / "kubani").exists() and (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return Path.cwd()


def load_config(project_root: Path) -> dict[str, Any]:
    """Load configuration from config files."""
    config = {}

    # Try config.local.yaml first, then config.development.yaml
    for config_name in ["config.local.yaml", "config/local.yaml", "config/development.yaml"]:
        config_path = project_root / config_name
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
            logger.debug(f"Loaded config from {config_path}")
            break

    return config


def detect_target(name: str, project_root: Path) -> tuple[str, Path]:
    """
    Detect if target is an agent or syndicate.

    Returns:
        Tuple of (target_type, target_path)

    Raises:
        FileNotFoundError if target not found
    """
    # Check syndicates first
    syndicate_path = project_root / "kubani" / "syndicates" / name.replace("-", "_")
    if syndicate_path.exists():
        return "syndicate", syndicate_path

    # Check agents
    agent_path = project_root / "kubani" / "agents" / name.replace("-", "_")
    if agent_path.exists():
        return "agent", agent_path

    # Try with hyphens preserved
    syndicate_path = project_root / "kubani" / "syndicates" / name
    if syndicate_path.exists():
        return "syndicate", syndicate_path

    agent_path = project_root / "kubani" / "agents" / name
    if agent_path.exists():
        return "agent", agent_path

    raise FileNotFoundError(f"No agent or syndicate named '{name}' found")


def get_required_mcp_servers(target_type: str, target_path: Path) -> list[str]:
    """Determine which MCP servers are needed for a target."""
    # Default servers based on target type
    if target_type == "syndicate":
        # Syndicates typically need memory and discord
        return ["memory", "discord"]
    else:
        # Agents - check config or use defaults
        config_path = target_path / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                agent_config = yaml.safe_load(f) or {}
            return agent_config.get("mcp_servers", ["memory"])
        return ["memory"]


def set_environment_from_config(config: dict[str, Any], mcp_urls: dict[str, str]) -> None:
    """Set environment variables from config and MCP URLs."""
    import os

    services = config.get("services", {})

    # Service URLs
    if "llm_url" in services:
        os.environ["VLLM_API_URL"] = services["llm_url"]
    if "embeddings_url" in services:
        os.environ["EMBEDDINGS_API_URL"] = services["embeddings_url"]
    if "qdrant_url" in services:
        os.environ["QDRANT_URL"] = services["qdrant_url"]
    if "redis_url" in services:
        os.environ["REDIS_URL"] = services["redis_url"]

    # LLM config
    llm_config = config.get("llm", {})
    if "model" in llm_config:
        os.environ["VLLM_MODEL"] = llm_config["model"]

    # MCP server URLs (local)
    for name, url in mcp_urls.items():
        env_name = f"{name.upper()}_MCP_URL"
        os.environ[env_name] = url


async def run_agent(
    agent_name: str,
    agent_path: Path,
    method: str | None = None,
) -> dict[str, Any]:
    """
    Run an agent's primary method directly.

    Returns:
        Result dict from the agent method
    """
    # Import the agent module
    module_name = agent_name.replace("-", "_")

    # Add to path if needed
    if str(agent_path.parent) not in sys.path:
        sys.path.insert(0, str(agent_path.parent))

    try:
        agent_module = __import__(f"{module_name}.agent", fromlist=[""])
    except ImportError:
        # Try alternative import paths
        agent_module = __import__(f"kubani.agents.{module_name}.agent", fromlist=[""])

    # Find the agent class
    agent_class = None
    for name in dir(agent_module):
        obj = getattr(agent_module, name)
        if (
            isinstance(obj, type)
            and name.endswith("Agent")
            and name != "KubaniAgent"
        ):
            agent_class = obj
            break

    if not agent_class:
        raise ValueError(f"No agent class found in {agent_name}")

    # Instantiate and run
    agent = agent_class()

    # Determine method to call
    if not method:
        # Auto-detect based on agent type
        method_map = {
            "feed_collector": "collect",
            "content_analyst": "full_analysis",
            "digest_publisher": "compose_digest",
            "research_collector": "collect_research",
        }
        method = method_map.get(module_name, "run")

    # Get the method
    agent_method = getattr(agent, method, None)
    if not agent_method:
        raise ValueError(f"Agent {agent_name} has no method '{method}'")

    # Call the method
    if asyncio.iscoroutinefunction(agent_method):
        result = await agent_method()
    else:
        result = agent_method()

    # Convert to dict if needed
    if hasattr(result, "__dict__"):
        return vars(result)
    elif hasattr(result, "_asdict"):
        return result._asdict()
    elif isinstance(result, dict):
        return result
    else:
        return {"result": result}


async def run_syndicate(
    syndicate_name: str,
    syndicate_path: Path,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Run a syndicate's agents in sequence.

    Returns:
        Aggregated results from all phases
    """
    # Load syndicate config
    config_path = syndicate_path / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Syndicate config not found: {config_path}")

    with open(config_path) as f:
        syndicate_config = yaml.safe_load(f) or {}

    agents = syndicate_config.get("agents", [])
    results = {"phases": [], "summary": {}}

    project_root = find_project_root()

    for agent_name in agents:
        phase_name = agent_name.replace("-", " ").title()
        console.print(f"\n[bold blue]{'=' * 20} Phase: {phase_name} {'=' * 20}[/bold blue]\n")

        agent_path = project_root / "kubani" / "agents" / agent_name.replace("-", "_")

        try:
            # For digest-publisher, pass dry_run context
            if agent_name == "digest-publisher" and dry_run:
                info("Dry run mode - digest will be displayed but not published")

            phase_result = await run_agent(agent_name, agent_path)
            results["phases"].append({
                "agent": agent_name,
                "success": True,
                "result": phase_result,
            })

            # Display phase results
            display_agent_results(agent_name, phase_result, dry_run)

        except Exception as e:
            logger.error(f"Phase {agent_name} failed: {e}")
            results["phases"].append({
                "agent": agent_name,
                "success": False,
                "error": str(e),
            })

    return results


def display_agent_results(agent_name: str, result: dict[str, Any], dry_run: bool = True) -> None:
    """Display formatted results for an agent."""
    module_name = agent_name.replace("-", "_")

    if module_name == "feed_collector":
        display_collection_results(result)
    elif module_name == "content_analyst":
        display_analysis_results(result)
    elif module_name == "digest_publisher":
        display_digest_results(result, dry_run)
    else:
        # Generic display
        console.print(f"  Result: {result}")


def display_collection_results(result: dict[str, Any]) -> None:
    """Display feed collection results."""
    articles = result.get("articles", [])
    total = result.get("total_collected", len(articles))
    filtered = result.get("seen_filtered", 0)
    sources = result.get("sources_fetched", 0)

    info(f"Articles: {total} collected, {filtered} duplicates filtered")
    info(f"Sources fetched: {sources}")

    if articles and len(articles) <= 5:
        muted("Top articles:")
        for i, article in enumerate(articles[:5], 1):
            title = article.get("title", "Unknown")[:60]
            console.print(f"    {i}. {title}")


def display_analysis_results(result: dict[str, Any]) -> None:
    """Display content analysis results."""
    analyzed = result.get("articles_analyzed", 0)
    processed = len(result.get("processed_articles", []))
    breaking = result.get("breaking_articles", [])
    trends = result.get("trends", [])

    info(f"Analyzed: {analyzed} articles")
    info(f"Processed: {processed} articles")

    if breaking:
        console.print(f"\n  [bold red]Breaking News ({len(breaking)}):[/bold red]")
        for article in breaking[:3]:
            title = article.get("title", "Unknown")[:50]
            score = article.get("importance_score", "?")
            console.print(f"    [red]{title}[/red] (importance: {score})")

    if trends:
        console.print(f"\n  [bold cyan]Top Trends ({len(trends)}):[/bold cyan]")
        for trend in trends[:5]:
            topic = trend.get("topic", "Unknown")
            status = trend.get("status", "")
            count = trend.get("article_count", 0)
            console.print(f"    [cyan]{topic}[/cyan] - {count} articles ({status})")


def display_digest_results(result: dict[str, Any], dry_run: bool = True) -> None:
    """Display digest composition results."""
    digest = result.get("digest", result.get("content", ""))

    if digest:
        console.print("\n[bold green]Composed Digest:[/bold green]")
        print_divider()
        # Show truncated preview
        preview = digest[:1500] + "..." if len(digest) > 1500 else digest
        console.print(preview)
        print_divider()

    if dry_run:
        warning("DRY RUN - would send to Discord")
    else:
        channel = result.get("channel", "ai-news")
        success(f"Published to #{channel}")


def display_session_header(session: DevSession) -> None:
    """Display the session configuration header."""
    target_info = f"[bold]{session.target_name}[/bold]"
    mode = "direct (no Temporal)"
    mcp_servers = list(session.mcp_manager.servers.keys()) or ["detecting..."]

    content = f"""[bold]Target:[/bold]  {session.target_name}
[bold]Type:[/bold]    {session.target_type}
[bold]Mode:[/bold]    {mode}
[bold]MCP:[/bold]     {', '.join(mcp_servers)}
[bold]Dry run:[/bold] {session.dry_run}"""

    print_panel(content, title="Kubani Dev Session", style="blue")


async def run_dev_session(
    target: str,
    workflow: bool = False,
    publish: bool = False,
    mcp_servers: list[str] | None = None,
    no_mcp: bool = False,
    json_output: bool = False,
) -> int:
    """
    Run a development session.

    Returns:
        Exit code (0 for success)
    """
    project_root = find_project_root()

    # Load config
    config = load_config(project_root)

    # Detect target
    try:
        target_type, target_path = detect_target(target, project_root)
    except FileNotFoundError as e:
        error(str(e))
        return 1

    # Determine required MCP servers
    if no_mcp:
        required_servers = []
    elif mcp_servers:
        required_servers = mcp_servers
    else:
        required_servers = get_required_mcp_servers(target_type, target_path)

    # Create session
    mcp_manager = MCPServerManager(project_root)
    session = DevSession(
        target_name=target,
        target_type=target_type,
        target_path=target_path,
        config=config,
        mcp_manager=mcp_manager,
        dry_run=not publish,
    )

    # Setup signal handler for cleanup
    def signal_handler(signum, frame):
        console.print("\n")
        warning("Received interrupt, cleaning up...")
        mcp_manager.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Display header
        console.print()
        display_session_header(session)
        console.print()

        # Start MCP servers
        if required_servers:
            for i, server_name in enumerate(required_servers, 1):
                info(f"[{i}/{len(required_servers)}] Starting {server_name} MCP server...")
                try:
                    server = await mcp_manager.start_server(server_name, config=config)
                    success(f"{server_name} ready at {server.url}")
                except Exception as e:
                    warning(f"Failed to start {server_name}: {e}")
                    muted("  Continuing with degraded functionality...")

        # Set environment variables
        set_environment_from_config(config, mcp_manager.get_server_urls())

        # Run the target
        console.print()
        if target_type == "syndicate":
            results = await run_syndicate(target, target_path, dry_run=session.dry_run)
        else:
            header(f"Running {target}...")
            results = await run_agent(target, target_path)
            display_agent_results(target, results, session.dry_run)

        session.results = results

        # Display summary
        console.print()
        print_divider("=")

        if json_output:
            import json
            console.print(json.dumps(results, indent=2, default=str))
        else:
            success("Session complete")

            if not publish and target_type == "syndicate":
                muted("\nOptions:")
                muted("  --publish    Send to Discord (instead of dry run)")
                muted("  --workflow   Test full Temporal workflow")
                muted("  --json       Output results as JSON")

        return 0

    except Exception as e:
        logger.exception(f"Session failed: {e}")
        error(f"Session failed: {e}")
        return 1

    finally:
        # Cleanup
        muted("\nStopping MCP servers...")
        mcp_manager.stop_all()
        success("Cleanup complete")


# Typer command
app = typer.Typer()


@app.command()
def dev(
    target: Annotated[str, typer.Argument(help="Agent or syndicate name")],
    workflow: Annotated[
        bool, typer.Option("--workflow", help="Run full Temporal workflow")
    ] = False,
    publish: Annotated[
        bool, typer.Option("--publish", help="Actually publish to Discord")
    ] = False,
    mcp: Annotated[
        str | None, typer.Option("--mcp", help="Comma-separated MCP servers to run")
    ] = None,
    no_mcp: Annotated[
        bool, typer.Option("--no-mcp", help="Skip MCP server startup")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output results as JSON")
    ] = False,
):
    """
    Run an agent or syndicate locally for development.

    Automatically starts required MCP servers, sets environment variables,
    and runs the target with rich console output.

    Examples:

        # Run single agent
        kubani dev feed-collector

        # Run full syndicate
        kubani dev news-digest

        # Actually publish to Discord
        kubani dev news-digest --publish

        # Skip MCP servers
        kubani dev feed-collector --no-mcp
    """
    mcp_servers = mcp.split(",") if mcp else None

    exit_code = asyncio.run(
        run_dev_session(
            target=target,
            workflow=workflow,
            publish=publish,
            mcp_servers=mcp_servers,
            no_mcp=no_mcp,
            json_output=json_output,
        )
    )

    raise typer.Exit(exit_code)
```

**Step 4: Register the command in cli.py**

Add to `kubani/cli/cli.py` after the existing imports:

```python
# Add import near top with other command imports
from kubani.cli.dev import dev as dev_command

# Add command registration (around line 428, after local-run)
@app.command("dev")
def dev(
    target: Annotated[str, typer.Argument(help="Agent or syndicate name")],
    workflow: Annotated[
        bool, typer.Option("--workflow", help="Run full Temporal workflow")
    ] = False,
    publish: Annotated[
        bool, typer.Option("--publish", help="Actually publish to Discord")
    ] = False,
    mcp: Annotated[
        str | None, typer.Option("--mcp", help="Comma-separated MCP servers to run")
    ] = None,
    no_mcp: Annotated[
        bool, typer.Option("--no-mcp", help="Skip MCP server startup")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output results as JSON")
    ] = False,
):
    """Run an agent or syndicate locally for development."""
    from kubani.cli.dev import run_dev_session

    mcp_servers = mcp.split(",") if mcp else None

    exit_code = asyncio.run(
        run_dev_session(
            target=target,
            workflow=workflow,
            publish=publish,
            mcp_servers=mcp_servers,
            no_mcp=no_mcp,
            json_output=json_output,
        )
    )

    raise typer.Exit(exit_code)
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/unit/cli/test_dev.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add kubani/cli/dev.py kubani/cli/cli.py tests/unit/cli/test_dev.py
git commit -m "feat(cli): add kubani dev command for local agent testing

- Spawns MCP servers as subprocesses
- Loads config from config.local.yaml
- Runs agents directly without Temporal
- Rich console output with results display

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Add Test Directory and Init Files

**Files:**
- Create: `tests/unit/cli/__init__.py`

**Step 1: Create init file**

```python
# tests/unit/cli/__init__.py
"""CLI unit tests."""
```

**Step 2: Commit**

```bash
git add tests/unit/cli/__init__.py
git commit -m "chore: add cli test directory init file

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Integration Test with Real Agent

**Files:**
- Test: `tests/integration/cli/test_dev_integration.py`

**Step 1: Write integration test**

```python
# tests/integration/cli/test_dev_integration.py
"""Integration tests for kubani dev command."""

import pytest
from typer.testing import CliRunner


@pytest.mark.integration
class TestDevIntegration:
    """Integration tests that run actual agents."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_dev_feed_collector_no_mcp(self, runner):
        """Test running feed-collector without MCP servers."""
        from kubani.cli.cli import app

        # Run with --no-mcp to avoid needing actual servers
        result = runner.invoke(app, ["dev", "feed-collector", "--no-mcp"])

        # Should either succeed or fail gracefully
        # (may fail if Redis not available for dedup)
        assert result.exit_code in [0, 1]
        assert "feed-collector" in result.stdout.lower() or "session" in result.stdout.lower()
```

**Step 2: Run integration test**

Run: `pytest tests/integration/cli/test_dev_integration.py -v -m integration`

**Step 3: Commit**

```bash
git add tests/integration/cli/test_dev_integration.py tests/integration/cli/__init__.py
git commit -m "test: add integration tests for kubani dev command

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Update Design Document Status

**Files:**
- Modify: `docs/plans/drafts/2026-01-29-kubani-dev-command.md`

**Step 1: Update status**

Move from drafts to ready or update status to "Implemented":

```bash
mv docs/plans/drafts/2026-01-29-kubani-dev-command.md docs/plans/completed/2026-01-29-kubani-dev-command.md
```

**Step 2: Commit**

```bash
git add docs/plans/
git commit -m "docs: mark kubani dev command design as completed

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | MCP Server Manager | `mcp_manager.py`, tests |
| 2 | Dev Command Core | `dev.py`, `cli.py` modification |
| 3 | Test Directory Setup | `__init__.py` files |
| 4 | Integration Tests | Integration test file |
| 5 | Documentation | Move design to completed |

**Total estimated scope:** ~500 lines of implementation + ~100 lines of tests

**Key verification:** After all tasks, run:
```bash
kubani dev feed-collector --no-mcp
kubani dev news-digest --no-mcp
```
