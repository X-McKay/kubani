"""Skill management commands using the skill-auto workflow.

Commands:
  auto        - Autonomously create and improve skills via Temporal workflow
  auto-status - Check status of a running auto workflow
"""

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING, Optional

import click

from kubani.cli.ui import console, error, info, spinner, success, warning

if TYPE_CHECKING:
    from kubani.workflows.skill_auto.models import SkillAutoInput

logger = logging.getLogger(__name__)


@click.group(name="skill")
def skill_group():
    """
    Manage skills using the autonomous skill development workflow.

    The skill-auto workflow creates, evaluates, and improves skills automatically
    using Temporal workflows. It iterates until quality goals are met.

    Commands:
      auto        - Create or improve skills autonomously
      auto-status - Check status of a running workflow
    """
    pass


@skill_group.command(name="auto")
@click.option("--description", "-d", required=True, help="Description of the skill to create")
@click.option(
    "--improve",
    "-i",
    "skill_path",
    help="Path to existing skill to improve (instead of creating new)",
)
@click.option("--seed-tests", help="Path to seed test cases file")
@click.option("--max-iterations", default=5, type=int, help="Maximum improvement iterations")
@click.option("--target-accuracy", default=80, type=int, help="Target accuracy percentage")
@click.option("--review-each-iteration", is_flag=True, help="Pause for review after each iteration")
@click.option("--no-promote", is_flag=True, help="Skip promotion step")
@click.option("--no-notify", is_flag=True, help="Disable Discord notifications")
@click.option("--allow-overlap", is_flag=True, help="Allow creation even if overlap detected")
@click.option("--background", is_flag=True, help="Run as background Temporal workflow")
@click.option(
    "--temporal",
    default="cluster",
    type=click.Choice(["cluster", "local"]),
    help="Temporal instance to use",
)
def auto_skill(
    description: str,
    skill_path: Optional[str],
    seed_tests: Optional[str],
    max_iterations: int,
    target_accuracy: int,
    review_each_iteration: bool,
    no_promote: bool,
    no_notify: bool,
    allow_overlap: bool,
    background: bool,
    temporal: str,
):
    """
    Autonomously create and improve a skill.

    Creates a skill from description, evaluates it, improves based on feedback,
    and repeats until quality goals are met or iteration limit reached.

    \b
    Examples:
        # Create new skill
        kubani skill auto -d "A skill that diagnoses OOMKilled pods"

        # Improve existing skill
        kubani skill auto -d "Improve accuracy" --improve kubani/skills/_development/oom-diagnostics

        # Run in background
        kubani skill auto -d "A skill that ..." --background
    """
    from kubani.workflows.skill_auto.models import SkillAutoInput

    workflow_input = SkillAutoInput(
        description=description,
        mode="improve" if skill_path else "create",
        skill_path=skill_path,
        seed_tests_path=seed_tests,
        max_iterations=max_iterations,
        target_accuracy=target_accuracy / 100.0,
        review_each_iteration=review_each_iteration,
        skip_promotion=no_promote,
        notify=not no_notify,
        allow_overlap=allow_overlap,
    )

    if background:
        asyncio.run(_run_auto_background(workflow_input, temporal))
    else:
        asyncio.run(_run_auto_foreground(workflow_input, temporal))


async def _run_auto_foreground(workflow_input: "SkillAutoInput", temporal: str):
    """Run auto workflow in foreground with streaming progress."""
    from temporalio.client import Client

    from kubani.workflows.skill_auto import SkillAutoWorkflow

    # Connect to Temporal
    host = (
        "localhost:7233"
        if temporal == "local"
        else os.environ.get("TEMPORAL_HOST", "temporal.almckay.io:7233")
    )
    client = await Client.connect(host)

    # Start workflow
    workflow_id = f"skill-auto-{workflow_input.skill_path or 'new'}-{int(time.time())}"
    handle = await client.start_workflow(
        SkillAutoWorkflow.run,
        workflow_input,
        id=workflow_id,
        task_queue="skill-development",
    )

    info(f"Started workflow: {workflow_id}")

    # Poll for progress
    last_iteration = 0

    with spinner("Running auto skill development...") as sp:
        while True:
            try:
                state = await handle.query(SkillAutoWorkflow.get_state)

                if state and state.iteration > last_iteration:
                    sp.text = (
                        f"Iteration {state.iteration}: {state.status} "
                        f"(best: {state.best_score:.2f})"
                    )
                    last_iteration = state.iteration

                if state and state.status in ("completed", "failed"):
                    break

                await asyncio.sleep(2)
            except Exception:
                await asyncio.sleep(5)

    # Get result
    result = await handle.result()

    if result.success:
        success(f"Completed in {result.iterations_completed} iterations")
        if result.final_metrics:
            success(f"Final accuracy: {result.final_metrics.accuracy * 100:.0f}%")
        success(f"Skill path: {result.skill_path}")
    else:
        error(f"Failed: {result.stop_reason}")
        if result.error:
            error(result.error)


async def _run_auto_background(workflow_input: "SkillAutoInput", temporal: str):
    """Start auto workflow in background."""
    from temporalio.client import Client

    from kubani.workflows.skill_auto import SkillAutoWorkflow

    host = (
        "localhost:7233"
        if temporal == "local"
        else os.environ.get("TEMPORAL_HOST", "temporal.almckay.io:7233")
    )
    client = await Client.connect(host)

    workflow_id = f"skill-auto-{workflow_input.skill_path or 'new'}-{int(time.time())}"
    await client.start_workflow(
        SkillAutoWorkflow.run,
        workflow_input,
        id=workflow_id,
        task_queue="skill-development",
    )

    success(f"Started background workflow: {workflow_id}")
    info(f"Monitor with: kubani skill auto-status {workflow_id}")


@skill_group.command(name="auto-status")
@click.argument("workflow_id")
@click.option(
    "--temporal",
    default="cluster",
    type=click.Choice(["cluster", "local"]),
)
def auto_status(workflow_id: str, temporal: str):
    """Check status of a running auto workflow."""
    asyncio.run(_check_auto_status(workflow_id, temporal))


async def _check_auto_status(workflow_id: str, temporal: str):
    """Query workflow status."""
    from temporalio.client import Client

    from kubani.workflows.skill_auto import SkillAutoWorkflow

    host = (
        "localhost:7233"
        if temporal == "local"
        else os.environ.get("TEMPORAL_HOST", "temporal.almckay.io:7233")
    )
    client = await Client.connect(host)

    handle = client.get_workflow_handle(workflow_id)

    try:
        state = await handle.query(SkillAutoWorkflow.get_state)

        if not state:
            error("No state available for workflow")
            return

        console.print(f"[bold]Workflow:[/bold] {workflow_id}")
        console.print(f"[bold]Status:[/bold] {state.status}")
        console.print(f"[bold]Skill:[/bold] {state.skill_name}")
        console.print(f"[bold]Iteration:[/bold] {state.iteration}")
        console.print(f"[bold]Best score:[/bold] {state.best_score:.2f}")

        if state.overlap_warning:
            warning(f"Overlap warning: {state.overlap_warning.overlapping_skills}")

        if state.error:
            error(f"Error: {state.error}")

    except Exception as e:
        error(f"Failed to query workflow: {e}")
