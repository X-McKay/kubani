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
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
import questionary
import typer
import yaml

# Typer app for registration with main CLI
skill_app = typer.Typer(help="Skill management commands")

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
            skill_name = questionary.text(
                "Skill name:",
                instruction="(use kebab-case)",
                validate=lambda x: len(x) > 0 or "Name is required",
            ).ask()

            if skill_name is None:  # User cancelled with Ctrl+C
                error("Cancelled")
                sys.exit(1)

        if not skill_description:
            skill_description = questionary.text(
                "Skill description:",
                multiline=True,
                instruction="(Esc+Enter to submit, Ctrl+C to cancel)",
            ).ask()

            if skill_description is None:  # User cancelled with Ctrl+C
                error("Cancelled")
                sys.exit(1)
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
        user_input = questionary.text(
            "You:",
            multiline=True,
            instruction="(Esc+Enter to submit, Ctrl+C or type 'exit' to cancel)",
        ).ask()

        # Handle Ctrl+C cancellation
        if user_input is None:
            console.print()
            warning("Cancelled")
            return

        # Handle text-based exit
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
@click.option("--llm-url", help="LLM base URL (for quick mode)")
@click.option("--llm-model", help="LLM model name (for quick mode)")
@click.option(
    "--mode",
    type=click.Choice(["quick", "full"]),
    default="quick",
    help="quick: single large model | full: compare 4 configurations",
)
@click.option("--parallel", is_flag=True, help="Run full mode evaluations in parallel")
@click.option("--verbose", is_flag=True, help="Show detailed output")
@click.option("--save-results", is_flag=True, default=True, help="Save results to file")
def evaluate_skill(
    skill_path: str,
    llm_url: Optional[str],
    llm_model: Optional[str],
    mode: str,
    parallel: bool,
    verbose: bool,
    save_results: bool,
):
    """Evaluate a skill using LLM execution.

    Supports two modes:

    \b
    quick (default): Single evaluation with large model + thinking enabled.
                    Fast feedback for iterative development.

    \b
    full: Compare 4 configurations:
          - Large model with thinking enabled
          - Large model with thinking disabled
          - Small model with thinking enabled
          - Small model with thinking disabled

          Generates comparison matrix with accuracy, latency, and token metrics,
          plus an LLM-generated analysis summary.

    Examples:
        kubani-dev skill eval skills/development/my-skill
        kubani-dev skill eval skills/development/my-skill --mode full
        kubani-dev skill eval skills/development/my-skill --mode full --parallel
    """
    skill_dir = Path(skill_path)

    if mode == "full":
        _run_full_evaluation(skill_dir, parallel, verbose, save_results)
    else:
        _run_quick_evaluation(skill_dir, llm_url, llm_model, verbose, save_results)


