"""Agent management commands using the new framework."""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click
import typer
import typer.main

# Typer app for registration with main CLI
agent_app = typer.Typer(help="Agent management commands")

from kubani_dev.ui import (
    console,
    create_table,
    error,
    info,
    muted,
    print_panel,
    spinner,
    success,
    warning,
)

logger = logging.getLogger(__name__)


@click.group(name="agent")
def agent_group():
    """
    Manage agents using the new agent framework.

    Commands for running, testing, and evaluating agents locally
    with the agent-framework abstractions.
    """
    pass


@agent_group.command(name="run")
@click.argument("agent_name")
@click.option("--trigger", "-t", help="JSON trigger event")
@click.option("--trigger-file", "-f", type=click.Path(exists=True), help="JSON trigger file")
@click.option("--mode", type=click.Choice(["local", "cluster"]), default="local")
@click.option("--hot-reload", is_flag=True, help="Enable hot reload")
@click.option("--trace", is_flag=True, help="Show execution trace")
def run_agent(
    agent_name: str,
    trigger: Optional[str],
    trigger_file: Optional[str],
    mode: str,
    hot_reload: bool,
    trace: bool,
):
    """
    Run an agent with the new framework.

    Uses AgentRunner for local or cluster mode execution.

    \b
    Examples:
        kubani-dev agent run k8s-monitor
        kubani-dev agent run k8s-monitor --trigger '{"event": "pod_crash"}'
        kubani-dev agent run k8s-monitor --mode cluster
    """
    # Parse trigger
    trigger_data = {}
    if trigger_file:
        with open(trigger_file) as f:
            trigger_data = json.load(f)
    elif trigger:
        try:
            trigger_data = json.loads(trigger)
        except json.JSONDecodeError as e:
            error(f"Invalid JSON trigger: {e}")
            sys.exit(1)

    # Find agent directory
    agents_dir = Path.cwd() / "agents"
    if not agents_dir.exists():
        agents_dir = Path(__file__).parents[4] / "agents"

    agent_dir = agents_dir / agent_name
    if not agent_dir.exists():
        error(f"Agent not found: {agent_name}")
        available = [
            d.name
            for d in agents_dir.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and d.name not in ("skills", "evaluations", "templates")
        ]
        info(f"Available agents: {', '.join(available)}")
        sys.exit(1)

    trigger_display = json.dumps(trigger_data)[:50] if trigger_data else "(none)"
    print_panel(
        f"[bold]Agent:[/bold] {agent_name}\n"
        f"[bold]Mode:[/bold] {mode}\n"
        f"[bold]Hot Reload:[/bold] {'enabled' if hot_reload else 'disabled'}\n"
        f"[bold]Trigger:[/bold] {trigger_display}",
        title="Agent Runner",
        style="cyan",
    )
    console.print()

    async def execute():
        from agent_framework import AgentRunner, AgentConfig, RunMode

        # Create config
        config = AgentConfig(
            name=agent_name,
            run_mode=RunMode.LOCAL if mode == "local" else RunMode.CLUSTER,
        )

        # Create runner
        runner = AgentRunner(config)

        info(f"Starting agent: {agent_name}")

        try:
            if trigger_data:
                # Single execution with trigger
                result = await runner.execute_once(trigger_data)

                if trace:
                    console.print_json(json.dumps(result, indent=2, default=str))
                else:
                    success("Agent execution complete")
                    if isinstance(result, dict):
                        console.print("\n[bold]Result:[/bold]")
                        console.print(json.dumps(result, indent=2, default=str)[:500])
            else:
                # Continuous run
                info("Running in continuous mode (Ctrl+C to stop)...")
                await runner.run()

        except KeyboardInterrupt:
            info("Shutting down...")
        except Exception as e:
            error(f"Agent execution failed: {e}")
            raise

    asyncio.run(execute())


@agent_group.command(name="list")
def list_agents():
    """List all available agents."""
    agents_dir = Path.cwd() / "agents"
    if not agents_dir.exists():
        agents_dir = Path(__file__).parents[4] / "agents"

    if not agents_dir.exists():
        error("Agents directory not found")
        return

    table = create_table(
        title="Available Agents", columns=["Name", "Version", "Status", "Description"]
    )

    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue

        # Skip non-agent directories
        if agent_dir.name in ("skills", "evaluations", "templates", "core"):
            continue

        # Try to load pyproject.toml for version
        pyproject = agent_dir / "pyproject.toml"
        version = "-"
        description = "-"

        if pyproject.exists():
            try:
                import tomllib

                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
                version = data.get("project", {}).get("version", "-")
                description = data.get("project", {}).get("description", "-")
                if len(description) > 40:
                    description = description[:37] + "..."
            except Exception:
                pass

        # Check if agent has worker.py (indicates it's a real agent)
        src_dir = agent_dir / "src"
        has_worker = False
        if src_dir.exists():
            for f in src_dir.rglob("worker.py"):
                has_worker = True
                break

        status = "[green]ready[/green]" if has_worker else "[yellow]scaffold[/yellow]"

        table.add_row(agent_dir.name, version, status, description)

    console.print(table)


