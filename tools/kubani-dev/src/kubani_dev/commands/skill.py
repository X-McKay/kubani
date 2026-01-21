"""LLM-powered skill management commands.

Provides a complete skill lifecycle management system:
- draft: Create new skills using LLM conversation
- eval: Evaluate skills using LLM execution + critic verification
- improve: Automatically improve skills based on evaluation feedback
- promote: Move skills from development to production
- list: List and search skills
- info: Show detailed skill information
- validate: Validate skill format and structure
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import click
import yaml

from kubani_dev.llm_client import LLMClient
from kubani_dev.skill_drafter import SkillDrafter
from kubani_dev.skill_evaluator_llm import SkillEvaluatorLLM
from kubani_dev.skill_improver import SkillImprover
from kubani_dev.ui import (
    console,
    create_table,
    error,
    info,
    muted,
    print_panel,
    print_results_summary,
    spinner,
    success,
    warning,
)

logger = logging.getLogger(__name__)


def get_llm_client(
    base_url: Optional[str] = None, model: Optional[str] = None, timeout: int = 300
) -> LLMClient:
    """Get LLM client with configuration.

    Args:
        base_url: LLM API base URL
        model: Model name
        timeout: Request timeout in seconds (default: 300 for skill operations)
    """
    # Default to Kubani LLM endpoint (OpenAI-compatible)
    base_url = base_url or os.getenv("LLM_BASE_URL", "https://llm.almckay.io")
    model = model or os.getenv("LLM_MODEL", "nvidia/Qwen3-14B-FP4")

    return LLMClient(base_url=base_url, model=model, timeout=timeout)


@click.group(name="skill")
def skill_group():
    """
    Manage skills in the Kubani development workflow.

    This command group provides LLM-powered tools for creating, evaluating,
    improving, and promoting skills through their lifecycle.

    Commands:
      draft     - Create new skills using LLM conversation
      eval      - Evaluate skills using LLM execution + critic
      improve   - Automatically improve skills based on evaluation
      promote   - Move skills from development to production
      list      - List all skills with optional search
      info      - Show detailed skill information
      validate  - Validate skill format and structure
    """
    pass


# Backward compatibility alias
skill_llm = skill_group


@skill_group.command(name="draft")
@click.argument("name", required=False)
@click.argument("description", required=False)
@click.option("--name", "-n", "name_opt", help="Skill name (kebab-case)")
@click.option("--description", "-d", "desc_opt", help="Skill description")
@click.option("--llm-url", help="LLM base URL")
@click.option("--llm-model", help="LLM model name")
@click.option(
    "--output-dir",
    type=click.Path(),
    help="Output directory (default: skills/development/<skill-name>)",
)
@click.option("--non-interactive", is_flag=True, help="Skip conversation, generate directly")
def draft_skill(
    name: Optional[str],
    description: Optional[str],
    name_opt: Optional[str],
    desc_opt: Optional[str],
    llm_url: Optional[str],
    llm_model: Optional[str],
    output_dir: Optional[str],
    non_interactive: bool,
):
    """
    Draft a new skill using LLM-powered conversation.

    \b
    Examples:
        kubani-dev skill draft my-skill "Calculate the factorial of a number"
        kubani-dev skill draft --name my-skill --description "Calculate factorial"
        kubani-dev skill draft my-skill  # prompts for description
        kubani-dev skill draft            # prompts for both
    """
    # Merge positional args with options (options take precedence)
    skill_name = name_opt or name
    skill_description = desc_opt or description

    # Prompt for missing values in interactive mode
    if not non_interactive:
        if not skill_name:
            skill_name = click.prompt("Skill name (kebab-case)", type=str)
        if not skill_description:
            skill_description = click.prompt("Skill description", type=str)
    else:
        # Non-interactive mode requires both
        if not skill_name or not skill_description:
            error("Both name and description required in non-interactive mode")
            sys.exit(1)

    # Normalize name to kebab-case
    skill_name = skill_name.lower().replace(" ", "-").replace("_", "-")

    llm = get_llm_client(llm_url, llm_model)
    drafter = SkillDrafter(llm)

    # Display configuration panel
    print_panel(
        f"[bold]Model:[/bold] {llm.model}\n[bold]Endpoint:[/bold] {llm.base_url}",
        title="Kubani Skill Draft",
        style="cyan",
    )
    console.print()
    info(f"Creating skill: [bold]{skill_name}[/bold]")
    console.print(f"   {skill_description}\n")

    if non_interactive:
        # Generate directly without conversation
        # Create a simple spec from description
        spec = {
            "name": skill_name,
            "description": skill_description,
            "inputs": {},
            "outputs": {},
            "steps": ["Execute the task as described"],
            "error_handling": ["Handle errors gracefully"],
        }

        # Generate files
        if not output_dir:
            output_dir = f"skills/development/{spec['name']}"

        output_path = Path(output_dir)

        try:
            with spinner("Generating skill files..."):
                files = drafter.generate_skill_files(spec, output_path)
        except RuntimeError as e:
            console.print()
            error(f"Generation failed: {e}")
            console.print()
            warning("The LLM may be slow or overloaded. Try again or use a different model.")
            muted("Tip: Set LLM_MODEL environment variable or use --llm-model to try another model")
            sys.exit(1)
        except Exception as e:
            console.print()
            error(f"Unexpected error: {e}")
            sys.exit(1)

        success(f"Skill created: [bold]{skill_name}[/bold]")
        console.print()

        # Display created files in a table
        table = create_table(columns=["File", "Status"])
        for filename in files:
            table.add_row(filename, "[green]Created[/green]")
        console.print(table)

        return

    # Interactive conversation
    with spinner("Starting LLM conversation..."):
        response = drafter.start_conversation(skill_description)
    console.print(f"[bold cyan]Assistant:[/bold cyan] {response}\n")

    # Conversation loop
    while True:
        user_input = click.prompt("You", type=str)

        if user_input.lower() in ["quit", "exit", "cancel"]:
            warning("Cancelled")
            return

        with spinner("Processing..."):
            result = drafter.continue_conversation(user_input)

        console.print(f"\n[bold cyan]Assistant:[/bold cyan] {result['message']}\n")

        if result["is_ready"]:
            spec = result["spec"]

            # Override with provided skill name
            spec["name"] = skill_name

            # Show spec in a panel
            print_panel(
                json.dumps(spec, indent=2),
                title="Skill Specification",
                style="green",
            )
            console.print()

            # Confirm
            if click.confirm("Generate skill files with this spec?", default=True):
                # Determine output directory
                if not output_dir:
                    output_dir = f"skills/development/{skill_name}"

                output_path = Path(output_dir)

                try:
                    with spinner("Generating skill files..."):
                        files = drafter.generate_skill_files(spec, output_path)
                except RuntimeError as e:
                    console.print()
                    error(f"Generation failed: {e}")
                    console.print()
                    warning(
                        "The LLM may be slow or overloaded. Try again or use a different model."
                    )
                    muted(
                        "Tip: Set LLM_MODEL environment variable or use --llm-model to try another model"
                    )
                    sys.exit(1)
                except Exception as e:
                    console.print()
                    error(f"Unexpected error: {e}")
                    sys.exit(1)

                success(f"Skill created: [bold]{skill_name}[/bold]")
                console.print()

                # Display created files in a table
                table = create_table(columns=["File", "Status"])
                for filename in files:
                    table.add_row(filename, "[green]Created[/green]")
                console.print(table)

                # Ask if they want to evaluate
                if click.confirm("\nRun evaluation now?", default=True):
                    ctx = click.get_current_context()
                    ctx.invoke(
                        evaluate_skill,
                        skill_path=str(output_path),
                        llm_url=llm_url,
                        llm_model=llm_model,
                        verbose=True,
                    )

                return
            else:
                info("Let's refine the spec...")


@skill_group.command(name="eval")
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--llm-url", help="LLM base URL")
@click.option("--llm-model", help="LLM model name")
@click.option("--verbose", is_flag=True, help="Show detailed output")
@click.option("--save-results", is_flag=True, default=True, help="Save results to file")
def evaluate_skill(
    skill_path: str,
    llm_url: Optional[str],
    llm_model: Optional[str],
    verbose: bool,
    save_results: bool,
):
    """Evaluate a skill using LLM execution."""
    llm = get_llm_client(llm_url, llm_model)
    evaluator = SkillEvaluatorLLM(llm)

    skill_dir = Path(skill_path)

    # Display configuration panel
    print_panel(
        f"[bold]Skill:[/bold] {skill_dir.name}\n"
        f"[bold]Model:[/bold] {llm.model}\n"
        f"[bold]Endpoint:[/bold] {llm.base_url}",
        title="Kubani Skill Evaluation",
        style="cyan",
    )
    console.print()

    try:
        with spinner("Running evaluation..."):
            results = evaluator.evaluate_skill(skill_dir, verbose=verbose)

        # Display summary in a table
        metrics = results["metrics"]

        # Results table
        results_table = create_table(title="Evaluation Results", columns=["Metric", "Value"])
        results_table.add_row("Accuracy", f"[bold]{metrics['accuracy']:.1f}%[/bold]")
        results_table.add_row("Tests Passed", f"{metrics['tests_passed']}/{metrics['tests_total']}")
        results_table.add_row(
            "Assertions Passed",
            f"{metrics['assertions_passed']}/{metrics['assertions_total']}",
        )
        results_table.add_row("Avg Latency", f"{metrics['avg_latency_ms']:.0f} ms")
        results_table.add_row("Avg Tokens/Test", f"{metrics['avg_tokens_per_test']['total']:.0f}")
        results_table.add_row("Total Tokens", f"{metrics['total_tokens']['total']}")
        console.print(results_table)
        console.print()

        # Summary line
        print_results_summary(
            passed=metrics["tests_passed"],
            failed=metrics["tests_total"] - metrics["tests_passed"],
        )

        # Save results
        if save_results:
            results_path = skill_dir / "latest_eval.json"
            evaluator.save_evaluation_results(results, results_path)

            report = evaluator.generate_evaluation_report(results)
            report_path = skill_dir / "latest_eval.md"
            report_path.write_text(report)

            console.print()
            info("Results saved:")
            console.print(f"   [muted]{results_path}[/muted]")
            console.print(f"   [muted]{report_path}[/muted]")

        # Ask if they want to improve
        if metrics["accuracy"] < 100:
            if click.confirm("\n🔧 Skill could be improved. Run improvement?", default=True):
                ctx = click.get_current_context()
                ctx.invoke(
                    improve_skill,
                    skill_path=skill_path,
                    llm_url=llm_url,
                    llm_model=llm_model,
                    goals=["accuracy"],
                )

    except Exception as e:
        error(f"Evaluation failed: {e}")
        sys.exit(1)


@skill_group.command(name="improve")
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--llm-url", help="LLM base URL")
@click.option("--llm-model", help="LLM model name")
@click.option(
    "--goals",
    multiple=True,
    default=["accuracy"],
    help="Improvement goals (accuracy, latency, tokens)",
)
@click.option("--auto-evaluate", is_flag=True, default=True, help="Evaluate after improvement")
def improve_skill(
    skill_path: str,
    llm_url: Optional[str],
    llm_model: Optional[str],
    goals: tuple,
    auto_evaluate: bool,
):
    """Improve a skill based on evaluation results."""
    llm = get_llm_client(llm_url, llm_model)
    improver = SkillImprover(llm)

    skill_dir = Path(skill_path)

    # Display configuration panel
    print_panel(
        f"[bold]Skill:[/bold] {skill_dir.name}\n"
        f"[bold]Goals:[/bold] {', '.join(goals)}\n"
        f"[bold]Model:[/bold] {llm.model}\n"
        f"[bold]Endpoint:[/bold] {llm.base_url}",
        title="Kubani Skill Improvement",
        style="yellow",
    )
    console.print()

    # Load evaluation results
    eval_path = skill_dir / "latest_eval.json"
    if not eval_path.exists():
        error("No evaluation results found. Run evaluation first.")
        sys.exit(1)

    with open(eval_path) as f:
        evaluation_results = json.load(f)

    # Analyze and improve
    with spinner("Analyzing evaluation results..."):
        analysis = improver.analyze_evaluation(evaluation_results)

    console.print(f"\n[bold]Analysis:[/bold] {analysis['analysis']}\n")

    if analysis.get("improvements"):
        # Display improvements in a table
        improvements_table = create_table(
            title="Improvement Suggestions", columns=["#", "Priority", "Issue", "Suggestion"]
        )
        for i, imp in enumerate(analysis["improvements"], 1):
            priority_color = {"high": "red", "medium": "yellow", "low": "green"}.get(
                imp["priority"].lower(), "white"
            )
            improvements_table.add_row(
                str(i),
                f"[{priority_color}]{imp['priority'].upper()}[/{priority_color}]",
                imp["issue"],
                imp["suggestion"],
            )
        console.print(improvements_table)
        console.print()

    if click.confirm("Apply improvements?", default=True):
        with spinner("Generating improved skill..."):
            result = improver.improve_skill(skill_dir, evaluation_results, list(goals))

        # Save improved skill
        improver.save_improved_skill(skill_dir, result["improved_skill"], create_backup=True)

        success("Skill improved and saved (backup created)")
        console.print(f"   [muted]Tokens used: {result['tokens_used']['total']}[/muted]")

        # Re-evaluate
        if auto_evaluate:
            console.print()
            info("Re-evaluating improved skill...")
            console.print()
            ctx = click.get_current_context()
            ctx.invoke(
                evaluate_skill,
                skill_path=skill_path,
                llm_url=llm_url,
                llm_model=llm_model,
                verbose=True,
                save_results=True,
            )


@skill_group.command(name="list")
@click.option(
    "--category", type=click.Choice(["development", "core", "agents"]), help="Filter by category"
)
@click.option("--search", "-s", type=str, help="Search skills by keyword in name or description")
def list_skills(category: Optional[str], search: Optional[str]):
    """List all skills with optional search."""
    skills_dir = Path("skills")

    if not skills_dir.exists():
        warning("No skills directory found")
        return

    categories = [category] if category else ["development", "core", "agents"]
    total_found = 0

    for cat in categories:
        cat_dir = skills_dir / cat
        if not cat_dir.exists():
            continue

        skills = [d for d in cat_dir.iterdir() if d.is_dir()]

        if not skills:
            continue

        # Filter by search term if provided
        matching_skills = []
        for skill_dir in sorted(skills):
            if search:
                # Check skill name
                if search.lower() in skill_dir.name.lower():
                    matching_skills.append(skill_dir)
                    continue

                # Check metadata description
                metadata_path = skill_dir / "metadata.json"
                if metadata_path.exists():
                    with open(metadata_path) as f:
                        metadata = json.load(f)
                    desc = metadata.get("description", "")
                    if search.lower() in desc.lower():
                        matching_skills.append(skill_dir)
                        continue

                # Check SKILL.md content
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    content = skill_md.read_text()
                    if search.lower() in content.lower():
                        matching_skills.append(skill_dir)
            else:
                matching_skills.append(skill_dir)

        if not matching_skills:
            continue

        # Create table for this category
        table = create_table(
            title=f"[bold]{cat.upper()}[/bold]",
            columns=["Name", "Version", "Status", "Description"],
        )

        for skill_dir in matching_skills:
            total_found += 1
            # Load metadata if available
            metadata_path = skill_dir / "metadata.json"
            if metadata_path.exists():
                with open(metadata_path) as f:
                    metadata = json.load(f)

                desc = metadata.get("description", "No description")
                # Truncate long descriptions
                if len(desc) > 50:
                    desc = desc[:47] + "..."
                version = metadata.get("version", "-")
                status = metadata.get("status", "-")

                # Color status
                status_colors = {
                    "production": "green",
                    "development": "yellow",
                    "draft": "blue",
                }
                status_color = status_colors.get(status.lower(), "white")

                table.add_row(
                    skill_dir.name,
                    f"v{version}",
                    f"[{status_color}]{status}[/{status_color}]",
                    desc,
                )
            else:
                table.add_row(skill_dir.name, "-", "-", "[muted]No metadata[/muted]")

        console.print(table)
        console.print()

    # Summary
    if search:
        info(f"Found [bold]{total_found}[/bold] skill(s) matching '[bold]{search}[/bold]'")
    else:
        info(f"Total: [bold]{total_found}[/bold] skill(s)")


@skill_group.command(name="validate")
@click.argument("skill_path", type=click.Path(exists=True), required=False)
@click.option("--all", "validate_all", is_flag=True, help="Validate all skills")
def validate_skill(skill_path: Optional[str], validate_all: bool):
    """
    Validate skill format and structure.

    Checks for required files and proper formatting.

    Examples:
        kubani-dev skill validate skills/development/my-skill
        kubani-dev skill validate --all
    """

    def validate_single_skill(path: Path) -> tuple[bool, list[str]]:
        """Validate a single skill directory."""
        errors = []

        # Check SKILL.md exists
        skill_md = path / "SKILL.md"
        if not skill_md.exists():
            errors.append("Missing SKILL.md")
        else:
            content = skill_md.read_text()
            if len(content) < 100:
                errors.append("SKILL.md too short (< 100 chars)")
            if "## " not in content:
                errors.append("SKILL.md missing section headers")

        # Check test_cases.yaml exists and is valid
        test_cases = path / "test_cases.yaml"
        if not test_cases.exists():
            errors.append("Missing test_cases.yaml")
        else:
            try:
                with open(test_cases) as f:
                    data = yaml.safe_load(f)
                if not data or "test_cases" not in data:
                    errors.append("test_cases.yaml missing 'test_cases' key")
                elif not data["test_cases"]:
                    errors.append("test_cases.yaml has no test cases")
            except yaml.YAMLError as e:
                errors.append(f"Invalid YAML in test_cases.yaml: {e}")

        # Check metadata.json if present
        metadata = path / "metadata.json"
        if metadata.exists():
            try:
                with open(metadata) as f:
                    data = json.load(f)
                required = ["name", "description", "version"]
                missing = [k for k in required if k not in data]
                if missing:
                    errors.append(f"metadata.json missing fields: {missing}")
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in metadata.json: {e}")

        return len(errors) == 0, errors

    skills_to_validate = []

    if validate_all:
        skills_dir = Path("skills")
        for cat in ["development", "core", "agents"]:
            cat_dir = skills_dir / cat
            if cat_dir.exists():
                for skill_dir in cat_dir.iterdir():
                    if skill_dir.is_dir():
                        skills_to_validate.append(skill_dir)
    elif skill_path:
        skills_to_validate.append(Path(skill_path))
    else:
        error("Provide a skill path or use --all")
        return

    info(f"Validating [bold]{len(skills_to_validate)}[/bold] skill(s)...")
    console.print()

    passed = 0
    failed = 0

    for skill_dir in skills_to_validate:
        is_valid, validation_errors = validate_single_skill(skill_dir)

        if is_valid:
            success(skill_dir.name)
            passed += 1
        else:
            error(skill_dir.name)
            for err in validation_errors:
                console.print(f"   [muted]-[/muted] {err}")
            failed += 1

    console.print()
    print_results_summary(passed=passed, failed=failed)

    if failed > 0:
        sys.exit(1)


@skill_group.command(name="info")
@click.argument("skill_path", type=click.Path(exists=True))
def skill_info(skill_path: str):
    """Show detailed information about a skill."""
    skill_dir = Path(skill_path)

    # Load metadata
    metadata_path = skill_dir / "metadata.json"
    metadata = {}
    if metadata_path.exists():
        with open(metadata_path) as f:
            metadata = json.load(f)

    # Display skill info in a table
    info_table = create_table(title=f"Skill: {skill_dir.name}", columns=["Property", "Value"])
    info_table.add_row("Description", metadata.get("description", "N/A"))
    info_table.add_row("Version", metadata.get("version", "N/A"))
    info_table.add_row("Status", metadata.get("status", "N/A"))
    info_table.add_row("Created by", metadata.get("created_by", "N/A"))
    console.print(info_table)

    # Load latest evaluation
    eval_path = skill_dir / "latest_eval.json"
    if eval_path.exists():
        with open(eval_path) as f:
            eval_data = json.load(f)

        metrics = eval_data["metrics"]
        console.print()
        eval_table = create_table(
            title=f"Latest Evaluation ({eval_data.get('timestamp', 'unknown')})",
            columns=["Metric", "Value"],
        )
        eval_table.add_row("Accuracy", f"[bold]{metrics['accuracy']:.1f}%[/bold]")
        eval_table.add_row("Tests Passed", f"{metrics['tests_passed']}/{metrics['tests_total']}")
        eval_table.add_row("Avg Latency", f"{metrics['avg_latency_ms']:.0f} ms")
        eval_table.add_row("Avg Tokens", f"{metrics['avg_tokens_per_test']['total']:.0f}")
        console.print(eval_table)

    console.print()


@skill_group.command(name="eval-history")
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--limit", default=10, help="Maximum number of evaluations to show")
def eval_history(skill_path: str, limit: int):
    """View evaluation history for a skill."""
    skill_dir = Path(skill_path)

    print_panel(
        f"[bold]Skill:[/bold] {skill_dir.name}",
        title="Evaluation History",
        style="cyan",
    )

    # Check for latest_eval.json
    latest_eval = skill_dir / "latest_eval.json"
    if not latest_eval.exists():
        warning("No evaluation history found")
        return

    # Load and display latest evaluation
    with open(latest_eval) as f:
        eval_data = json.load(f)

    metrics = eval_data["metrics"]
    timestamp = eval_data.get("timestamp", "unknown")

    # Summary table
    console.print()
    summary_table = create_table(title=f"Evaluation @ {timestamp}", columns=["Metric", "Value"])
    summary_table.add_row("Accuracy", f"[bold]{metrics['accuracy']:.1f}%[/bold]")
    summary_table.add_row("Tests Passed", f"{metrics['tests_passed']}/{metrics['tests_total']}")
    summary_table.add_row("Avg Latency", f"{metrics['avg_latency_ms']:.0f} ms")
    summary_table.add_row("Avg Tokens", f"{metrics['avg_tokens_per_test']['total']:.0f}")
    console.print(summary_table)

    # Show test results summary
    test_results = eval_data.get("test_results", [])
    if test_results:
        console.print()
        results_table = create_table(
            title="Test Results", columns=["Status", "Test", "Critic", "Confidence"]
        )
        for test in test_results:
            status = "[green]PASS[/green]" if test["passed"] else "[red]FAIL[/red]"
            critic_status = "-"
            confidence = "-"

            # Show critic feedback if available
            if "critic" in test and test["critic"]:
                critic = test["critic"]
                critic_status = "[green]OK[/green]" if critic.get("success") else "[red]FAIL[/red]"
                confidence = f"{critic.get('confidence', 0):.2f}"

            results_table.add_row(status, test["name"], critic_status, confidence)

        console.print(results_table)

    console.print()


@skill_group.command(name="promote")
@click.argument("skill_path", type=click.Path(exists=True))
@click.option(
    "--category", type=click.Choice(["core", "agents"]), required=True, help="Target category"
)
@click.option("--version", help="Explicit version (default: auto-bump)")
@click.option(
    "--bump",
    type=click.Choice(["patch", "minor", "major"]),
    default="patch",
    help="Version bump type",
)
def promote_skill(skill_path: str, category: str, version: Optional[str], bump: str):
    """Promote a skill from development to production."""
    from kubani_dev.version_utils import bump_version

    skill_dir = Path(skill_path)
    skill_name = skill_dir.name

    # Load metadata
    metadata_path = skill_dir / "metadata.json"
    if not metadata_path.exists():
        error("No metadata.json found")
        return

    with open(metadata_path) as f:
        metadata = json.load(f)

    # Determine new version
    if version:
        new_version = version
    else:
        # Auto-bump version
        current_version = metadata.get("version", "0.0.0")
        new_version = bump_version(current_version, bump)

    # Show promotion summary
    promotion_info = f"""[bold]Skill:[/bold] {skill_name}
