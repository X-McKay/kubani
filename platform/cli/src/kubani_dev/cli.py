"""
Kubani Development CLI - Typer-based entry point.

Provides a unified interface for agent development and testing.
Migrated from Click to Typer for better type hints and auto-completion.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from kubani_dev import __version__

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("kubani-dev")


def find_project_root() -> Path:
    """Find the kubani project root directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / "agents").exists() and (current / "skills").exists():
            return current
        current = current.parent
    return Path.cwd()


# Create main app
app = typer.Typer(
    name="kubani-dev",
    help="Kubani Development CLI - Accelerate your agent development.",
    no_args_is_help=True,
)


def version_callback(value: bool):
    if value:
        typer.echo(f"kubani-dev {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose logging")
    ] = False,
    version: Annotated[
        bool,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version"),
    ] = False,
):
    """Kubani Development CLI - Accelerate your agent development."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)


# -----------------------------------------------------------------------------
# Init Command
# -----------------------------------------------------------------------------


@app.command()
def init(
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Overwrite existing configuration")
    ] = False,
):
    """Initialize kubani-dev configuration."""
    from kubani_dev.config import init_config

    project_root = find_project_root()
    config_file = init_config(project_root, force=force)

    typer.echo(f"✓ Initialized kubani-dev at {config_file}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("  1. Edit .kubani-dev/config.yaml to configure your environment")
    typer.echo("  2. Run 'kubani-dev run <agent>' to start developing")
    typer.echo("  3. Run 'kubani-dev skill auto -d \"...\"' to create skills")


# -----------------------------------------------------------------------------
# Run Command
# -----------------------------------------------------------------------------


@app.command()
def run(
    agent: Annotated[str, typer.Argument(help="Agent name to run")],
    hot_reload: Annotated[
        bool, typer.Option("--hot-reload", "-r", help="Enable hot-reloading")
    ] = True,
    port: Annotated[int, typer.Option("--port", "-p", help="Port for agent server")] = 8080,
    mock_mcp: Annotated[bool, typer.Option("--mock-mcp", help="Use mock MCP servers")] = False,
    mock_redis: Annotated[bool, typer.Option("--mock-redis", help="Use mock Redis")] = False,
):
    """Run an agent locally for development."""
    from kubani_dev.runner import AgentRunner

    project_root = find_project_root()
    logger.info(f"Starting {agent} agent (hot-reload={hot_reload})")

    runner = AgentRunner(
        agent_name=agent,
        project_root=project_root,
        hot_reload=hot_reload,
        port=port,
        mock_mcp=mock_mcp,
        mock_redis=mock_redis,
    )

    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        logger.info("Shutting down...")


# -----------------------------------------------------------------------------
# Test Command
# -----------------------------------------------------------------------------


@app.command()
def test(
    agent: Annotated[Optional[str], typer.Argument(help="Agent name (optional)")] = None,
    coverage: Annotated[
        bool, typer.Option("--coverage", "-c", help="Generate coverage report")
    ] = False,
    watch: Annotated[
        bool, typer.Option("--watch", "-w", help="Watch mode - rerun on changes")
    ] = False,
    filter: Annotated[
        Optional[str], typer.Option("--filter", "-k", help="Filter tests by name pattern")
    ] = None,
):
    """Run tests for an agent or all agents."""
    from kubani_dev.testing import TestRunner

    project_root = find_project_root()

    runner = TestRunner(
        project_root=project_root,
        agent_name=agent,
        coverage=coverage,
        watch=watch,
        filter_pattern=filter,
    )

    exit_code = runner.run()
    sys.exit(exit_code)


# -----------------------------------------------------------------------------
# Dashboard Command
# -----------------------------------------------------------------------------


@app.command()
def dashboard(
    port: Annotated[int, typer.Option("--port", "-p", help="Dashboard port")] = 3000,
    host: Annotated[str, typer.Option("--host", "-h", help="Dashboard host")] = "localhost",
):
    """Start the observability dashboard."""
    from kubani_dev.dashboard import start_dashboard

    project_root = find_project_root()
    logger.info(f"Starting dashboard at http://{host}:{port}")

    start_dashboard(
        project_root=project_root,
        host=host,
        port=port,
    )


# -----------------------------------------------------------------------------
# New Agent Command
# -----------------------------------------------------------------------------


@app.command("new")
def new_agent(
    name: Annotated[str, typer.Argument(help="Agent name")],
    template: Annotated[
        str, typer.Option("--template", "-t", help="Agent template to use")
    ] = "basic",
    directory: Annotated[
        Optional[Path], typer.Option("--directory", "-d", help="Target directory")
    ] = None,
):
    """Create a new agent from a template."""
    from kubani_dev.scaffold import create_agent

    project_root = find_project_root()
    target_dir = directory or project_root / "agents" / name

    logger.info(f"Creating new agent '{name}' from template '{template}'")

    create_agent(
        name=name,
        template=template,
        target_dir=target_dir,
        project_root=project_root,
    )

    logger.info(f"Agent created at {target_dir}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo(f"  1. cd {target_dir}")
    typer.echo(f"  2. Edit src/{name.replace('-', '_')}/agent.py")
    typer.echo(f"  3. kubani-dev run {name}")


# -----------------------------------------------------------------------------
# Sync Command
# -----------------------------------------------------------------------------


@app.command()
def sync(
    skills: Annotated[bool, typer.Option("--skills/--no-skills", help="Sync skills")] = True,
    agents: Annotated[bool, typer.Option("--agents/--no-agents", help="Sync agents")] = True,
    mcp: Annotated[
        bool, typer.Option("--mcp/--no-mcp", help="Sync MCP servers and policies")
    ] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be synced")] = False,
    registry_url: Annotated[
        str, typer.Option("--registry-url", envvar="REGISTRY_URL", help="Registry service URL")
    ] = "http://localhost:8000",
):
    """Sync Git resources to the registry."""
    from kubani_dev.sync import RegistrySync, print_sync_results

    project_root = find_project_root()

    if dry_run:
        logger.info("Dry run mode - no changes will be made")

    logger.info(f"Syncing to registry at {registry_url}")

    syncer = RegistrySync(project_root, registry_url)

    results = asyncio.run(
        syncer.sync_all(
            dry_run=dry_run,
            skills=skills,
            agents=agents,
            mcp=mcp,
        )
    )

    print_sync_results(results)

    total_failed = sum(r.failed for r in results.values())
    if total_failed > 0:
        sys.exit(1)


# -----------------------------------------------------------------------------
# Trace Command
# -----------------------------------------------------------------------------


@app.command()
def trace(
    trace_id: Annotated[Optional[str], typer.Argument(help="Trace ID to view")] = None,
    agent: Annotated[
        Optional[str], typer.Option("--agent", "-a", help="Filter by agent name")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of traces to show")] = 10,
    status: Annotated[
        Optional[str], typer.Option("--status", "-s", help="Filter by status")
    ] = None,
):
    """View and analyze execution traces."""
    from kubani_dev.trace import TraceStore, TraceViewer

    project_root = find_project_root()
    store = TraceStore(project_root)
    viewer = TraceViewer(store)

    if trace_id:
        output = asyncio.run(viewer.show_trace(trace_id))
        typer.echo(output)
    else:
        output = asyncio.run(viewer.list_traces(agent=agent, limit=limit))
        typer.echo(output)


# -----------------------------------------------------------------------------
# Metrics Command
# -----------------------------------------------------------------------------


@app.command()
def metrics(
    agent: Annotated[Optional[str], typer.Argument(help="Agent name (optional)")] = None,
    format: Annotated[str, typer.Option("--format", "-f", help="Output format")] = "text",
    export: Annotated[
        Optional[Path], typer.Option("--export", "-e", help="Export metrics to file")
    ] = None,
):
    """View and export agent metrics."""
    from kubani_dev.metrics import MetricsCollector, MetricsViewer

    project_root = find_project_root()
    collector = MetricsCollector(project_root)
    viewer = MetricsViewer(collector)

    if format == "json":
        output = collector.export_json()
    elif format == "prometheus":
        output = collector.export_prometheus()
    else:
        if agent:
            output = viewer.format_agent_dashboard(agent)
        else:
            output = viewer.format_summary()

    if export:
        export.write_text(output)
        typer.echo(f"Exported metrics to {export}")
    else:
        typer.echo(output)


# -----------------------------------------------------------------------------
# Monitor Command
# -----------------------------------------------------------------------------


@app.command()
def monitor(
    agent: Annotated[str, typer.Argument(help="Agent name to monitor")],
    env: Annotated[str, typer.Option("--env", "-e", help="Environment")] = "dev",
    follow: Annotated[
        bool, typer.Option("--follow", "-f", help="Follow logs in real-time")
    ] = False,
):
    """Monitor agent deployment in a cluster."""
    from kubani_dev.deploy import ProductionMonitor

    project_root = find_project_root()
    mon = ProductionMonitor(agent, project_root, env)

    if follow:
        typer.echo(f"Following logs for {agent} in {env}...")
        try:
            asyncio.run(mon.watch())
        except KeyboardInterrupt:
            typer.echo("\nStopped following logs")
    else:
        pods = mon.get_pods()
        if not pods:
            typer.echo(f"No pods found for {agent} in {env}")
            return

        typer.echo(f"Pods for {agent} in {env}:")
        for pod in pods:
            name = pod.get("metadata", {}).get("name", "unknown")
            status = pod.get("status", {}).get("phase", "Unknown")
            typer.echo(f"  {name}: {status}")


# -----------------------------------------------------------------------------
# Build Command
# -----------------------------------------------------------------------------


@app.command()
def build(
    agent: Annotated[str, typer.Argument(help="Agent name to build")],
    tag: Annotated[str, typer.Option("--tag", "-t", help="Image tag")] = "latest",
    push: Annotated[
        bool, typer.Option("--push", "-p", help="Push to registry after build")
    ] = False,
    registry: Annotated[
        Optional[str], typer.Option("--registry", "-r", help="Container registry")
    ] = None,
):
    """Build agent container image."""
    from kubani_dev.deploy import AgentBuilder, BuildConfig

    project_root = find_project_root()

    config = BuildConfig(
        agent_name=agent,
        project_root=project_root,
        registry=registry or "",
        tag=tag,
        push=push,
    )

    builder = AgentBuilder(config)

    if builder.build():
        typer.echo(f"✓ Built {agent}:{tag}")
    else:
        typer.echo(f"✗ Build failed for {agent}")
        sys.exit(1)


# -----------------------------------------------------------------------------
# Local Run Command
# -----------------------------------------------------------------------------


@app.command("local-run")
def local_run(
    agent: Annotated[str, typer.Argument(help="Agent name to run locally")],
    temporal: Annotated[str, typer.Option("--temporal", help="Temporal mode")] = "local",
    output: Annotated[str, typer.Option("--output", help="Output routing")] = "console",
    tunnel: Annotated[
        bool, typer.Option("--tunnel/--no-tunnel", help="Enable tunnel to cluster services")
    ] = False,
    tunnel_method: Annotated[
        str, typer.Option("--tunnel-method", help="Tunnel method")
    ] = "kubectl-forward",
):
    """Run an agent locally with cluster service connectivity."""
    from kubani_dev.local_run import local_run as do_local_run

    do_local_run.callback(agent, temporal, output, tunnel, tunnel_method, False)


# -----------------------------------------------------------------------------
# Deploy Command
# -----------------------------------------------------------------------------


@app.command()
def deploy(
    target: Annotated[str, typer.Argument(help="Target to deploy")],
    version: Annotated[
        Optional[str], typer.Option("--version", "-v", help="Version to deploy")
    ] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Force deployment")] = False,
    skip_verification: Annotated[
        bool, typer.Option("--skip-verification", help="Skip health verification")
    ] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be deployed")] = False,
):
    """Deploy an agent or service to the cluster."""
    from kubani_dev.deploy import deploy_command

    exit_code = asyncio.run(
        deploy_command(
            target=target,
            version=version,
            force=force,
            skip_verification=skip_verification,
            dry_run=dry_run,
        )
    )
    sys.exit(exit_code)


# -----------------------------------------------------------------------------
# Skill and Agent Command Groups
# -----------------------------------------------------------------------------

# Import Click command groups
from kubani_dev.commands.skill import skill_group
from kubani_dev.commands.agent import agent_group

# Import Typer command groups
from kubani_dev.commands.cluster import app as cluster_app
from kubani_dev.commands.config import app as config_app
from kubani_dev.commands.env import app as env_app
from kubani_dev.commands.registry import app as registry_app

# Add Typer sub-apps
app.add_typer(cluster_app, name="cluster")
app.add_typer(config_app, name="config")
app.add_typer(env_app, name="env")
app.add_typer(registry_app, name="registry")

# Cache for the Click command with all groups registered
_click_app = None


def get_click_app():
    """Get the Click command with all command groups registered.

    Caches the Click command to ensure Click groups are only added once
    and the same instance is used throughout.
    """
    global _click_app
    if _click_app is None:
        import typer.main

        _click_app = typer.main.get_command(app)
        _click_app.add_command(skill_group, name="skill")
        _click_app.add_command(agent_group, name="agent")

    return _click_app


def main_cli() -> None:
    """Main entry point."""
    click_app = get_click_app()
    click_app()


if __name__ == "__main__":
    main_cli()
