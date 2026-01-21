"""
Kubani Development CLI - Main Entry Point

Provides a unified interface for agent development, testing, and evaluation.
Designed to accelerate development iteration cycles by 17x+ compared to
deploying to a cluster for every change.

Features:
- Hot-reloading for rapid development
- Integrated test runner
- Multi-layered evaluation framework
- Real-time observability dashboard
- Agent scaffolding from templates
- Trace viewing and analysis
- Metrics collection and export
- Build and deploy commands
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import click

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


@click.group()
@click.version_option(version=__version__)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """
    Kubani Development CLI - Accelerate your agent development.

    A unified tool for running, testing, and evaluating Kubani agents locally.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["project_root"] = find_project_root()

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)


# -----------------------------------------------------------------------------
# Init Command
# -----------------------------------------------------------------------------


@cli.command()
@click.option("--force", "-f", is_flag=True, help="Overwrite existing configuration")
@click.pass_context
def init(ctx: click.Context, force: bool) -> None:
    """
    Initialize kubani-dev configuration.

    Creates:
    - .kubani-dev/ directory with config.yaml
    - Test dataset directories
    - Connection profiles

    Examples:
        kubani-dev init
        kubani-dev init --force
    """
    from kubani_dev.config import init_config

    project_root = ctx.obj["project_root"]

    config_file = init_config(project_root, force=force)

    click.echo(f"✓ Initialized kubani-dev at {config_file}")
    click.echo("")
    click.echo("Next steps:")
    click.echo("  1. Edit .kubani-dev/config.yaml to configure your environment")
    click.echo("  2. Run 'kubani-dev run <agent>' to start developing")
    click.echo("  3. Run 'kubani-dev eval <agent>' to evaluate your agent")


# -----------------------------------------------------------------------------
# Run Command
# -----------------------------------------------------------------------------


@cli.command()
@click.argument("agent", type=str)
@click.option("--hot-reload", "-r", is_flag=True, default=True, help="Enable hot-reloading")
@click.option("--port", "-p", type=int, default=8080, help="Port for agent server")
@click.option("--mock-mcp", is_flag=True, help="Use mock MCP servers")
@click.option("--mock-redis", is_flag=True, help="Use mock Redis")
@click.pass_context
def run(
    ctx: click.Context,
    agent: str,
    hot_reload: bool,
    port: int,
    mock_mcp: bool,
    mock_redis: bool,
) -> None:
    """
    Run an agent locally for development.

    AGENT is the name of the agent to run (e.g., 'k8s-monitor', 'news-monitor').

    Examples:
        kubani-dev run k8s-monitor
        kubani-dev run k8s-monitor --mock-mcp --mock-redis
    """
    from kubani_dev.runner import AgentRunner

    project_root = ctx.obj["project_root"]
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


@cli.command()
@click.argument("agent", type=str, required=False)
@click.option("--coverage", "-c", is_flag=True, help="Generate coverage report")
@click.option("--watch", "-w", is_flag=True, help="Watch mode - rerun on changes")
@click.option("--filter", "-k", type=str, help="Filter tests by name pattern")
@click.pass_context
def test(
    ctx: click.Context,
    agent: Optional[str],
    coverage: bool,
    watch: bool,
    filter: Optional[str],
) -> None:
    """
    Run tests for an agent or all agents.

    AGENT is optional - if not provided, runs tests for all agents.

    Examples:
        kubani-dev test                    # Run all tests
        kubani-dev test k8s-monitor        # Run k8s-monitor tests
        kubani-dev test -k "test_sentinel" # Filter by test name
    """
    from kubani_dev.testing import TestRunner

    project_root = ctx.obj["project_root"]

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
# Eval Command
# -----------------------------------------------------------------------------