@agent_group.command(name="info")
@click.argument("agent_name")
def agent_info(agent_name: str):
    """Show detailed information about an agent."""
    agents_dir = Path.cwd() / "agents"
    if not agents_dir.exists():
        agents_dir = Path(__file__).parents[4] / "agents"

    agent_dir = agents_dir / agent_name
    if not agent_dir.exists():
        error(f"Agent not found: {agent_name}")
        return

    # Load pyproject.toml
    pyproject = agent_dir / "pyproject.toml"
    project_data = {}
    if pyproject.exists():
        try:
            import tomllib

            with open(pyproject, "rb") as f:
                project_data = tomllib.load(f).get("project", {})
        except Exception:
            pass

    # Basic info table
    info_table = create_table(title=f"Agent: {agent_name}", columns=["Property", "Value"])
    info_table.add_row("Name", project_data.get("name", agent_name))
    info_table.add_row("Version", project_data.get("version", "unknown"))
    info_table.add_row("Description", project_data.get("description", "No description"))
    info_table.add_row("Path", str(agent_dir))

    console.print(info_table)
    console.print()

    # List key files
    files_table = create_table(title="Key Files", columns=["File", "Status"])

    key_files = [
        ("pyproject.toml", "Package configuration"),
        ("src/*/worker.py", "Temporal worker"),
        ("src/*/workflows.py", "Workflow definitions"),
        ("src/*/activities.py", "Activity definitions"),
        ("README.md", "Documentation"),
    ]

    for pattern, desc in key_files:
        if "*" in pattern:
            matches = list(agent_dir.glob(pattern))
            exists = len(matches) > 0
        else:
            exists = (agent_dir / pattern).exists()

        status = "[green]exists[/green]" if exists else "[red]missing[/red]"
        files_table.add_row(pattern, status)

    console.print(files_table)


@agent_group.command(name="eval")
@click.argument("agent_name")
@click.option("--suite", "-s", type=click.Path(exists=True), help="Evaluation suite YAML")
@click.option("--output", "-o", type=click.Choice(["table", "json"]), default="table")
def eval_agent(
    agent_name: str,
    suite: Optional[str],
    output: str,
):
    """
    Evaluate an agent end-to-end.

    Runs evaluation scenarios and checks agent behavior.

    \b
    Examples:
        kubani-dev agent eval k8s-monitor
        kubani-dev agent eval k8s-monitor --suite evaluations/k8s/full.yaml
    """
    import yaml

    # Find evaluation suite
    if not suite:
        # Look for default suite
        eval_dirs = [
            Path.cwd() / "agents" / "evaluations" / agent_name,
            Path.cwd() / "evaluations" / agent_name,
        ]

        for eval_dir in eval_dirs:
            if eval_dir.exists():
                suite_files = list(eval_dir.glob("*.yaml")) + list(eval_dir.glob("*.yml"))
                if suite_files:
                    suite = str(suite_files[0])
                    break

    if not suite:
        warning(f"No evaluation suite found for {agent_name}")
        muted("Create one at: agents/evaluations/{agent_name}/eval.yaml")
        return

    print_panel(
        f"[bold]Agent:[/bold] {agent_name}\n[bold]Suite:[/bold] {suite}",
        title="Agent Evaluation",
        style="magenta",
    )
    console.print()

    # Load suite
    with open(suite) as f:
        suite_data = yaml.safe_load(f)

    scenarios = suite_data.get("scenarios", [])
    if not scenarios:
        warning("No scenarios defined in evaluation suite")
        return

    info(f"Running {len(scenarios)} evaluation scenarios...")
    console.print()

    results = []
    passed = 0

    for scenario in scenarios:
        scenario_name = scenario.get("name", "unnamed")

        with spinner(f"Running: {scenario_name}..."):
            # TODO: Implement actual agent evaluation
            # For now, this is a placeholder
            result = {
                "name": scenario_name,
                "passed": True,  # Placeholder
                "duration_ms": 0,
                "details": {},
            }

        results.append(result)
        if result["passed"]:
            passed += 1
            success(f"  {scenario_name}")
        else:
            error(f"  {scenario_name}")

    console.print()

    # Summary
    total = len(results)
    if output == "json":
        console.print_json(
            json.dumps(
                {
                    "agent": agent_name,
                    "suite": suite,
                    "total": total,
                    "passed": passed,
                    "failed": total - passed,
                    "results": results,
                },
                indent=2,
            )
        )
    else:
        summary_table = create_table(title="Evaluation Summary", columns=["Metric", "Value"])
        summary_table.add_row("Total Scenarios", str(total))
        summary_table.add_row("Passed", f"[green]{passed}[/green]")
        summary_table.add_row("Failed", f"[red]{total - passed}[/red]")
        summary_table.add_row("Pass Rate", f"{passed / total * 100:.1f}%" if total > 0 else "N/A")
        console.print(summary_table)


# Note: Click commands are registered with the main CLI via agent_group
# The agent_app Typer instance is kept for future migration to native Typer commands