def _run_quick_evaluation(
    skill_dir: Path,
    llm_url: Optional[str],
    llm_model: Optional[str],
    verbose: bool,
    save_results: bool,
):
    """Run quick mode evaluation (single configuration)."""
    llm = get_llm_client(llm_url, llm_model)
    evaluator = SkillEvaluatorLLM(llm)

    # Display configuration panel
    print_panel(
        f"[bold]Skill:[/bold] {skill_dir.name}\n"
        f"[bold]Mode:[/bold] quick\n"
        f"[bold]Model:[/bold] {llm.model}\n"
        f"[bold]Endpoint:[/bold] {llm.base_url}",
        title="Kubani Skill Evaluation",
        style="cyan",
    )
    console.print()

    try:
        start_time = time.time()
        with spinner("Running evaluation..."):
            results = evaluator.evaluate_skill(skill_dir, verbose=verbose)
        elapsed_time = time.time() - start_time

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

        # Format elapsed time
        if elapsed_time < 60:
            elapsed_str = f"{elapsed_time:.1f}s"
        else:
            minutes = int(elapsed_time // 60)
            seconds = elapsed_time % 60
            elapsed_str = f"{minutes}m {seconds:.1f}s"
        results_table.add_row("Total Elapsed Time", elapsed_str)

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
            if click.confirm("\n Skill could be improved. Run improvement?", default=True):
                ctx = click.get_current_context()
                ctx.invoke(
                    improve_skill,
                    skill_path=str(skill_dir),
                    llm_url=llm_url,
                    llm_model=llm_model,
                    goals=["accuracy"],
                )

    except Exception as e:
        error(f"Evaluation failed: {e}")
        sys.exit(1)


def _run_full_evaluation(
    skill_dir: Path,
    parallel: bool,
    verbose: bool,
    save_results: bool,
):
    """Run full mode evaluation (4 configurations comparison)."""
    # Lazy imports to avoid linter issues with top-level imports
    from kubani_dev.eval_orchestrator import create_full_evaluator
    from kubani_dev.eval_reporter import (
        generate_comparison_table,
        generate_rankings,
        generate_summary,
        save_comparison_report,
    )

    # Display configuration panel
    exec_mode = "parallel" if parallel else "sequential"
    print_panel(
        f"[bold]Skill:[/bold] {skill_dir.name}\n"
        f"[bold]Mode:[/bold] full (4 configurations)\n"
        f"[bold]Execution:[/bold] {exec_mode}\n"
        f"[bold]Configs:[/bold] Large+Think, Large-NoThink, Small+Think, Small-NoThink",
        title="Kubani Multi-Config Skill Evaluation",
        style="magenta",
    )
    console.print()

    # Create orchestrator
    orchestrator = create_full_evaluator(parallel=parallel)

    # Progress tracking
    config_status = {}

    def progress_callback(config_name: str, status: str):
        config_status[config_name] = status
        if verbose:
            status_icon = {"queued": "...", "running": "->", "completed": "+", "failed": "x"}.get(
                status, "?"
            )
            console.print(f"  [{status_icon}] {config_name}: {status}")

    try:
        info(f"Running evaluation across {len(orchestrator.configurations)} configurations...")
        console.print()

        # Run evaluation
        report = orchestrator.evaluate(
            skill_dir,
            verbose=verbose,
            progress_callback=progress_callback if verbose else None,
        )

        console.print()

        # Display comparison table
        comparison_table = generate_comparison_table(report)
        console.print(comparison_table)

        # Display rankings
        rankings_text = generate_rankings(report)
        if rankings_text:
            console.print(rankings_text)

        # Generate and display summary
        info("Generating analysis summary...")
        with spinner("Analyzing results..."):
            report.summary = generate_summary(report)

        console.print()
        print_panel(report.summary, title="Analysis Summary", style="green")
        console.print()

        # Save results
        if save_results:
            json_path, md_path = save_comparison_report(
                report,
                skill_dir,
                generate_llm_summary=False,  # Already generated above
            )

            console.print()
            info("Results saved:")
            console.print(f"   [muted]{json_path}[/muted]")
            console.print(f"   [muted]{md_path}[/muted]")

        # Summary of best configuration
        rankings = report.get_rankings()
        if rankings.get("accuracy"):
            best_accuracy = rankings["accuracy"][0]
            best_result = report.get_result(best_accuracy)
            if best_result:
                console.print()
                success(
                    f"Best accuracy: [bold]{best_result.config.display_name}[/bold] "
                    f"({best_result.accuracy:.1f}%)"
                )

    except Exception as e:
        error(f"Full evaluation failed: {e}")
        import traceback

        if verbose:
            traceback.print_exc()
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
        metadata_data = None
        if metadata.exists():
            try:
                with open(metadata) as f:
                    metadata_data = json.load(f)
                required = ["name", "description", "version"]
                missing = [k for k in required if k not in metadata_data]
                if missing:
                    errors.append(f"metadata.json missing fields: {missing}")
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in metadata.json: {e}")

        # Check scripts/ directory if present or referenced in metadata
        scripts_dir = path / "scripts"
        if metadata_data and metadata_data.get("has_scripts"):
            if not scripts_dir.exists():
                errors.append(
                    "metadata.json declares has_scripts=True but scripts/ directory missing"
                )
            elif metadata_data.get("scripts", {}).get("main"):
                main_script = path / metadata_data["scripts"]["main"]
                if not main_script.exists():
                    errors.append(f"Main script not found: {metadata_data['scripts']['main']}")

        # Validate scripts if they exist
        if scripts_dir.exists():
            for script_file in scripts_dir.glob("*.py"):
                script_content = script_file.read_text()

                # Syntax check
                try:
                    compile(script_content, str(script_file), "exec")
                except SyntaxError as e:
                    errors.append(f"Syntax error in {script_file.name}: {e}")
                    continue

                # Check for execute function
                if "def execute(" not in script_content:
                    errors.append(f"Script {script_file.name} missing required 'execute' function")

        # Validate allowed_tools if specified in metadata
        if metadata_data and metadata_data.get("allowed_tools"):
            allowed_tools = metadata_data["allowed_tools"]
            if not isinstance(allowed_tools, list):
                errors.append("metadata.json allowed_tools must be a list")
            else:
                # Validate tool format (should be tool name or mcp__server__tool format)
                valid_tool_patterns = [
                    r"^(Read|Write|Edit|Bash|Glob|Grep|WebFetch|WebSearch)$",  # Core tools
                    r"^mcp__[\w-]+__[\w-]+$",  # MCP tools
                ]
                import re

                for tool in allowed_tools:
                    if not any(re.match(p, tool) for p in valid_tool_patterns):
                        errors.append(f"Invalid tool format in allowed_tools: {tool}")

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


@skill_group.command(name="run")
@click.argument("skill_name")
@click.option("--context", "-c", help="JSON context string")
@click.option("--context-file", "-f", type=click.Path(exists=True), help="JSON context file")
@click.option("--llm-url", help="LLM base URL")
@click.option("--llm-model", help="LLM model name")
@click.option("--trace", "show_trace", is_flag=True, help="Show full execution trace")
@click.option("--no-record", is_flag=True, help="Don't record trace to backend")
@click.option("--output", "-o", type=click.Choice(["json", "summary"]), default="summary")
def run_skill(
    skill_name: str,
    context: Optional[str],
    context_file: Optional[str],
    llm_url: Optional[str],
    llm_model: Optional[str],
    show_trace: bool,
    no_record: bool,
    output: str,
):
    """
    Execute a skill with given context.

    \b
    Examples:
        kubani-dev skill run k8s/diagnostic/investigate-pod-failure \\
            --context '{"pod": "nginx-abc", "namespace": "default"}'

        kubani-dev skill run investigate-pod-failure -f context.json --trace
    """
    import asyncio
    import json as json_module

    # Parse context
    ctx = {}
    if context_file:
        with open(context_file) as f:
            ctx = json_module.load(f)
    elif context:
        try:
            ctx = json_module.loads(context)
        except json_module.JSONDecodeError as e:
            error(f"Invalid JSON context: {e}")
            sys.exit(1)

    # Get skills directory
    skills_dir = Path.cwd() / "agents" / "skills"
    if not skills_dir.exists():
        # Try relative to script
        skills_dir = Path(__file__).parents[4] / "agents" / "skills"

    if not skills_dir.exists():
        error(f"Skills directory not found: {skills_dir}")
        sys.exit(1)

    async def execute():
        from skill_dev_tools.skill_executor import SkillExecutor
        from skill_dev_tools.llm import LLMClientWrapper
        from skill_dev_tools.config import SkillConfig

        # Create LLM client
        llm = LLMClientWrapper(
            base_url=llm_url or os.getenv("LLM_BASE_URL", "https://llm.almckay.io/v1"),
            model=llm_model or os.getenv("LLM_MODEL", "nvidia/Qwen3-14B-FP4"),
        )

        # Create executor
        executor = SkillExecutor(
            skills_dir=skills_dir,
            llm_client=llm,
        )

        # Execute skill
        config = SkillConfig(
            name=skill_name,
            record_trace=not no_record,
        )

        info(f"Executing skill: [bold]{skill_name}[/bold]")
        if ctx:
            muted(f"Context: {json_module.dumps(ctx, indent=2)[:200]}...")

        with spinner("Running skill..."):
            result = await executor.execute(skill_name, context=ctx, config=config)

        await llm.close()
        return result

    # Run async execution
    result = asyncio.run(execute())

    # Output results
    if output == "json" or show_trace:
        console.print_json(result.model_dump_json(indent=2))
    else:
        # Summary output
        if result.output.get("status") == "success":
            success("Skill completed successfully")
        elif result.output.get("status") == "failure":
            error("Skill failed")
        else:
            warning(f"Skill status: {result.output.get('status', 'unknown')}")

        console.print()

        if result.output.get("summary"):
            info(f"Summary: {result.output['summary']}")

        if result.output.get("findings"):
            console.print("\n[bold]Findings:[/bold]")
            for finding in result.output["findings"]:
                console.print(f"  • {finding}")

        if result.output.get("recommendations"):
            console.print("\n[bold]Recommendations:[/bold]")
            for rec in result.output["recommendations"]:
                console.print(f"  • {rec}")

        # Metrics
        console.print()
        muted(
            f"Duration: {result.duration_ms:.0f}ms | Tokens: {result.total_tokens} | LLM calls: {result.llm_calls}"
        )

        if not no_record:
            muted(f"Trace ID: {result.trace_id}")


@skill_group.command(name="eval-matrix")
@click.argument("skill_name")
@click.option("--suite", "-s", type=click.Path(exists=True), help="Evaluation suite YAML")
@click.option(
    "--matrix",
    "-m",
    default="model:local",
    help="Matrix config (e.g., 'model:opus,haiku thinking:on,off')",
)
@click.option("--llm-url", help="Default LLM base URL")
@click.option("--output", "-o", type=click.Choice(["table", "json"]), default="table")
def eval_matrix(
    skill_name: str,
    suite: Optional[str],
    matrix: str,
    llm_url: Optional[str],
    output: str,
):
    """
    Evaluate skill across model/config matrix.

    \b
    Examples:
        kubani-dev skill eval-matrix investigate-pod-failure \\
            --matrix "model:opus,haiku thinking:on,off"

        kubani-dev skill eval-matrix my-skill \\
            --suite test_cases.yaml \\
            --matrix "model:local,opus"
    """
    import asyncio

    # Get skills directory
    skills_dir = Path.cwd() / "agents" / "skills"
    if not skills_dir.exists():
        skills_dir = Path(__file__).parents[4] / "agents" / "skills"

    # Load test cases
    test_cases = []
    if suite:
        with open(suite) as f:
            suite_data = yaml.safe_load(f)
            test_cases = suite_data.get("test_cases", [])
    else:
        # Try to find test_cases.yaml in skill directory
        skill_path = skills_dir / skill_name.replace("/", os.sep)
        test_file = skill_path / "test_cases.yaml"
        if test_file.exists():
            with open(test_file) as f:
                suite_data = yaml.safe_load(f)
                test_cases = suite_data.get("test_cases", [])

    if not test_cases:
        warning("No test cases found. Running with empty context.")
        test_cases = [{"name": "default", "context": {}}]

    async def run_matrix():
        from skill_dev_tools.skill_executor import SkillExecutor
        from skill_dev_tools.evaluation import ModelMatrix
        from skill_dev_tools.llm import LLMClientWrapper

        # Create base executor
        llm = LLMClientWrapper(
            base_url=llm_url or os.getenv("LLM_BASE_URL", "https://llm.almckay.io/v1"),
        )
        executor = SkillExecutor(skills_dir=skills_dir, llm_client=llm)

        # Create matrix
        model_matrix = ModelMatrix.from_string(matrix)

        info(f"Running matrix evaluation for [bold]{skill_name}[/bold]")
        info(f"Matrix: {matrix}")
        info(f"Test cases: {len(test_cases)}")
        console.print()

        with spinner("Running matrix evaluation..."):
            report = await model_matrix.evaluate(executor, skill_name, test_cases)

        await llm.close()
        return report

    report = asyncio.run(run_matrix())

    # Output results
    if output == "json":
        import json as json_module

        console.print_json(
            json_module.dumps(
                {
                    "skill": report.skill_name,
                    "dimensions": report.dimensions,
                    "results": [
                        {
                            "config": r.config,
                            "metrics": r.metrics,
                        }
                        for r in report.results
                    ],
                },
                indent=2,
            )
        )
    else:
        # Table output
        table = create_table(title=f"Matrix Evaluation: {report.skill_name}")

        rows = report.to_table()
        if rows:
            for header in rows[0]:
                table.add_column(header)
            for row in rows[1:]:
                # Color code accuracy
                colored_row = list(row)
                acc_idx = len(row) - 3  # Accuracy column
                acc_val = float(row[acc_idx].rstrip("%")) / 100
                if acc_val >= 0.9:
                    colored_row[acc_idx] = f"[green]{row[acc_idx]}[/green]"
                elif acc_val >= 0.7:
                    colored_row[acc_idx] = f"[yellow]{row[acc_idx]}[/yellow]"
                else:
                    colored_row[acc_idx] = f"[red]{row[acc_idx]}[/red]"
                table.add_row(*colored_row)

        console.print(table)


@skill_group.command(name="traces")
@click.argument("skill_name")
@click.option("--last", "-n", default=10, help="Number of traces to show")
@click.option("--output", "-o", type=click.Choice(["table", "json"]), default="table")
def show_traces(
    skill_name: str,
    last: int,
    output: str,
):
    """
    Show recent execution traces for a skill.

    \b
    Examples:
        kubani-dev skill traces investigate-pod-failure
        kubani-dev skill traces my-skill --last 5 --output json
    """
    import asyncio
    import json as json_module

    skills_dir = Path.cwd() / "agents" / "skills"
    if not skills_dir.exists():
        skills_dir = Path(__file__).parents[4] / "agents" / "skills"

    async def get_traces():
        from skill_dev_tools.skill_executor import SkillExecutor

        executor = SkillExecutor(skills_dir=skills_dir)
        return await executor.get_recent_traces(skill_name, limit=last)

    traces = asyncio.run(get_traces())

    if not traces:
        warning(f"No traces found for skill: {skill_name}")
        return

    if output == "json":
        console.print_json(
            json_module.dumps([t.model_dump() for t in traces], indent=2, default=str)
        )
    else:
        # Table output
        table = create_table(title=f"Recent Traces: {skill_name}")
        table.add_column("Trace ID", style="cyan")
        table.add_column("Time")
        table.add_column("Status")
        table.add_column("Duration")
        table.add_column("Tokens")

        for t in traces:
            status = t.output.get("status", "unknown")
            status_color = (
                "green" if status == "success" else "red" if status == "failure" else "yellow"
            )

            table.add_row(
                t.trace_id[:12],
                t.start_time.strftime("%Y-%m-%d %H:%M"),
                f"[{status_color}]{status}[/{status_color}]",
                f"{t.duration_ms:.0f}ms" if t.duration_ms else "—",
                str(t.total_tokens),
            )

        console.print(table)


@skill_group.command(name="create")
@click.argument("skill_name")
@click.option(
    "--category", "-c", default="development", help="Skill category (k8s/diagnostic, etc.)"
)
@click.option("--description", "-d", help="Short description")
@click.option("--with-tests", is_flag=True, default=True, help="Generate test cases template")
@click.option("--with-scripts", is_flag=True, help="Include scripts directory")
def create_skill(
    skill_name: str,
    category: str,
    description: Optional[str],
    with_tests: bool,
    with_scripts: bool,
):
    """
    Create a new skill from template.

    Quick scaffolding for new skills. Use 'skill draft' for LLM-assisted
    skill creation with conversation.

    \b
    Examples:
        kubani-dev skill create investigate-oom-kill --category k8s/diagnostic
        kubani-dev skill create my-skill -d "Does something useful"
        kubani-dev skill create my-skill --with-scripts
    """

    # Normalize name
    skill_name = skill_name.lower().replace(" ", "-").replace("_", "-")

    # Determine output path
    skills_base = Path.cwd() / "agents" / "skills"
    if not skills_base.exists():
        skills_base = Path(__file__).parents[4] / "agents" / "skills"

    # Handle category path
    if "/" in category:
        skill_dir = skills_base / category / skill_name
    else:
        skill_dir = skills_base / category / skill_name

    if skill_dir.exists():
        error(f"Skill already exists: {skill_dir}")
        sys.exit(1)

    skill_dir.mkdir(parents=True, exist_ok=True)

    # Create SKILL.md
    skill_md_content = f"""---
name: {skill_name}
version: "0.1.0"
category: {category}
description: {description or "TODO: Add description"}
triggers: []
---

# {skill_name.replace("-", " ").title()}

## Purpose

{description or "TODO: Describe what this skill does"}

## When to Use

- TODO: List scenarios when this skill should be triggered

## Steps

1. **Gather Context**
   - TODO: What information needs to be collected

2. **Analyze**
   - TODO: What analysis should be performed

3. **Take Action**
   - TODO: What actions should be taken

## Expected Output

Return a JSON response with:
- `status`: "success" | "failure" | "needs_approval"
- `summary`: Brief description of findings
- `findings`: List of discovered issues
- `recommendations`: List of suggested actions

## Examples

### Example 1: Basic Usage

**Input Context:**
```json
{{
    "example_field": "value"
}}
```

**Expected Output:**
```json
{{
    "status": "success",
    "summary": "Analysis complete",
    "findings": ["Finding 1"],
    "recommendations": ["Recommendation 1"]
}}
```
"""

    (skill_dir / "SKILL.md").write_text(skill_md_content)

    # Create metadata.json
    metadata = {
        "name": skill_name,
        "version": "0.1.0",
        "category": category,
        "description": description or "TODO: Add description",
        "status": "development",
        "created_at": datetime.now().isoformat(),
        "created_by": "kubani-dev",
    }

    if with_scripts:
        metadata["has_scripts"] = True
        metadata["scripts"] = {"main": "scripts/main.py"}

    (skill_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    # Create test_cases.yaml
    if with_tests:
        test_cases_content = f"""# Test cases for {skill_name}
# Run with: kubani-dev skill eval {skill_dir.relative_to(Path.cwd()) if skill_dir.is_relative_to(Path.cwd()) else skill_dir}

test_cases:
  - name: "basic_test"
    description: "Basic functionality test"
    context:
      example_field: "test_value"
    expected:
      status: "success"
    assertions:
      - type: "contains"
        field: "summary"
        value: "complete"

  - name: "edge_case"
    description: "Test edge case handling"
    context:
      example_field: ""
    expected:
      status: "success"
"""
        (skill_dir / "test_cases.yaml").write_text(test_cases_content)

    # Create scripts directory if requested
    if with_scripts:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)

        main_script = '''"""Main script for skill execution."""

from typing import Any


def execute(context: dict[str, Any]) -> dict[str, Any]:
    """
    Execute the skill logic.

    Args:
        context: Input context from skill execution

    Returns:
        Result dictionary with status, findings, etc.
    """
    # TODO: Implement skill logic
    return {
        "status": "success",
        "summary": "Execution complete",
        "findings": [],
        "recommendations": [],
    }
'''
        (scripts_dir / "main.py").write_text(main_script)
        (scripts_dir / "__init__.py").write_text("")

    # Success output
    success(f"Created skill: [bold]{skill_name}[/bold]")
    console.print(f"   Location: {skill_dir}")
    console.print()

    # Show created files
    table = create_table(columns=["File", "Purpose"])
    table.add_row("SKILL.md", "Skill definition and instructions")
    table.add_row("metadata.json", "Skill metadata and configuration")
    if with_tests:
        table.add_row("test_cases.yaml", "Evaluation test cases")
    if with_scripts:
        table.add_row("scripts/main.py", "Executable skill logic")
    console.print(table)

    console.print()
    muted("Next steps:")
    muted(f"  1. Edit {skill_dir}/SKILL.md to define skill behavior")
    muted(f"  2. Run: kubani-dev skill run {skill_name} --context '{{...}}'")
    muted(f"  3. Evaluate: kubani-dev skill eval {skill_dir}")


@skill_group.command(name="watch")
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--context", "-c", help="JSON context string")
@click.option("--context-file", "-f", type=click.Path(exists=True), help="JSON context file")
@click.option("--llm-url", help="LLM base URL")
@click.option("--llm-model", help="LLM model name")
@click.option("--debounce", default=1.0, help="Debounce delay in seconds")
def watch_skill(
    skill_path: str,
    context: Optional[str],
    context_file: Optional[str],
    llm_url: Optional[str],
    llm_model: Optional[str],
    debounce: float,
):
    """
    Watch a skill for changes and auto-run.

    Hot reload development - automatically re-executes the skill when
    SKILL.md or scripts change.

    \b
    Examples:
        kubani-dev skill watch skills/development/my-skill
        kubani-dev skill watch ./my-skill --context '{"test": true}'
        kubani-dev skill watch ./my-skill -f context.json --debounce 2
    """
    from threading import Timer

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        error("watchdog not installed. Run: pip install watchdog")
        sys.exit(1)

    skill_dir = Path(skill_path)

    # Parse context
    ctx = {}
    if context_file:
        with open(context_file) as f:
            ctx = json.load(f)
    elif context:
        try:
            ctx = json.loads(context)
        except json.JSONDecodeError as e:
            error(f"Invalid JSON context: {e}")
            sys.exit(1)

    # Get skill name from path
    skill_name = skill_dir.name

    panel_content = f"[bold]Skill:[/bold] {skill_name}\n[bold]Path:[/bold] {skill_dir}"
    if ctx:
        panel_content += f"\n[bold]Context:[/bold] {json.dumps(ctx)[:50]}..."
    else:
        panel_content += "\n[bold]Context:[/bold] (none)"

    print_panel(
        panel_content,
        title="Skill Watch Mode",
        style="cyan",
    )
    console.print()
    info("Watching for changes... (Ctrl+C to stop)")
    console.print()

    # Debounced execution
    pending_timer: Timer | None = None

    def run_skill():
        console.print("\n" + "=" * 60)
        info(f"[{datetime.now().strftime('%H:%M:%S')}] Change detected, running skill...")
        console.print()

        try:
            import asyncio
            from skill_dev_tools.skill_executor import SkillExecutor
            from skill_dev_tools.llm import LLMClientWrapper
            from skill_dev_tools.config import SkillConfig

            async def execute():
                llm = LLMClientWrapper(
                    base_url=llm_url or os.getenv("LLM_BASE_URL", "https://llm.almckay.io/v1"),
                    model=llm_model or os.getenv("LLM_MODEL", "nvidia/Qwen3-14B-FP4"),
                )

                # Create executor with skill's parent as skills_dir
                executor = SkillExecutor(
                    skills_dir=skill_dir.parent,
                    llm_client=llm,
                )

                config = SkillConfig(name=skill_name, record_trace=True)

                with spinner("Running skill..."):
                    result = await executor.execute(skill_name, context=ctx, config=config)

                await llm.close()
                return result

            result = asyncio.run(execute())

            # Display result
            if result.output.get("status") == "success":
                success("Skill completed successfully")
            elif result.output.get("status") == "failure":
                error("Skill failed")
            else:
                warning(f"Skill status: {result.output.get('status', 'unknown')}")

            if result.output.get("summary"):
                console.print(f"\n[bold]Summary:[/bold] {result.output['summary']}")

            muted(f"\nDuration: {result.duration_ms:.0f}ms | Tokens: {result.total_tokens}")

        except Exception as e:
            error(f"Execution failed: {e}")

        console.print()
        muted("Watching for changes...")

    class SkillChangeHandler(FileSystemEventHandler):
        def on_modified(self, event):
            nonlocal pending_timer

            if event.is_directory:
                return

            # Only watch relevant files
            path = Path(event.src_path)
            if path.suffix not in (".md", ".py", ".yaml", ".yml", ".json"):
                return

            # Debounce
            if pending_timer:
                pending_timer.cancel()

            pending_timer = Timer(debounce, run_skill)
            pending_timer.start()

    # Initial run
    run_skill()

    # Set up file watcher
    event_handler = SkillChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, str(skill_dir), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        console.print()
        info("Watch mode stopped")

    observer.join()


@skill_group.command(name="stats")
@click.argument("skill_name", required=False)
@click.option("--backend", type=click.Choice(["jsonl", "duckdb"]), default="jsonl")
@click.option("--db", type=click.Path(), help="DuckDB database path")
@click.option("--by-skill", is_flag=True, help="Show breakdown by skill")
@click.option(
    "--over-time", type=click.Choice(["hour", "day", "week"]), help="Show performance over time"
)
def skill_stats(
    skill_name: Optional[str],
    backend: str,
    db: Optional[str],
    by_skill: bool,
    over_time: Optional[str],
):
    """
    Show execution statistics for skills.

    Aggregate metrics across execution traces. Uses DuckDB for
    advanced analytical queries.

    \b
    Examples:
        kubani-dev skill stats
        kubani-dev skill stats investigate-pod-failure
        kubani-dev skill stats --backend duckdb --db traces.duckdb
        kubani-dev skill stats --by-skill
        kubani-dev skill stats --over-time day
    """
    import asyncio

    async def get_stats():
        if backend == "duckdb":
            from skill_dev_tools.backends import DuckDBBackend

            trace_backend = DuckDBBackend(db or "traces.duckdb")
        else:
            from skill_dev_tools.backends import JsonlBackend

            skills_dir = Path.cwd() / "agents" / "skills"
            trace_backend = JsonlBackend(skills_dir / ".traces")

        stats = await trace_backend.get_stats(skill_name)

        # Additional analytics for DuckDB
        by_skill_data = None
        over_time_data = None

        if backend == "duckdb" and hasattr(trace_backend, "get_token_usage_by_skill"):
            if by_skill:
                by_skill_data = await trace_backend.get_token_usage_by_skill()
            if over_time:
                over_time_data = await trace_backend.get_performance_over_time(
                    skill_name, over_time
                )

        return stats, by_skill_data, over_time_data

    stats, by_skill_data, over_time_data = asyncio.run(get_stats())

    if not stats or stats.get("total_traces", 0) == 0:
        warning("No traces found")
        return

    print_panel(
        f"[bold]Skill:[/bold] {skill_name or 'All skills'}",
        title="Execution Statistics",
        style="cyan",
    )
    console.print()

    # Main stats table
    table = create_table(columns=["Metric", "Value"])
    table.add_row("Total Executions", str(stats.get("total_traces", 0)))
    table.add_row("Total Tokens", f"{stats.get('total_tokens', 0):,}")
    table.add_row("Avg Duration", f"{stats.get('avg_duration_ms', 0):.0f} ms")
    table.add_row("Avg Tokens", f"{stats.get('avg_tokens', 0):.0f}")
    table.add_row("Total LLM Calls", str(stats.get("total_llm_calls", 0)))
    table.add_row("Unique Skills", str(stats.get("unique_skills", "-")))
    table.add_row("First Execution", str(stats.get("first_trace", "-")))
    table.add_row("Last Execution", str(stats.get("last_trace", "-")))

    console.print(table)

    # By-skill breakdown
    if by_skill_data:
        console.print()
        skill_table = create_table(
            title="Token Usage by Skill",
            columns=["Skill", "Executions", "Total Tokens", "Avg Tokens", "Avg Duration"],
        )
        for row in by_skill_data[:10]:  # Top 10
            skill_table.add_row(
                row["skill_name"],
                str(row["executions"]),
                f"{row['total_tokens']:,}",
                f"{row['avg_tokens']:.0f}",
                f"{row['avg_duration_ms']:.0f} ms",
            )
        console.print(skill_table)

    # Over time breakdown
    if over_time_data:
        console.print()
        time_table = create_table(
            title=f"Performance Over Time ({over_time})",
            columns=["Time", "Executions", "Avg Duration", "Avg Tokens"],
        )
        for row in over_time_data[-10:]:  # Last 10 periods
            time_table.add_row(
                row["time_bucket"][:10] if row["time_bucket"] else "-",
                str(row["executions"]),
                f"{row['avg_duration_ms']:.0f} ms",
                f"{row['avg_tokens']:.0f}",
            )
        console.print(time_table)


# Note: Click commands are registered with the main CLI via skill_group
# The skill_app Typer instance is kept for future migration to native Typer commands