@cli.command()
@click.argument("agent", type=str)
@click.option("--suite", "-s", type=str, default="all", help="Evaluation suite to run")
@click.option("--output", "-o", type=Path, help="Output directory for results")
@click.option("--parallel", "-j", type=int, default=1, help="Parallel evaluation jobs")
@click.pass_context
def eval(
    ctx: click.Context,
    agent: str,
    suite: str,
    output: Optional[Path],
    parallel: int,
) -> None:
    """
    Run evaluation suite for an agent.

    Supports multiple evaluation strategies:
    - Automated checks (syntax, type checking, linting)
    - LLM-as-Judge evaluation
    - Simulation-based testing
    - Human review integration

    Examples:
        kubani-dev eval k8s-monitor
        kubani-dev eval k8s-monitor --suite llm-judge
        kubani-dev eval k8s-monitor --output ./eval-results
    """
    from kubani_dev.evaluation import EvaluationRunner

    project_root = ctx.obj["project_root"]
    output_dir = output or project_root / "eval-results" / agent

    logger.info(f"Running {suite} evaluation for {agent}")

    runner = EvaluationRunner(
        agent_name=agent,
        project_root=project_root,
        suite=suite,
        output_dir=output_dir,
        parallel_jobs=parallel,
    )

    asyncio.run(runner.run())


# -----------------------------------------------------------------------------
# Dashboard Command
# -----------------------------------------------------------------------------


@cli.command()
@click.option("--port", "-p", type=int, default=3000, help="Dashboard port")
@click.option("--host", "-h", type=str, default="localhost", help="Dashboard host")
@click.pass_context
def dashboard(ctx: click.Context, port: int, host: str) -> None:
    """
    Start the observability dashboard.

    Provides real-time visibility into:
    - Agent execution traces
    - Performance metrics
    - Evaluation results
    - Memory system state

    Examples:
        kubani-dev dashboard
        kubani-dev dashboard --port 8080
    """
    from kubani_dev.dashboard import start_dashboard

    project_root = ctx.obj["project_root"]
    logger.info(f"Starting dashboard at http://{host}:{port}")

    start_dashboard(
        project_root=project_root,
        host=host,
        port=port,
    )


# -----------------------------------------------------------------------------
# New Agent Command
# -----------------------------------------------------------------------------


@cli.command()
@click.argument("name", type=str)
@click.option("--template", "-t", type=str, default="basic", help="Agent template to use")
@click.option("--directory", "-d", type=Path, help="Target directory")
@click.pass_context
def new(
    ctx: click.Context,
    name: str,
    template: str,
    directory: Optional[Path],
) -> None:
    """
    Create a new agent from a template.

    Available templates:
    - basic: Simple agent with minimal configuration
    - federated: Agent with Sentinel/Healer/Explorer pattern
    - workflow: Hybrid workflow-agent pattern

    Examples:
        kubani-dev new my-agent
        kubani-dev new my-agent --template federated
    """
    from kubani_dev.scaffold import create_agent

    project_root = ctx.obj["project_root"]
    target_dir = directory or project_root / "agents" / name

    logger.info(f"Creating new agent '{name}' from template '{template}'")

    create_agent(
        name=name,
        template=template,
        target_dir=target_dir,
        project_root=project_root,
    )

    logger.info(f"Agent created at {target_dir}")
    click.echo("")
    click.echo("Next steps:")
    click.echo(f"  1. cd {target_dir}")
    click.echo(f"  2. Edit src/{name.replace('-', '_')}/agent.py")
    click.echo(f"  3. kubani-dev run {name}")


# -----------------------------------------------------------------------------
# Skills Command (Consolidated LLM-powered skill management)
# -----------------------------------------------------------------------------

# NOTE: The standalone 'skills' command has been deprecated and consolidated
# into 'kubani-dev skill' which provides LLM-powered skill development:
#   - kubani-dev skill list --search "OOM"  (replaces: kubani-dev skills --search)
#   - kubani-dev skill validate --all       (replaces: kubani-dev skills --validate)
#   - kubani-dev skill draft/eval/improve   (new LLM-powered workflow)


# -----------------------------------------------------------------------------
# Sync Command
# -----------------------------------------------------------------------------


@cli.command()
@click.option("--skills/--no-skills", default=True, help="Sync skills")
@click.option("--agents/--no-agents", default=True, help="Sync agents")
@click.option("--mcp/--no-mcp", default=True, help="Sync MCP servers and policies")
@click.option("--dry-run", is_flag=True, help="Show what would be synced without syncing")
@click.option(
    "--registry-url",
    type=str,
    envvar="REGISTRY_URL",
    default="http://localhost:8000",
    help="Registry service URL",
)
@click.pass_context
def sync(
    ctx: click.Context,
    skills: bool,
    agents: bool,
    mcp: bool,
    dry_run: bool,
    registry_url: str,
) -> None:
    """
    Sync Git resources to the registry.

    Synchronizes:
    - Skills (skills/**/*.md)
    - Agents (agents/*/pyproject.toml)
    - MCP Servers (mcp/servers/*.json)
    - MCP Policies (mcp/policies/*.json)

    Examples:
        kubani-dev sync                  # Sync everything
        kubani-dev sync --dry-run        # Preview what would be synced
        kubani-dev sync --skills         # Only sync skills
        kubani-dev sync --no-mcp         # Skip MCP sync
    """
    from kubani_dev.sync import RegistrySync, print_sync_results

    project_root = ctx.obj["project_root"]

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

    # Exit with error if any failures
    total_failed = sum(r.failed for r in results.values())
    if total_failed > 0:
        sys.exit(1)


