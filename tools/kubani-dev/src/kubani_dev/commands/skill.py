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

logger = logging.getLogger(__name__)


def get_llm_client(base_url: Optional[str] = None, model: Optional[str] = None) -> LLMClient:
    """Get LLM client with configuration."""
    # Default to Kubani LLM endpoint (OpenAI-compatible)
    base_url = base_url or os.getenv("LLM_BASE_URL", "https://llm.almckay.io")
    model = model or os.getenv("LLM_MODEL", "nvidia/Qwen3-14B-FP4")

    return LLMClient(base_url=base_url, model=model)


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
@click.argument("description")
@click.option("--llm-url", help="LLM base URL")
@click.option("--llm-model", help="LLM model name")
@click.option(
    "--output-dir",
    type=click.Path(),
    help="Output directory (default: skills/development/<skill-name>)",
)
@click.option("--non-interactive", is_flag=True, help="Skip conversation, generate directly")
def draft_skill(
    description: str,
    llm_url: Optional[str],
    llm_model: Optional[str],
    output_dir: Optional[str],
    non_interactive: bool,
):
    """Draft a new skill using LLM-powered conversation."""
    llm = get_llm_client(llm_url, llm_model)
    drafter = SkillDrafter(llm)

    click.echo(f"🤖 Using LLM: {llm.model} @ {llm.base_url}")
    click.echo(f"📝 Creating skill: {description}\n")

    if non_interactive:
        # Generate directly without conversation
        click.echo("Generating skill directly...")

        # Create a simple spec from description
        spec = {
            "name": description.lower().replace(" ", "-")[:50],
            "description": description,
            "inputs": {},
            "outputs": {},
            "steps": ["Execute the task as described"],
            "error_handling": ["Handle errors gracefully"],
        }

        # Generate files
        if not output_dir:
            output_dir = f"skills/development/{spec['name']}"

        output_path = Path(output_dir)
        files = drafter.generate_skill_files(spec, output_path)

        click.echo(f"\n✅ Skill created at: {output_path}")
        for filename in files:
            click.echo(f"   - {filename}")

        return

    # Interactive conversation
    response = drafter.start_conversation(description)
    click.echo(f"🤖 Assistant: {response}\n")

    # Conversation loop
    while True:
        user_input = click.prompt("You", type=str)

        if user_input.lower() in ["quit", "exit", "cancel"]:
            click.echo("❌ Cancelled")
            return

        result = drafter.continue_conversation(user_input)

        click.echo(f"\n🤖 Assistant: {result['message']}\n")

        if result["is_ready"]:
            spec = result["spec"]

            # Show spec
            click.echo("📋 Skill Specification:")
            click.echo(json.dumps(spec, indent=2))
            click.echo()

            # Confirm
            if click.confirm("Generate skill files with this spec?", default=True):
                # Determine output directory
                if not output_dir:
                    output_dir = f"skills/development/{spec['name']}"

                output_path = Path(output_dir)
                files = drafter.generate_skill_files(spec, output_path)

                click.echo(f"\n✅ Skill created at: {output_path}")
                for filename in files:
                    click.echo(f"   - {filename}")

                # Ask if they want to evaluate
                if click.confirm("\n🧪 Run evaluation now?", default=True):
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
                click.echo("Let's refine the spec...")


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

    click.echo(f"🧪 Evaluating skill: {skill_dir.name}")
    click.echo(f"🤖 Using LLM: {llm.model} @ {llm.base_url}\n")

    try:
        results = evaluator.evaluate_skill(skill_dir, verbose=verbose)

        # Display summary
        metrics = results["metrics"]
        click.echo("\n" + "=" * 60)
        click.echo("📊 EVALUATION RESULTS")
        click.echo("=" * 60)
        click.echo(f"Accuracy:           {metrics['accuracy']:.1f}%")
        click.echo(f"Tests Passed:       {metrics['tests_passed']}/{metrics['tests_total']}")
        click.echo(
            f"Assertions Passed:  {metrics['assertions_passed']}/{metrics['assertions_total']}"
        )
        click.echo(f"Avg Latency:        {metrics['avg_latency_ms']:.0f} ms")
        click.echo(f"Avg Tokens/Test:    {metrics['avg_tokens_per_test']['total']:.0f}")
        click.echo(f"Total Tokens:       {metrics['total_tokens']['total']}")
        click.echo("=" * 60)

        # Save results
        if save_results:
            results_path = skill_dir / "latest_eval.json"
            evaluator.save_evaluation_results(results, results_path)

            report = evaluator.generate_evaluation_report(results)
            report_path = skill_dir / "latest_eval.md"
            report_path.write_text(report)

            click.echo("\n💾 Results saved:")
            click.echo(f"   - {results_path}")
            click.echo(f"   - {report_path}")

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
        click.echo(f"❌ Evaluation failed: {e}", err=True)
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

    click.echo(f"🔧 Improving skill: {skill_dir.name}")
    click.echo(f"🎯 Goals: {', '.join(goals)}")
    click.echo(f"🤖 Using LLM: {llm.model} @ {llm.base_url}\n")

    # Load evaluation results
    eval_path = skill_dir / "latest_eval.json"
    if not eval_path.exists():
        click.echo("❌ No evaluation results found. Run evaluation first.", err=True)
        sys.exit(1)

    with open(eval_path) as f:
        evaluation_results = json.load(f)

    # Analyze and improve
    click.echo("Analyzing evaluation results...")
    analysis = improver.analyze_evaluation(evaluation_results)

    click.echo(f"\n📊 Analysis: {analysis['analysis']}\n")

    if analysis.get("improvements"):
        click.echo("💡 Improvement Suggestions:")
        for i, imp in enumerate(analysis["improvements"], 1):
            click.echo(f"{i}. [{imp['priority'].upper()}] {imp['issue']}")
            click.echo(f"   → {imp['suggestion']}")
            click.echo(f"   Impact: {imp['expected_impact']}\n")

    if click.confirm("Apply improvements?", default=True):
        click.echo("\nGenerating improved skill...")

        result = improver.improve_skill(skill_dir, evaluation_results, list(goals))

        # Save improved skill
        improver.save_improved_skill(skill_dir, result["improved_skill"], create_backup=True)

        click.echo("✅ Skill improved and saved (backup created)")
        click.echo(f"   Tokens used: {result['tokens_used']['total']}")

        # Re-evaluate
        if auto_evaluate:
            click.echo("\n🔄 Re-evaluating improved skill...\n")
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
        click.echo("No skills directory found")
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

        click.echo(f"\n📁 {cat.upper()}")
        click.echo("─" * 60)

        for skill_dir in matching_skills:
            total_found += 1
            # Load metadata if available
            metadata_path = skill_dir / "metadata.json"
            if metadata_path.exists():
                with open(metadata_path) as f:
                    metadata = json.load(f)

                desc = metadata.get("description", "No description")
                version = metadata.get("version", "unknown")
                status = metadata.get("status", "unknown")

                click.echo(f"  {skill_dir.name} (v{version}) [{status}]")
                click.echo(f"    {desc}")
            else:
                click.echo(f"  {skill_dir.name}")

    # Summary
    if search:
        click.echo(f"\n🔍 Found {total_found} skill(s) matching '{search}'")
    else:
        click.echo(f"\n📊 Total: {total_found} skill(s)")


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
        click.echo("❌ Provide a skill path or use --all")
        return

    click.echo(f"🔍 Validating {len(skills_to_validate)} skill(s)...\n")

    passed = 0
    failed = 0

    for skill_dir in skills_to_validate:
        is_valid, errors = validate_single_skill(skill_dir)

        if is_valid:
            click.echo(f"✅ {skill_dir.name}")
            passed += 1
        else:
            click.echo(f"❌ {skill_dir.name}")
            for err in errors:
                click.echo(f"   - {err}")
            failed += 1

    click.echo(f"\n📊 Results: {passed} passed, {failed} failed")

    if failed > 0:
        sys.exit(1)


