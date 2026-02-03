"""
Kubani Development CLI - Typer-based entry point.

Provides a unified interface for agent development and testing.
Migrated from Click to Typer for better type hints and auto-completion.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Annotated

import typer

from kubani.cli import __version__

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("kubani")


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
    name="kubani",
    help="Kubani Development CLI - Accelerate your agent development.",
    no_args_is_help=True,
)


def version_callback(value: bool):
    if value:
        typer.echo(f"kubani {__version__}")
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
    """Initialize kubani configuration."""
    from kubani.cli.config import init_config

    project_root = find_project_root()
    config_file = init_config(project_root, force=force)

    typer.echo(f"✓ Initialized kubani at {config_file}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("  1. Edit .kubani/config.yaml to configure your environment")
    typer.echo("  2. Run 'kubani run <agent>' to start developing")
    typer.echo("  3. Run 'kubani skill auto -d \"...\"' to create skills")


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
    from kubani.cli.runner import AgentRunner

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
    agent: Annotated[str | None, typer.Argument(help="Agent name (optional)")] = None,
    coverage: Annotated[
        bool, typer.Option("--coverage", "-c", help="Generate coverage report")
    ] = False,
    watch: Annotated[
        bool, typer.Option("--watch", "-w", help="Watch mode - rerun on changes")
    ] = False,
    filter: Annotated[
        str | None, typer.Option("--filter", "-k", help="Filter tests by name pattern")
    ] = None,
):
    """Run tests for an agent or all agents."""
    from kubani.cli.testing import TestRunner

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
    from kubani.cli.dashboard import start_dashboard

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
        Path | None, typer.Option("--directory", "-d", help="Target directory")
    ] = None,
):
    """Create a new agent from a template."""
    from kubani.cli.scaffold import create_agent

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
    typer.echo(f"  3. kubani run {name}")


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
    """[DEPRECATED] Sync Git resources to the registry. Use migrate/export instead."""
    from kubani.cli.sync import RegistrySync, print_sync_results

    # Show deprecation warning
    typer.echo(
        typer.style(
            "\nWarning: The 'sync' command is deprecated.\n\n"
            "Use the new registry-first commands instead:\n"
            "  kubani migrate to-registry  # One-time migration\n"
            "  kubani export to-git        # Export to Git\n\n",
            fg=typer.colors.YELLOW,
        )
    )

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
    trace_id: Annotated[str | None, typer.Argument(help="Trace ID to view")] = None,
    agent: Annotated[str | None, typer.Option("--agent", "-a", help="Filter by agent name")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of traces to show")] = 10,
    status: Annotated[str | None, typer.Option("--status", "-s", help="Filter by status")] = None,
):
    """View and analyze execution traces."""
    from kubani.cli.trace import TraceStore, TraceViewer

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
    agent: Annotated[str | None, typer.Argument(help="Agent name (optional)")] = None,
    format: Annotated[str, typer.Option("--format", "-f", help="Output format")] = "text",
    export: Annotated[
        Path | None, typer.Option("--export", "-e", help="Export metrics to file")
    ] = None,
):
    """View and export agent metrics."""
    from kubani.cli.metrics import MetricsCollector, MetricsViewer

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
    from kubani.cli.deploy import ProductionMonitor

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
        str | None, typer.Option("--registry", "-r", help="Container registry")
    ] = None,
):
    """Build agent container image."""
    from kubani.cli.deploy import AgentBuilder, BuildConfig

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
    from kubani.cli.local_run import local_run as do_local_run

    do_local_run.callback(agent, temporal, output, tunnel, tunnel_method, False)


# -----------------------------------------------------------------------------
# Dev Command
# -----------------------------------------------------------------------------


@app.command("dev")
def dev(
    target: Annotated[str, typer.Argument(help="Agent or syndicate name")],
    workflow: Annotated[
        bool, typer.Option("--workflow", help="Run full Temporal workflow")
    ] = False,
    publish: Annotated[
        bool, typer.Option("--publish", help="Actually publish to Discord (default is dry run)")
    ] = False,
    mcp: Annotated[
        str | None, typer.Option("--mcp", help="Comma-separated MCP servers to run")
    ] = None,
    no_mcp: Annotated[bool, typer.Option("--no-mcp", help="Skip MCP server startup")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output results as JSON")] = False,
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


# -----------------------------------------------------------------------------
# Deploy Command
# -----------------------------------------------------------------------------


@app.command()
def deploy(
    target: Annotated[
        str, typer.Argument(help="Target to deploy (k8s-monitor, news-monitor, all)")
    ],
    version: Annotated[
        str | None,
        typer.Option("--version", "-v", help="Version tag (auto-generated if not provided)"),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Force deployment even on errors")
    ] = False,
    skip_verification: Annotated[
        bool, typer.Option("--skip-verification", help="Skip health verification after deploy")
    ] = False,
    skip_build: Annotated[
        bool, typer.Option("--skip-build", help="Skip build, use existing images")
    ] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be deployed")] = False,
):
    """
    Deploy an agent to the cluster.

    Builds locally with Earthly, pushes to the local registry, updates GitOps
    manifests, and triggers a Kubernetes rollout.

    Examples:
        kubani deploy k8s-monitor
        kubani deploy news-monitor --version 1.2.3
        kubani deploy all --dry-run
        kubani deploy k8s-monitor --skip-build
    """
    from kubani.cli.deploy import deploy_command

    exit_code = asyncio.run(
        deploy_command(
            target=target,
            version=version,
            force=force,
            skip_verification=skip_verification,
            dry_run=dry_run,
            skip_build=skip_build,
        )
    )
    sys.exit(exit_code)


# -----------------------------------------------------------------------------
# Skill and Agent Command Groups
# -----------------------------------------------------------------------------

# Import Click command groups
from kubani.cli.commands.agent import agent_group

# Import Typer command groups
from kubani.cli.commands.cluster import app as cluster_app
from kubani.cli.commands.config import app as config_app
from kubani.cli.commands.env import app as env_app
from kubani.cli.commands.export import app as export_app
from kubani.cli.commands.migrate import app as migrate_app
from kubani.cli.commands.registry import app as registry_app
from kubani.cli.commands.skill import skill_group
from kubani.cli.commands.sync import app as sync_deprecated_app

# Add Typer sub-apps
app.add_typer(cluster_app, name="cluster")
app.add_typer(config_app, name="config")
app.add_typer(env_app, name="env")
app.add_typer(export_app, name="export")
app.add_typer(migrate_app, name="migrate")
app.add_typer(registry_app, name="registry")
app.add_typer(sync_deprecated_app, name="sync-legacy")

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