# -----------------------------------------------------------------------------
# Trace Command
# -----------------------------------------------------------------------------


@cli.command()
@click.argument("trace_id", type=str, required=False)
@click.option("--agent", "-a", type=str, help="Filter by agent name")
@click.option("--limit", "-n", type=int, default=10, help="Number of traces to show")
@click.option("--status", "-s", type=str, help="Filter by status (success, failed, running)")
@click.pass_context
def trace(
    ctx: click.Context,
    trace_id: Optional[str],
    agent: Optional[str],
    limit: int,
    status: Optional[str],
) -> None:
    """
    View and analyze execution traces.

    Examples:
        kubani-dev trace                      # List recent traces
        kubani-dev trace abc123               # Show specific trace
        kubani-dev trace --agent k8s-monitor  # Filter by agent
        kubani-dev trace --status failed      # Show failed traces
    """
    from kubani_dev.trace import TraceStore, TraceViewer

    project_root = ctx.obj["project_root"]
    store = TraceStore(project_root)
    viewer = TraceViewer(store)

    if trace_id:
        # Show specific trace
        output = asyncio.run(viewer.show_trace(trace_id))
        click.echo(output)
    else:
        # List traces
        output = asyncio.run(viewer.list_traces(agent=agent, limit=limit))
        click.echo(output)


# -----------------------------------------------------------------------------
# Metrics Command
# -----------------------------------------------------------------------------


@cli.command()
@click.argument("agent", type=str, required=False)
@click.option("--format", "-f", type=click.Choice(["text", "json", "prometheus"]), default="text")
@click.option("--export", "-e", type=Path, help="Export metrics to file")
@click.pass_context
def metrics(
    ctx: click.Context,
    agent: Optional[str],
    format: str,
    export: Optional[Path],
) -> None:
    """
    View and export agent metrics.

    Examples:
        kubani-dev metrics                    # Show all metrics
        kubani-dev metrics k8s-monitor        # Show agent metrics
        kubani-dev metrics --format json      # JSON output
        kubani-dev metrics --export metrics.json
    """
    from kubani_dev.metrics import MetricsCollector, MetricsViewer

    project_root = ctx.obj["project_root"]
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
        click.echo(f"Exported metrics to {export}")
    else:
        click.echo(output)


# -----------------------------------------------------------------------------
# Monitor Command
# -----------------------------------------------------------------------------


@cli.command()
@click.argument("agent", type=str)
@click.option("--env", "-e", type=click.Choice(["dev", "staging", "production"]), default="dev")
@click.option("--follow", "-f", is_flag=True, help="Follow logs in real-time")
@click.pass_context
def monitor(
    ctx: click.Context,
    agent: str,
    env: str,
    follow: bool,
) -> None:
    """
    Monitor agent deployment in a cluster.

    Examples:
        kubani-dev monitor k8s-monitor              # Check status
        kubani-dev monitor k8s-monitor --follow     # Follow logs
        kubani-dev monitor k8s-monitor --env prod   # Production environment
    """
    from kubani_dev.deploy import ProductionMonitor

    project_root = ctx.obj["project_root"]
    monitor = ProductionMonitor(agent, project_root, env)

    if follow:
        click.echo(f"Following logs for {agent} in {env}...")
        try:
            asyncio.run(monitor.watch())
        except KeyboardInterrupt:
            click.echo("\nStopped following logs")
    else:
        pods = monitor.get_pods()
        if not pods:
            click.echo(f"No pods found for {agent} in {env}")
            return

        click.echo(f"Pods for {agent} in {env}:")
        for pod in pods:
            name = pod.get("metadata", {}).get("name", "unknown")
            status = pod.get("status", {}).get("phase", "Unknown")
            click.echo(f"  {name}: {status}")


