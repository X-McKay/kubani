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
"""

import asyncio
import logging
import os
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
    logger.info(f"Next steps:")
    logger.info(f"  1. cd {target_dir}")
    logger.info(f"  2. Edit src/{name.replace('-', '_')}/agent.py")
    logger.info(f"  3. kubani-dev run {name}")


@cli.command()
@click.argument("skill", type=str, required=False)
@click.option("--validate", "-v", is_flag=True, help="Validate skill format")
@click.option("--search", "-s", type=str, help="Search skills by keyword")
@click.pass_context
def skills(
    ctx: click.Context,
    skill: Optional[str],
    validate: bool,
    search: Optional[str],
) -> None:
    """
    Manage and validate skills.

    Examples:
        kubani-dev skills                     # List all skills
        kubani-dev skills --search "OOM"      # Search skills
        kubani-dev skills --validate          # Validate all skills
        kubani-dev skills k8s/pod-restart     # Show skill details
    """
    from kubani_dev.skills import SkillManager

    project_root = ctx.obj["project_root"]
    manager = SkillManager(project_root / "skills")

    if validate:
        results = manager.validate_all()
        for path, errors in results.items():
            if errors:
                click.echo(f"❌ {path}")
                for error in errors:
                    click.echo(f"   - {error}")
            else:
                click.echo(f"✓ {path}")
    elif search:
        matches = manager.search(search)
        for match in matches:
            click.echo(f"  {match['name']}: {match['description'][:60]}...")
    elif skill:
        info = manager.get_skill(skill)
        if info:
            click.echo(f"Name: {info['name']}")
            click.echo(f"Description: {info['description']}")
            click.echo(f"Category: {info['metadata'].get('category', 'N/A')}")
        else:
            click.echo(f"Skill not found: {skill}")
    else:
        all_skills = manager.list_all()
        for category, skills_list in all_skills.items():
            click.echo(f"\n{category}:")
            for s in skills_list:
                click.echo(f"  - {s}")


def main() -> None:
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
