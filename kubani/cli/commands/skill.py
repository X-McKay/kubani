"""Skill management commands using the skill-auto workflow.

Commands:
  auto         - Autonomously create and improve skills via Temporal workflow
  auto-status  - Check status of a running auto workflow
  validate     - Validate a skill against Agent Skills standard
  validate-all - Validate all skills in a directory
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import click

from kubani.cli.ui import console, create_table, error, info, spinner, success, warning

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


# =============================================================================
# Skill Validation Commands
# =============================================================================


@skill_group.command(name="validate")
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--fix", is_flag=True, help="Attempt to fix validation errors (not implemented)")
@click.option("--strict", is_flag=True, help="Treat warnings as errors")
@click.option("--output", "-o", type=click.Choice(["text", "json"]), default="text")
def validate_skill(skill_path: str, fix: bool, strict: bool, output: str):
    """
    Validate a skill against Agent Skills standard.

    Checks:
    - YAML frontmatter format
    - Required fields (name, description, license, compatibility)
    - metadata.kubani fields (domain, category, version, confidence)
    - Test case coverage
    - Progressive disclosure readiness

    \b
    Examples:
        kubani skill validate kubani/skills/news/collection/fetch-rss-feeds
        kubani skill validate kubani/skills/news/collection/fetch-rss-feeds --strict
    """
    from kubani.workflows.skill_auto.utils import (
        assess_test_coverage,
        validate_skill_directory,
    )

    skill_dir = Path(skill_path)

    # Handle single file vs directory
    if skill_dir.is_file():
        skill_dir = skill_dir.parent

    is_valid, errors, warnings = validate_skill_directory(skill_dir)
    coverage = assess_test_coverage(skill_dir)

    if output == "json":
        result = {
            "path": str(skill_dir),
            "valid": is_valid and (not strict or len(warnings) == 0),
            "errors": errors,
            "warnings": warnings,
            "coverage": coverage,
        }
        console.print_json(json.dumps(result, indent=2))
        return

    # Text output
    skill_name = skill_dir.name
    console.print(f"\n[bold]Validating skill:[/bold] {skill_name}")
    console.print(f"[dim]Path: {skill_dir}[/dim]\n")

    if errors:
        error("Errors:")
        for err in errors:
            console.print(f"  [red]✗[/red] {err}")
        console.print()

    if warnings:
        warning("Warnings:")
        for warn in warnings:
            console.print(f"  [yellow]![/yellow] {warn}")
        console.print()

    # Coverage info
    console.print("[bold]Test Coverage:[/bold]")
    console.print(f"  Tests: {coverage['test_count']}")
    console.print(f"  Assertions: {coverage['assertions_count']}")
    console.print(f"  Coverage: {coverage['coverage_pct']*100:.0f}%")
    console.print(f"  Edge cases: {'✓' if coverage['has_edge_cases'] else '✗'}")
    console.print(f"  Error cases: {'✓' if coverage['has_error_cases'] else '✗'}")

    if coverage["warnings"]:
        for warn in coverage["warnings"]:
            console.print(f"  [yellow]![/yellow] {warn}")
    console.print()

    # Summary
    if is_valid and (not strict or len(warnings) == 0):
        success(f"Skill '{skill_name}' is valid!")
    elif is_valid:
        warning(f"Skill '{skill_name}' is valid but has warnings")
    else:
        error(f"Skill '{skill_name}' has validation errors")
        raise SystemExit(1)


@skill_group.command(name="validate-all")
@click.option("--path", "-p", type=click.Path(exists=True), help="Skills root directory")
@click.option("--domain", "-d", help="Filter by domain (e.g., news)")
@click.option("--category", "-c", help="Filter by category (e.g., collection)")
@click.option("--strict", is_flag=True, help="Treat warnings as errors")
@click.option("--output", "-o", type=click.Choice(["table", "json"]), default="table")
def validate_all_skills(
    path: Optional[str],
    domain: Optional[str],
    category: Optional[str],
    strict: bool,
    output: str,
):
    """
    Validate all skills in a directory.

    Discovers all SKILL.md files and validates each against Agent Skills standard.

    \b
    Examples:
        kubani skill validate-all
        kubani skill validate-all --domain news
        kubani skill validate-all --domain news --category collection
        kubani skill validate-all --output json
    """
    from kubani.workflows.skill_auto.utils import (
        assess_test_coverage,
        validate_skill_directory,
    )

    # Find skills root
    skills_root = Path(path) if path else _find_skills_root()
    if not skills_root or not skills_root.exists():
        error("Could not find skills directory")
        raise SystemExit(1)

    info(f"Scanning skills in: {skills_root}")

    # Find all SKILL.md files
    skill_dirs = []
    for skill_file in skills_root.rglob("SKILL.md"):
        skill_dir = skill_file.parent

        # Skip _development unless explicitly looking there
        if "_development" in str(skill_dir) and domain != "_development":
            continue

        # Filter by domain
        if domain:
            # Check if domain is in the path
            relative = skill_dir.relative_to(skills_root)
            parts = relative.parts
            if len(parts) < 1 or parts[0] != domain:
                continue

        # Filter by category
        if category:
            relative = skill_dir.relative_to(skills_root)
            parts = relative.parts
            if len(parts) < 2 or parts[1] != category:
                continue

        skill_dirs.append(skill_dir)

    if not skill_dirs:
        warning("No skills found matching criteria")
        return

    info(f"Found {len(skill_dirs)} skills to validate\n")

    # Validate each skill
    results = []
    for skill_dir in sorted(skill_dirs):
        is_valid, errors, warnings_list = validate_skill_directory(skill_dir)
        coverage = assess_test_coverage(skill_dir)

        # Determine relative path for display
        try:
            rel_path = skill_dir.relative_to(skills_root)
        except ValueError:
            rel_path = skill_dir

        results.append({
            "path": str(rel_path),
            "name": skill_dir.name,
            "valid": is_valid,
            "errors": errors,
            "warnings": warnings_list,
            "test_count": coverage["test_count"],
            "coverage_pct": coverage["coverage_pct"],
            "strict_valid": is_valid and (not strict or len(warnings_list) == 0),
        })

    if output == "json":
        console.print_json(json.dumps(results, indent=2))
        return

    # Table output
    table = create_table(
        title="Skill Validation Results",
        columns=["Skill", "Format", "Tests", "Coverage", "Status"],
    )

    valid_count = 0
    for r in results:
        format_status = "[green]✓[/green]" if r["valid"] else "[red]✗[/red]"
        test_status = "[green]✓[/green]" if r["test_count"] > 0 else "[red]✗[/red]"
        coverage_str = f"{r['coverage_pct']*100:.0f}%"

        if r["strict_valid"]:
            status = "[green]OK[/green]"
            valid_count += 1
        elif r["valid"]:
            status = "[yellow]WARN[/yellow]"
            if not strict:
                valid_count += 1
        else:
            status = "[red]FAIL[/red]"

        table.add_row(
            r["name"],
            format_status,
            f"{test_status} ({r['test_count']})",
            coverage_str,
            status,
        )

    console.print(table)
    console.print()

    # Summary
    total = len(results)
    failed = total - valid_count
    if failed == 0:
        success(f"All {total} skills passed validation!")
    else:
        warning(f"{valid_count}/{total} skills passed, {failed} failed")
        if not strict:
            info("Run with --strict to treat warnings as errors")


def _find_skills_root() -> Optional[Path]:
    """Find the skills root directory."""
    # Check common locations
    candidates = [
        Path.cwd() / "kubani" / "skills",
        Path.cwd() / "skills",
        Path(__file__).parents[3] / "skills",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate

    return None


# =============================================================================
# Skill Test Generation Commands
# =============================================================================


@skill_group.command(name="generate-tests")
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--seed-tests", "-s", type=click.Path(exists=True), help="Seed test cases file")
@click.option("--count", "-n", default=5, type=int, help="Number of test cases to generate")
@click.option("--output", "-o", type=click.Choice(["yaml", "file"]), default="file")
def generate_tests(skill_path: str, seed_tests: Optional[str], count: int, output: str):
    """
    Generate test cases for a skill using LLM.

    Uses the skill_auto workflow's draft_test_cases capability to generate
    comprehensive test cases covering happy path, edge cases, and error scenarios.

    \b
    Examples:
        kubani skill generate-tests kubani/skills/news/collection/fetch-rss-feeds
        kubani skill generate-tests kubani/skills/news/analysis/analyze-article --output yaml
        kubani skill generate-tests my-skill --seed-tests existing_tests.yaml
    """
    asyncio.run(_generate_tests_async(skill_path, seed_tests, count, output))


async def _generate_tests_async(
    skill_path: str,
    seed_tests: Optional[str],
    count: int,
    output: str,
):
    """Generate test cases using workflow capability."""
    from kubani.framework.llm import FrameworkLLM
    from kubani.workflows.skill_auto.capabilities.draft_test_cases import draft_test_cases
    from kubani.workflows.skill_auto.utils import parse_skill_frontmatter

    skill_dir = Path(skill_path)
    if skill_dir.is_file():
        skill_dir = skill_dir.parent

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        error(f"SKILL.md not found in {skill_dir}")
        raise SystemExit(1)

    info(f"Generating test cases for: {skill_dir.name}")

    # Parse skill to create spec
    content = skill_md.read_text()
    frontmatter = parse_skill_frontmatter(content)

    # Build spec from frontmatter
    spec = {
        "name": frontmatter.get("name", skill_dir.name),
        "description": frontmatter.get("description", ""),
        "inputs": frontmatter.get("inputs", {}),
        "outputs": frontmatter.get("outputs", {}),
        "examples": frontmatter.get("examples", []),
    }

    # Load seed tests if provided
    seed_content = None
    if seed_tests:
        seed_content = Path(seed_tests).read_text()
        info(f"Using seed tests from: {seed_tests}")

    # Generate test cases using workflow capability
    try:
        with spinner("Generating test cases with LLM..."):
            llm = FrameworkLLM()
            test_yaml = await draft_test_cases(llm, spec, seed_content)
        success("Test cases generated")
    except Exception as e:
        error(f"Failed to generate tests: {e}")
        raise SystemExit(1)

    if output == "yaml":
        console.print("\n[bold]Generated Test Cases:[/bold]\n")
        console.print(test_yaml)
    else:
        # Write to file
        test_file = skill_dir / "test_cases.yaml"
        test_file.write_text(test_yaml)
        success(f"Wrote test cases to: {test_file}")

        # Show summary
        import yaml
        try:
            tests = yaml.safe_load(test_yaml)
            test_count = len(tests.get("test_cases", []))
            info(f"Generated {test_count} test cases")
        except yaml.YAMLError:
            pass


@skill_group.command(name="evaluate")
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--mode", "-m", type=click.Choice(["quick", "full"]), default="quick",
              help="Evaluation mode (quick=single config, full=4-config matrix)")
@click.option("--no-critic", is_flag=True, help="Disable LLM critic evaluation")
@click.option("--output", "-o", type=click.Choice(["text", "json"]), default="text")
def evaluate_skill_cmd(skill_path: str, mode: str, no_critic: bool, output: str):
    """
    Evaluate a skill against its test cases.

    Uses the skill_auto workflow's evaluate_skill capability to run LLM-based
    evaluation with optional critic verification.

    \b
    Examples:
        kubani skill evaluate kubani/skills/news/collection/fetch-rss-feeds
        kubani skill evaluate kubani/skills/news/analysis/analyze-article --mode full
        kubani skill evaluate my-skill --no-critic --output json
    """
    asyncio.run(_evaluate_skill_async(skill_path, mode, not no_critic, output))


async def _evaluate_skill_async(
    skill_path: str,
    mode: str,
    enable_critic: bool,
    output: str,
):
    """Evaluate skill using workflow capability."""
    from kubani.workflows.skill_auto.capabilities.evaluate_skill import evaluate_skill

    skill_dir = Path(skill_path)
    if skill_dir.is_file():
        skill_dir = skill_dir.parent

    # Check test_cases.yaml exists
    test_file = skill_dir / "test_cases.yaml"
    if not test_file.exists():
        error(f"No test_cases.yaml found in {skill_dir}")
        info("Run 'kubani skill generate-tests' first to create test cases")
        raise SystemExit(1)

    info(f"Evaluating skill: {skill_dir.name}")
    info(f"Mode: {mode}, Critic: {'enabled' if enable_critic else 'disabled'}")

    try:
        with spinner(f"Running {mode} evaluation..."):
            metrics, feedback = await evaluate_skill(
                str(skill_dir),
                mode=mode,
                parallel=True,
                enable_critic=enable_critic,
            )
        success("Evaluation complete")
    except FileNotFoundError as e:
        error(f"File not found: {e}")
        raise SystemExit(1)
    except Exception as e:
        error(f"Evaluation failed: {e}")
        raise SystemExit(1)

    if output == "json":
        import json as json_module
        result = {
            "skill": skill_dir.name,
            "mode": mode,
            "metrics": {
                "accuracy": metrics.accuracy,
                "tests_passed": metrics.tests_passed,
                "tests_total": metrics.tests_total,
                "latency_ms": metrics.latency_ms,
                "critic_confidence": metrics.critic_confidence,
            },
        }
        console.print_json(json_module.dumps(result, indent=2))
        return

    # Text output
    console.print(f"\n[bold]Evaluation Results: {skill_dir.name}[/bold]\n")

    # Metrics table
    table = create_table(
        title="Metrics",
        columns=["Metric", "Value"],
    )
    table.add_row("Accuracy", f"{metrics.accuracy:.1%}")
    table.add_row("Tests Passed", f"{metrics.tests_passed}/{metrics.tests_total}")
    table.add_row("Avg Latency", f"{metrics.latency_ms:.0f}ms")
    if enable_critic:
        table.add_row("Critic Confidence", f"{metrics.critic_confidence:.1%}")
    console.print(table)
    console.print()

    # Show feedback
    if feedback:
        console.print("[bold]Detailed Feedback:[/bold]")
        console.print(feedback)

    # Summary
    if metrics.accuracy >= 0.8:
        success(f"Skill passed with {metrics.accuracy:.1%} accuracy!")
    elif metrics.accuracy >= 0.6:
        warning(f"Skill needs improvement: {metrics.accuracy:.1%} accuracy")
    else:
        error(f"Skill failing: {metrics.accuracy:.1%} accuracy")


@skill_group.command(name="list")
@click.option("--path", "-p", type=click.Path(exists=True), help="Skills root directory")
@click.option("--domain", "-d", help="Filter by domain")
@click.option("--output", "-o", type=click.Choice(["table", "json"]), default="table")
def list_skills(path: Optional[str], domain: Optional[str], output: str):
    """
    List all available skills.

    \b
    Examples:
        kubani skill list
        kubani skill list --domain news
        kubani skill list --output json
    """
    from kubani.workflows.skill_auto.utils import parse_skill_frontmatter

    skills_root = Path(path) if path else _find_skills_root()
    if not skills_root or not skills_root.exists():
        error("Could not find skills directory")
        raise SystemExit(1)

    skills = []
    for skill_file in skills_root.rglob("SKILL.md"):
        skill_dir = skill_file.parent

        # Skip _development
        if "_development" in str(skill_dir):
            continue

        # Filter by domain
        if domain:
            try:
                relative = skill_dir.relative_to(skills_root)
                parts = relative.parts
                if len(parts) < 1 or parts[0] != domain:
                    continue
            except ValueError:
                continue

        # Parse frontmatter
        content = skill_file.read_text()
        frontmatter = parse_skill_frontmatter(content)
        metadata = frontmatter.get("metadata", {}).get("kubani", {})

        try:
            rel_path = skill_dir.relative_to(skills_root)
        except ValueError:
            rel_path = skill_dir

        skills.append({
            "name": frontmatter.get("name", skill_dir.name),
            "path": str(rel_path),
            "domain": metadata.get("domain", "unknown"),
            "category": metadata.get("category", "unknown"),
            "version": metadata.get("version", "0.0.0"),
            "confidence": metadata.get("confidence", 0.0),
            "description": frontmatter.get("description", "")[:50],
        })

    if output == "json":
        console.print_json(json.dumps(skills, indent=2))
        return

    table = create_table(
        title=f"Skills ({len(skills)} total)",
        columns=["Name", "Domain", "Category", "Version", "Confidence"],
    )

    for s in sorted(skills, key=lambda x: (x["domain"], x["category"], x["name"])):
        conf_str = f"{s['confidence']*100:.0f}%"
        table.add_row(s["name"], s["domain"], s["category"], s["version"], conf_str)

    console.print(table)