# -----------------------------------------------------------------------------
# Build Command
# -----------------------------------------------------------------------------


@cli.command()
@click.argument("agent", type=str)
@click.option("--tag", "-t", type=str, default="latest", help="Image tag")
@click.option("--push", "-p", is_flag=True, help="Push to registry after build")
@click.option("--registry", "-r", type=str, help="Container registry")
@click.pass_context
def build(
    ctx: click.Context,
    agent: str,
    tag: str,
    push: bool,
    registry: Optional[str],
) -> None:
    """
    Build agent container image.

    Examples:
        kubani-dev build k8s-monitor
        kubani-dev build k8s-monitor --tag v1.0.0
        kubani-dev build k8s-monitor --push
    """
    from kubani_dev.deploy import AgentBuilder, BuildConfig

    project_root = ctx.obj["project_root"]

    config = BuildConfig(
        agent_name=agent,
        project_root=project_root,
        registry=registry or "",
        tag=tag,
        push=push,
    )

    builder = AgentBuilder(config)

    if builder.build():
        click.echo(f"✓ Built {agent}:{tag}")
    else:
        click.echo(f"✗ Build failed for {agent}")
        sys.exit(1)


# -----------------------------------------------------------------------------
# Local Run Command
# -----------------------------------------------------------------------------


@cli.command("local-run")
@click.argument("agent", type=str)
@click.option(
    "--temporal",
    type=click.Choice(["local", "cluster"]),
    default="local",
    help="Use local Temporalite or cluster Temporal",
)
@click.option(
    "--output",
    type=click.Choice(["console", "discord", "both"]),
    default="console",
    help="Where to route agent output",
)
@click.option(
    "--tunnel/--no-tunnel",
    default=False,
    help="Enable tunnel to cluster services",
)
@click.option(
    "--tunnel-method",
    type=click.Choice(["telepresence", "kubectl-forward"]),
    default="kubectl-forward",
    help="Method for cluster connectivity",
)
@click.pass_context
def local_run(
    ctx: click.Context,
    agent: str,
    temporal: str,
    output: str,
    tunnel: bool,
    tunnel_method: str,
) -> None:
    """
    Run an agent locally with cluster service connectivity.

    This command sets up the local development environment:
    - Optionally tunnels to cluster services (Qdrant, Redis, Neo4j, etc.)
    - Starts local Temporal or connects to cluster Temporal
    - Routes output to console and/or Discord

    Examples:
        kubani-dev local-run k8s-monitor
        kubani-dev local-run k8s-monitor --tunnel --temporal=cluster --output=both
        kubani-dev local-run news-monitor --output=console
    """
    from kubani_dev.local_run import local_run as do_local_run

    # Invoke the local_run command directly
    do_local_run.callback(agent, temporal, output, tunnel, tunnel_method, False)


# -----------------------------------------------------------------------------
# Deploy Command
# -----------------------------------------------------------------------------


@cli.command()
@click.argument("target", type=str)
@click.option(
    "--version",
    "-v",
    type=str,
    default=None,
    help="Version/tag to deploy (default: latest)",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force deployment even if no changes detected",
)
@click.option(
    "--skip-verification",
    is_flag=True,
    help="Skip health verification after deployment",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be deployed without actually deploying",
)
@click.pass_context
def deploy(
    ctx: click.Context,
    target: str,
    version: Optional[str],
    force: bool,
    skip_verification: bool,
    dry_run: bool,
) -> None:
    """
    Deploy an agent or service to the cluster.

    TARGET is what to deploy: k8s-monitor, news-monitor, registry, ui, or all.

    This command provides transparent, end-to-end deployment:
    - Triggers GitHub Actions build workflow
    - Monitors build progress
    - Requests deployment from cluster controller
    - Streams deployment status
    - Verifies health after deployment
    - Automatically rolls back on failure

    Examples:
        kubani-dev deploy k8s-monitor
        kubani-dev deploy all --version v1.2.3
        kubani-dev deploy news-monitor --dry-run
        kubani-dev deploy k8s-monitor --skip-verification
    """
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
# Skill Management Command Group (LLM-powered)
# -----------------------------------------------------------------------------

from kubani_dev.commands.skill import skill_group

cli.add_command(skill_group)


def main() -> None:
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