@skill_group.command(name="info")
@click.argument("skill_path", type=click.Path(exists=True))
def skill_info(skill_path: str):
    """Show detailed information about a skill."""
    skill_dir = Path(skill_path)

    click.echo(f"\n📋 Skill: {skill_dir.name}")
    click.echo("=" * 60)

    # Load metadata
    metadata_path = skill_dir / "metadata.json"
    if metadata_path.exists():
        with open(metadata_path) as f:
            metadata = json.load(f)

        click.echo(f"Description: {metadata.get('description', 'N/A')}")
        click.echo(f"Version:     {metadata.get('version', 'N/A')}")
        click.echo(f"Status:      {metadata.get('status', 'N/A')}")
        click.echo(f"Created by:  {metadata.get('created_by', 'N/A')}")

    # Load latest evaluation
    eval_path = skill_dir / "latest_eval.json"
    if eval_path.exists():
        with open(eval_path) as f:
            eval_data = json.load(f)

        metrics = eval_data["metrics"]
        click.echo(f"\n📊 Latest Evaluation ({eval_data['timestamp']}):")
        click.echo(f"  Accuracy:     {metrics['accuracy']:.1f}%")
        click.echo(f"  Tests Passed: {metrics['tests_passed']}/{metrics['tests_total']}")
        click.echo(f"  Avg Latency:  {metrics['avg_latency_ms']:.0f} ms")
        click.echo(f"  Avg Tokens:   {metrics['avg_tokens_per_test']['total']:.0f}")

    click.echo()