[bold]From:[/bold] skills/development/{skill_name}
[bold]To:[/bold] skills/{category}/{skill_name}
[bold]Version:[/bold] {metadata.get("version", "unknown")} → {new_version}"""
    print_panel(promotion_info, title="Skill Promotion", style="magenta")

    # Confirm
    if not click.confirm("\nProceed with promotion?"):
        warning("Promotion cancelled")
        return

    # Create target directory
    target_dir = Path(f"skills/{category}/{skill_name}")
    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy files
    import shutil

    for file in ["SKILL.md", "test_cases.yaml", "metadata.json"]:
        src = skill_dir / file
        if src.exists():
            shutil.copy2(src, target_dir / file)

    # Copy latest evaluation if exists
    latest_eval = skill_dir / "latest_eval.json"
    if latest_eval.exists():
        shutil.copy2(latest_eval, target_dir / "latest_eval.json")

    latest_eval_md = skill_dir / "latest_eval.md"
    if latest_eval_md.exists():
        shutil.copy2(latest_eval_md, target_dir / "latest_eval.md")

    # Update metadata
    metadata["version"] = new_version
    metadata["status"] = "production"
    metadata["category"] = category

    with open(target_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    console.print()
    success("Skill promoted successfully!")
    info(f"Location: {target_dir}")
    info(f"Version: {new_version}")
    muted(f"Tip: Remove from development with: rm -rf {skill_dir}")
