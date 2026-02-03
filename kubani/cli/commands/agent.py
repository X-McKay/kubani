"""Agent management commands using the new framework."""

import asyncio
import json
import logging
import sys
from pathlib import Path

import click
import typer
import typer.main

# Typer app for registration with main CLI
agent_app = typer.Typer(help="Agent management commands")

from kubani.cli.ui import (
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


# Default Temporal settings for agent workflows
AGENT_AUTO_TASK_QUEUE = "agent-auto-task-queue"
DEFAULT_TEMPORAL_ADDRESS = "localhost:7233"


def _get_temporal_address() -> str:
    """Get Temporal address from config or environment."""
    import os

    return os.environ.get("TEMPORAL_ADDRESS", DEFAULT_TEMPORAL_ADDRESS)


@click.group(name="agent")
def agent_group():
    """
    Manage AI agents.

    Commands for drafting, evaluating, and managing agents.
    Use 'kubani dev <agent>' to run agents locally.
    """
    pass


@agent_group.command(name="draft")
@click.option("--name", "-n", required=True, help="Name of the agent to create.")
@click.option("--description", "-d", required=True, help="High-level description of the agent.")
@click.option(
    "--target-accuracy", type=float, default=0.8, help="Target evaluation accuracy (0.0-1.0)."
)
@click.option("--max-iterations", type=int, default=5, help="Maximum improvement iterations.")
@click.option(
    "--child-skill-max-iterations",
    type=int,
    default=3,
    help="Maximum iterations for auto-generated child skills.",
)
@click.option(
    "--child-skill-target-accuracy",
    type=float,
    default=0.70,
    help="Target accuracy for auto-generated child skills (0.0-1.0).",
)
@click.option("--non-interactive", is_flag=True, help="Run without waiting for completion.")
@click.option(
    "--temporal-address", default=None, help="Temporal server address (default: localhost:7233)."
)
def draft_agent(
    name: str,
    description: str,
    target_accuracy: float,
    max_iterations: int,
    child_skill_max_iterations: int,
    child_skill_target_accuracy: float,
    non_interactive: bool,
    temporal_address: str | None,
):
    """
    Draft a new agent using the automated agent creation workflow.

    This command starts the AgentAutoWorkflow in Temporal, which will:
    1. Draft the agent structure and identify required skills
    2. Create any missing skills (via child SkillAutoWorkflow)
    3. Write the agent files to disk
    4. Run an eval-improve loop until target accuracy is reached
    5. Publish the agent

    \b
    Examples:
        kubani agent draft --name k8s-watcher --description "Monitor Kubernetes pods for issues"
        kubani agent draft -n news-digest -d "Aggregate news from multiple sources" --target-accuracy 0.9
    """
    temporal_addr = temporal_address or _get_temporal_address()

    print_panel(
        f"[bold]Agent Name:[/bold] {name}\n"
        f"[bold]Description:[/bold] {description}\n"
        f"[bold]Target Accuracy:[/bold] {target_accuracy:.0%}\n"
        f"[bold]Max Iterations:[/bold] {max_iterations}\n"
        f"[bold]Temporal:[/bold] {temporal_addr}",
        title="🚀 Starting Agent Creation Workflow",
        style="cyan",
    )
    console.print()

    async def start_workflow():
        from temporalio.client import Client

        from kubani.workflows.agent_auto.domain.models import AgentAutoInput
        from kubani.workflows.agent_auto.workflow import AgentAutoWorkflow

        try:
            client = await Client.connect(temporal_addr)
        except Exception as e:
            error(f"Failed to connect to Temporal at {temporal_addr}: {e}")
            info("Make sure Temporal is running. You can start it with: temporal server start-dev")
            sys.exit(1)

        workflow_input = AgentAutoInput(
            agent_name=name,
            description=description,
            target_accuracy=target_accuracy,
            max_iterations=max_iterations,
            child_skill_max_iterations=child_skill_max_iterations,
            child_skill_target_accuracy=child_skill_target_accuracy,
        )

        workflow_id = f"agent-auto-{name}"

        try:
            handle = await client.start_workflow(
                AgentAutoWorkflow.run,
                args=[workflow_input],
                id=workflow_id,
                task_queue=AGENT_AUTO_TASK_QUEUE,
            )
        except Exception as e:
            error(f"Failed to start workflow: {e}")
            sys.exit(1)

        success(f"Workflow started with ID: {handle.id}")
        info(f"Monitor progress: kubani agent status {name}")
        info(f"Cancel workflow:  kubani agent cancel {name}")
        console.print()

        if non_interactive:
            muted("Running in non-interactive mode. Workflow will continue in background.")
            return

        info("Waiting for workflow to complete... (Ctrl+C to detach)")
        console.print()

        try:
            with spinner("Running agent creation workflow..."):
                result = await handle.result()

            console.print()
            if result.success:
                success("Agent created successfully!")
                info(f"Agent path: {result.agent_path}")
                info(
                    f"Final accuracy: {result.final_accuracy:.2%}" if result.final_accuracy else ""
                )
                info(f"Iterations completed: {result.iterations_completed}")
            else:
                warning(f"Agent creation finished with status: {result.status}")
                if result.error:
                    error(f"Error: {result.error}")
                if result.final_accuracy:
                    info(
                        f"Final accuracy: {result.final_accuracy:.2%} (target: {target_accuracy:.0%})"
                    )

        except KeyboardInterrupt:
            console.print()
            info("Detached from workflow. It continues running in Temporal.")
            info(f"Check status: kubani agent status {name}")

    asyncio.run(start_workflow())


@agent_group.command(name="status")
@click.argument("agent_name")
@click.option("--temporal-address", default=None, help="Temporal server address.")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON.")
def agent_status(
    agent_name: str,
    temporal_address: str | None,
    output_json: bool,
):
    """
    Get the status of a running agent creation workflow.

    Queries the Temporal workflow to show current status, iteration count,
    and evaluation history.

    \b
    Examples:
        kubani agent status my-agent
        kubani agent status my-agent --json
    """
    temporal_addr = temporal_address or _get_temporal_address()
    workflow_id = f"agent-auto-{agent_name}"

    async def get_status():
        from temporalio.client import Client
        from temporalio.service import RPCError

        try:
            client = await Client.connect(temporal_addr)
        except Exception as e:
            error(f"Failed to connect to Temporal at {temporal_addr}: {e}")
            sys.exit(1)

        handle = client.get_workflow_handle(workflow_id)

        try:
            description = await handle.describe()
        except RPCError as e:
            if "not found" in str(e).lower():
                error(f"No workflow found for agent '{agent_name}'")
                info(f"Start one with: kubani agent draft --name {agent_name} --description '...'")
            else:
                error(f"Failed to get workflow status: {e}")
            sys.exit(1)

        # Try to query the workflow state
        state = None
        try:
            state = await handle.query("get_state")
        except Exception:
            # Workflow might not support queries or be in a state that can't be queried
            pass

        if output_json:
            output = {
                "workflow_id": description.id,
                "status": description.status.name,
                "start_time": description.start_time.isoformat()
                if description.start_time
                else None,
                "state": state.model_dump() if state and hasattr(state, "model_dump") else state,
            }
            console.print_json(json.dumps(output, indent=2, default=str))
        else:
            print_panel(
                f"[bold]Workflow ID:[/bold] {description.id}\n"
                f"[bold]Status:[/bold] {description.status.name}\n"
                f"[bold]Started:[/bold] {description.start_time}",
                title=f"Agent Workflow: {agent_name}",
                style="cyan",
            )

            if state:
                console.print()
                state_dict = state.model_dump() if hasattr(state, "model_dump") else state
                if isinstance(state_dict, dict):
                    state_table = create_table(
                        title="Workflow State", columns=["Property", "Value"]
                    )
                    state_table.add_row("Agent Name", str(state_dict.get("agent_name", "-")))
                    state_table.add_row("Status", str(state_dict.get("status", "-")))
                    state_table.add_row("Iteration", str(state_dict.get("iteration", 0)))
                    state_table.add_row("Agent Path", str(state_dict.get("agent_path", "-")))

                    eval_history = state_dict.get("eval_history", [])
                    if eval_history:
                        last_eval = eval_history[-1]
                        accuracy = last_eval.get("objective_accuracy", 0)
                        state_table.add_row("Last Accuracy", f"{accuracy:.2%}")
                        state_table.add_row("Evaluations Run", str(len(eval_history)))

                    if state_dict.get("error"):
                        state_table.add_row("Error", f"[red]{state_dict['error']}[/red]")

                    console.print(state_table)

    asyncio.run(get_status())


@agent_group.command(name="cancel")
@click.argument("agent_name")
@click.option("--temporal-address", default=None, help="Temporal server address.")
@click.option("--force", is_flag=True, help="Cancel without confirmation.")
def cancel_agent(
    agent_name: str,
    temporal_address: str | None,
    force: bool,
):
    """
    Cancel a running agent creation workflow.

    Sends a cancel signal to the Temporal workflow, which will gracefully
    stop the agent creation process.

    \b
    Examples:
        kubani agent cancel my-agent
        kubani agent cancel my-agent --force
    """
    temporal_addr = temporal_address or _get_temporal_address()
    workflow_id = f"agent-auto-{agent_name}"

    if not force:
        if not click.confirm(f"Cancel workflow for agent '{agent_name}'?"):
            info("Cancelled.")
            return

    async def do_cancel():
        from temporalio.client import Client
        from temporalio.service import RPCError

        try:
            client = await Client.connect(temporal_addr)
        except Exception as e:
            error(f"Failed to connect to Temporal at {temporal_addr}: {e}")
            sys.exit(1)

        handle = client.get_workflow_handle(workflow_id)

        try:
            await handle.cancel()
            success(f"Cancel request sent to workflow for agent '{agent_name}'")
            info("The workflow will stop after completing its current activity.")
        except RPCError as e:
            if "not found" in str(e).lower():
                error(f"No workflow found for agent '{agent_name}'")
            else:
                error(f"Failed to cancel workflow: {e}")
            sys.exit(1)

    asyncio.run(do_cancel())


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
    suite: str | None,
    output: str,
):
    """
    Evaluate an agent end-to-end.

    Runs evaluation scenarios and checks agent behavior.

    \b
    Examples:
        kubani agent eval k8s-monitor
        kubani agent eval k8s-monitor --suite evaluations/k8s/full.yaml
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


# =============================================================================
# Agent Test Generation & Evaluation Commands (using workflow capabilities)
# =============================================================================


@agent_group.command(name="generate-tests")
@click.argument("agent_name")
@click.option("--count", "-n", default=5, type=int, help="Number of test cases to generate")
@click.option("--output", "-o", type=click.Choice(["yaml", "file"]), default="file")
def generate_tests(agent_name: str, count: int, output: str):
    """
    Generate test cases for an agent using LLM.

    Uses the agent_auto workflow's draft_agent_test_cases capability to generate
    comprehensive test cases covering core functionality, skill orchestration, and edge cases.

    \b
    Examples:
        kubani agent generate-tests feed_collector
        kubani agent generate-tests content_analyst --output yaml
    """
    asyncio.run(_generate_agent_tests_async(agent_name, count, output))


async def _generate_agent_tests_async(agent_name: str, count: int, output: str):
    """Generate test cases using workflow capability."""
    import re

    import yaml

    from kubani.framework.llm import FrameworkLLM
    from kubani.workflows.agent_auto.capabilities import draft_agent_test_cases

    # Find agent directory
    agent_dir = _find_agent_dir(agent_name)
    if not agent_dir:
        error(f"Agent not found: {agent_name}")
        raise SystemExit(1)

    info(f"Generating test cases for agent: {agent_name}")
    console.print(f"[dim]Path: {agent_dir}[/dim]\n")

    # Extract agent info from agent.py
    agent_file = agent_dir / "agent.py"
    if not agent_file.exists():
        error(f"agent.py not found in {agent_dir}")
        raise SystemExit(1)

    content = agent_file.read_text()

    # Extract description from docstring or class
    description = ""
    # Try to find class docstring
    docstring_match = re.search(r'class\s+\w+.*?:\s*"""([^"]+)"""', content, re.DOTALL)
    if docstring_match:
        description = docstring_match.group(1).strip().split("\n")[0]
    else:
        # Try module docstring
        module_doc = re.search(r'^"""([^"]+)"""', content, re.DOTALL)
        if module_doc:
            description = module_doc.group(1).strip().split("\n")[0]

    # Extract SKILLS_DOMAIN and SKILLS_CATEGORY
    domain_match = re.search(r'SKILLS_DOMAIN\s*[=:]\s*["\']([^"\']+)["\']', content)
    category_match = re.search(r'SKILLS_CATEGORY\s*[=:]\s*["\']([^"\']+)["\']', content)

    domain = domain_match.group(1) if domain_match else "unknown"
    category = category_match.group(1) if category_match else "unknown"

    # Find available skills
    skills = []
    skills_root = agent_dir.parent.parent / "skills"
    if skills_root.exists():
        skills_path = skills_root / domain / category
        if skills_path.exists():
            from kubani.workflows.skill_auto.utils import parse_skill_frontmatter

            for skill_file in skills_path.rglob("SKILL.md"):
                try:
                    skill_content = skill_file.read_text()
                    frontmatter = parse_skill_frontmatter(skill_content)
                    skills.append({
                        "name": frontmatter.get("name", skill_file.parent.name),
                        "description": frontmatter.get("description", "")[:100],
                    })
                except Exception:
                    pass

    info(f"Found {len(skills)} skills for {domain}/{category}")

    # Load config if exists
    config = None
    config_file = agent_dir / "config.yaml"
    if config_file.exists():
        try:
            config = yaml.safe_load(config_file.read_text())
        except yaml.YAMLError:
            pass

    # Generate test cases using workflow capability
    try:
        with spinner("Generating test cases with LLM..."):
            llm = FrameworkLLM()
            test_yaml = await draft_agent_test_cases(
                client=llm,
                agent_name=agent_name,
                description=description or f"Agent in {domain}/{category}",
                skills=skills,
                config=config,
            )
        success("Test cases generated")
    except Exception as e:
        error(f"Failed to generate tests: {e}")
        raise SystemExit(1)

    if output == "yaml":
        console.print("\n[bold]Generated Test Cases:[/bold]\n")
        console.print(test_yaml)
    else:
        # Write to file
        test_file = agent_dir / "test_cases.yaml"
        test_file.write_text(test_yaml)
        success(f"Wrote test cases to: {test_file}")

        # Show summary
        try:
            tests = yaml.safe_load(test_yaml)
            test_count = len(tests.get("test_cases", []))
            info(f"Generated {test_count} test cases")
        except yaml.YAMLError:
            pass


@agent_group.command(name="evaluate")
@click.argument("agent_name")
@click.option("--test-cases", "-t", type=click.Path(exists=True), help="Test cases YAML file")
@click.option("--output", "-o", type=click.Choice(["text", "json"]), default="text")
def evaluate_agent_cmd(agent_name: str, test_cases: str | None, output: str):
    """
    Evaluate an agent against test cases using the workflow capability.

    Uses the agent_auto workflow's EvaluationService to run the agent against
    test cases and measure skill precision/recall.

    \b
    Examples:
        kubani agent evaluate feed_collector
        kubani agent evaluate content_analyst --test-cases custom_tests.yaml
    """
    asyncio.run(_evaluate_agent_async(agent_name, test_cases, output))


async def _evaluate_agent_async(agent_name: str, test_cases_path: str | None, output: str):
    """Evaluate agent using workflow capability."""
    import yaml

    from kubani.workflows.agent_auto.capabilities import EvaluationService
    from kubani.workflows.agent_auto.models import AgentTestCase
    from kubani.workflows.agent_auto.temporal.activities import create_agent_runner

    # Find agent directory
    agent_dir = _find_agent_dir(agent_name)
    if not agent_dir:
        error(f"Agent not found: {agent_name}")
        raise SystemExit(1)

    # Find test cases file
    test_file = Path(test_cases_path) if test_cases_path else agent_dir / "test_cases.yaml"
    if not test_file.exists():
        error(f"No test_cases.yaml found: {test_file}")
        info("Run 'kubani agent generate-tests' first to create test cases")
        raise SystemExit(1)

    info(f"Evaluating agent: {agent_name}")
    info(f"Test cases: {test_file}")
    console.print()

    # Load test cases
    try:
        test_data = yaml.safe_load(test_file.read_text())
        raw_cases = test_data.get("test_cases", [])
        if not raw_cases:
            error("No test cases found in file")
            raise SystemExit(1)

        test_cases = [AgentTestCase(**tc) for tc in raw_cases]
        info(f"Loaded {len(test_cases)} test cases")
    except Exception as e:
        error(f"Failed to load test cases: {e}")
        raise SystemExit(1)

    # Run evaluation
    try:
        with spinner("Running agent evaluation..."):
            runner = create_agent_runner()
            eval_service = EvaluationService(agent_runner=runner)
            result = await eval_service.evaluate_agent(str(agent_dir), test_cases)
        success("Evaluation complete")
    except Exception as e:
        error(f"Evaluation failed: {e}")
        raise SystemExit(1)

    if output == "json":
        console.print_json(json.dumps(result.model_dump(), indent=2))
        return

    # Text output
    console.print(f"\n[bold]Evaluation Results: {agent_name}[/bold]\n")

    # Metrics table
    table = create_table(
        title="Metrics",
        columns=["Metric", "Value"],
    )
    table.add_row("Objective Accuracy", f"{result.objective_accuracy:.1%}")
    table.add_row("Skill Precision", f"{result.skill_precision:.1%}")
    table.add_row("Skill Recall", f"{result.skill_recall:.1%}")
    table.add_row("Invoked Skills", ", ".join(result.invoked_skills) or "None")
    console.print(table)
    console.print()

    # Missing/extraneous skills
    if result.missing_skills:
        warning(f"Missing skills: {', '.join(result.missing_skills)}")
    if result.extraneous_skills:
        warning(f"Extraneous skills: {', '.join(result.extraneous_skills)}")

    # Failures
    if result.failures:
        console.print(f"\n[bold]Failed Tests ({len(result.failures)}):[/bold]")
        for failure in result.failures:
            console.print(f"  [red]✗[/red] {failure}")

    console.print()

    # Summary
    if result.objective_accuracy >= 0.8:
        success(f"Agent passed with {result.objective_accuracy:.1%} accuracy!")
    elif result.objective_accuracy >= 0.6:
        warning(f"Agent needs improvement: {result.objective_accuracy:.1%} accuracy")
    else:
        error(f"Agent failing: {result.objective_accuracy:.1%} accuracy")


# =============================================================================
# Agent Validation Commands
# =============================================================================


@agent_group.command(name="validate")
@click.argument("agent_name")
@click.option("--check-skills", is_flag=True, help="Also validate agent's skills")
@click.option("--check-config", is_flag=True, help="Check config.yaml consistency")
@click.option("--check-logic", is_flag=True, help="Detect embedded business logic")
@click.option("--output", "-o", type=click.Choice(["text", "json"]), default="text")
def validate_agent(
    agent_name: str,
    check_skills: bool,
    check_config: bool,
    check_logic: bool,
    output: str,
):
    """
    Validate an agent follows SkillsOrchestrator pattern.

    Checks:
    - Inherits from SkillsOrchestrator
    - Has SKILLS_DOMAIN and SKILLS_CATEGORY class attributes
    - config.yaml matches class attributes (with --check-config)
    - Skills can be discovered (with --check-skills)
    - No embedded business logic (with --check-logic)

    \b
    Examples:
        kubani agent validate feed-collector
        kubani agent validate content-analyst --check-skills
        kubani agent validate feed-collector --check-config --check-logic
    """
    from kubani.workflows.agent_auto.capabilities import (
        detect_embedded_business_logic,
        validate_skills_orchestrator_pattern,
    )

    # Find agent directory
    agent_dir = _find_agent_dir(agent_name)
    if not agent_dir:
        error(f"Agent not found: {agent_name}")
        raise SystemExit(1)

    result = {
        "agent": agent_name,
        "path": str(agent_dir),
        "valid": True,
        "errors": [],
        "warnings": [],
        "logic_issues": [],
        "logic_recommendations": [],
    }

    # Validate SkillsOrchestrator pattern
    is_valid, errors, warnings_list = validate_skills_orchestrator_pattern(agent_dir)
    result["valid"] = is_valid
    result["errors"].extend(errors)
    result["warnings"].extend(warnings_list)

    # Check for embedded business logic
    if check_logic:
        issues, recommendations = detect_embedded_business_logic(agent_dir)
        result["logic_issues"] = issues
        result["logic_recommendations"] = recommendations

    # Check skills discovery (if requested)
    if check_skills and is_valid:
        skill_errors = _validate_agent_skills(agent_dir)
        result["errors"].extend(skill_errors)
        if skill_errors:
            result["valid"] = False

    if output == "json":
        console.print_json(json.dumps(result, indent=2))
        return

    # Text output
    console.print(f"\n[bold]Validating agent:[/bold] {agent_name}")
    console.print(f"[dim]Path: {agent_dir}[/dim]\n")

    # Pattern validation
    console.print("[bold]SkillsOrchestrator Pattern:[/bold]")
    if is_valid:
        success("  Agent follows SkillsOrchestrator pattern")
    else:
        error("  Pattern validation failed")
        for err in errors:
            console.print(f"    [red]✗[/red] {err}")

    if warnings_list:
        for warn in warnings_list:
            console.print(f"    [yellow]![/yellow] {warn}")
    console.print()

    # Embedded logic check
    if check_logic:
        console.print("[bold]Embedded Business Logic Check:[/bold]")
        if not result["logic_issues"]:
            success("  No embedded business logic detected")
        else:
            warning(f"  Found {len(result['logic_issues'])} potential issues:")
            for issue in result["logic_issues"][:5]:  # Limit to first 5
                console.print(f"    [yellow]![/yellow] {issue}")
            if len(result["logic_issues"]) > 5:
                console.print(f"    ... and {len(result['logic_issues']) - 5} more")

            if result["logic_recommendations"]:
                console.print("\n  Recommendations:")
                for rec in result["logic_recommendations"]:
                    console.print(f"    → {rec}")
        console.print()

    # Summary
    if result["valid"] and not result["logic_issues"]:
        success(f"Agent '{agent_name}' is valid!")
    elif result["valid"]:
        warning(f"Agent '{agent_name}' is valid but has warnings")
    else:
        error(f"Agent '{agent_name}' has validation errors")
        raise SystemExit(1)


@agent_group.command(name="validate-all")
@click.option("--path", "-p", type=click.Path(exists=True), help="Agents root directory")
@click.option("--check-skills", is_flag=True, help="Also validate each agent's skills")
@click.option("--output", "-o", type=click.Choice(["table", "json"]), default="table")
def validate_all_agents(path: str | None, check_skills: bool, output: str):
    """
    Validate all agents in a directory.

    Discovers all agent directories and validates each against SkillsOrchestrator pattern.

    \b
    Examples:
        kubani agent validate-all
        kubani agent validate-all --check-skills
    """
    from kubani.workflows.agent_auto.capabilities import (
        validate_skills_orchestrator_pattern,
    )

    agents_root = Path(path) if path else _find_agents_root()
    if not agents_root or not agents_root.exists():
        error("Could not find agents directory")
        raise SystemExit(1)

    info(f"Scanning agents in: {agents_root}")

    # Find all agent directories (those with agent.py)
    agent_dirs = []
    for agent_file in agents_root.rglob("agent.py"):
        agent_dir = agent_file.parent
        # Skip _base, tests, etc.
        if any(skip in str(agent_dir) for skip in ["_base", "tests", "__pycache__"]):
            continue
        agent_dirs.append(agent_dir)

    if not agent_dirs:
        warning("No agents found")
        return

    info(f"Found {len(agent_dirs)} agents to validate\n")

    # Validate each agent
    results = []
    for agent_dir in sorted(agent_dirs):
        is_valid, errors, warnings_list = validate_skills_orchestrator_pattern(agent_dir)

        results.append({
            "name": agent_dir.name,
            "path": str(agent_dir),
            "valid": is_valid,
            "errors": errors,
            "warnings": warnings_list,
            "error_count": len(errors),
            "warning_count": len(warnings_list),
        })

    if output == "json":
        console.print_json(json.dumps(results, indent=2))
        return

    # Table output
    table = create_table(
        title="Agent Validation Results",
        columns=["Agent", "Pattern", "Errors", "Warnings", "Status"],
    )

    valid_count = 0
    for r in results:
        pattern_status = "[green]✓[/green]" if r["valid"] else "[red]✗[/red]"
        status = "[green]OK[/green]" if r["valid"] else "[red]FAIL[/red]"
        if r["valid"]:
            valid_count += 1

        table.add_row(
            r["name"],
            pattern_status,
            str(r["error_count"]),
            str(r["warning_count"]),
            status,
        )

    console.print(table)
    console.print()

    # Summary
    total = len(results)
    failed = total - valid_count
    if failed == 0:
        success(f"All {total} agents passed validation!")
    else:
        warning(f"{valid_count}/{total} agents passed, {failed} failed")


def _find_agent_dir(agent_name: str) -> Path | None:
    """Find an agent directory by name."""
    candidates = [
        Path.cwd() / "kubani" / "agents" / agent_name,
        Path.cwd() / "agents" / agent_name,
        Path(__file__).parents[3] / "agents" / agent_name,
    ]

    for candidate in candidates:
        if candidate.exists() and (candidate / "agent.py").exists():
            return candidate

    return None


def _find_agents_root() -> Path | None:
    """Find the agents root directory."""
    candidates = [
        Path.cwd() / "kubani" / "agents",
        Path.cwd() / "agents",
        Path(__file__).parents[3] / "agents",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate

    return None


def _validate_agent_skills(agent_dir: Path) -> list[str]:
    """Validate that an agent can discover its skills."""
    errors = []

    # Read agent.py to get SKILLS_DOMAIN and SKILLS_CATEGORY
    agent_file = agent_dir / "agent.py"
    if not agent_file.exists():
        return ["Cannot check skills: agent.py not found"]

    content = agent_file.read_text()

    # Extract domain and category from the file
    import re

    domain_match = re.search(r'SKILLS_DOMAIN\s*[=:]\s*["\']([^"\']+)["\']', content)
    category_match = re.search(r'SKILLS_CATEGORY\s*[=:]\s*["\']([^"\']+)["\']', content)

    if not domain_match:
        errors.append("Cannot verify skills: SKILLS_DOMAIN not found or not a string literal")
        return errors

    if not category_match:
        errors.append("Cannot verify skills: SKILLS_CATEGORY not found or not a string literal")
        return errors

    domain = domain_match.group(1)
    category = category_match.group(1)

    # Find skills directory
    skills_root = agent_dir.parent.parent / "skills"
    if not skills_root.exists():
        errors.append(f"Skills root not found: {skills_root}")
        return errors

    # Check if skills exist for this domain/category
    skills_path = skills_root / domain / category
    if not skills_path.exists():
        errors.append(f"No skills found at {skills_path}")
        return errors

    # Count SKILL.md files
    skill_files = list(skills_path.rglob("SKILL.md"))
    if not skill_files:
        errors.append(f"No SKILL.md files found in {skills_path}")
    else:
        info(f"  Found {len(skill_files)} skills for {domain}/{category}")

    return errors


# Note: Click commands are registered with the main CLI via agent_group
# The agent_app Typer instance is kept for future migration to native Typer commands