@skill_group.command(name="eval-history")
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--limit", default=10, help="Maximum number of evaluations to show")
def eval_history(skill_path: str, limit: int):
    """View evaluation history for a skill."""
    skill_dir = Path(skill_path)

    click.echo(f"\n📊 Evaluation History: {skill_dir.name}")
    click.echo("=" * 80)

    # Check for latest_eval.json
    latest_eval = skill_dir / "latest_eval.json"
    if not latest_eval.exists():
        click.echo("❌ No evaluation history found")
        return

    # Load and display latest evaluation
    with open(latest_eval) as f:
        eval_data = json.load(f)

    metrics = eval_data["metrics"]
    timestamp = eval_data.get("timestamp", "unknown")

    click.echo(f"\n🕐 {timestamp}")
    click.echo(f"  Accuracy:     {metrics['accuracy']:.1f}%")
    click.echo(f"  Tests Passed: {metrics['tests_passed']}/{metrics['tests_total']}")
    click.echo(f"  Avg Latency:  {metrics['avg_latency_ms']:.0f} ms")
    click.echo(f"  Avg Tokens:   {metrics['avg_tokens_per_test']['total']:.0f}")

    # Show test results summary
    test_results = eval_data.get("test_results", [])
    if test_results:
        click.echo("\n  Test Results:")
        for test in test_results:
            status = "✅" if test["passed"] else "❌"
            click.echo(f"    {status} {test['name']}")

            # Show critic feedback if available
            if "critic" in test and test["critic"]:
                critic = test["critic"]
                confidence = critic.get("confidence", 0)
                click.echo(
                    f"       Critic: {'✅' if critic['success'] else '❌'} (confidence: {confidence:.2f})"
                )
                if critic.get("suggestions"):
                    click.echo(f"       Suggestion: {critic['suggestions']}")

    click.echo()


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
        click.echo("❌ No metadata.json found")
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

    click.echo(f"\n🚀 Promoting skill: {skill_name}")
    click.echo(f"   From: skills/development/{skill_name}")
    click.echo(f"   To:   skills/{category}/{skill_name}")
    click.echo(f"   Version: {metadata.get('version', 'unknown')} → {new_version}")

    # Confirm
    if not click.confirm("\nProceed with promotion?"):
        click.echo("❌ Promotion cancelled")
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

    click.echo("\n✅ Skill promoted successfully!")
    click.echo(f"   Location: {target_dir}")
    click.echo(f"   Version: {new_version}")
    click.echo(f"\n💡 Tip: Remove from development with: rm -rf {skill_dir}")
