"""LLM-integrated skill management commands."""

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


def get_llm_client(
    base_url: Optional[str] = None,
    model: Optional[str] = None
) -> LLMClient:
    """Get LLM client with configuration."""
    base_url = base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434")
    model = model or os.getenv("LLM_MODEL", "qwen2.5:3b")
    
    return LLMClient(base_url=base_url, model=model)


@click.group(name="skill-llm")
def skill_llm():
    """LLM-integrated skill development commands."""
    pass


@skill_llm.command(name="draft")
@click.argument("description")
@click.option("--llm-url", help="LLM base URL")
@click.option("--llm-model", help="LLM model name")
@click.option("--output-dir", type=click.Path(), help="Output directory (default: skills/development/<skill-name>)")
@click.option("--non-interactive", is_flag=True, help="Skip conversation, generate directly")
def draft_skill(
    description: str,
    llm_url: Optional[str],
    llm_model: Optional[str],
    output_dir: Optional[str],
    non_interactive: bool
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
            "error_handling": ["Handle errors gracefully"]
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
                        verbose=True
                    )
                
                return
            else:
                click.echo("Let's refine the spec...")


@skill_llm.command(name="eval")
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
    save_results: bool
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
        click.echo("\n" + "="*60)
        click.echo("📊 EVALUATION RESULTS")
        click.echo("="*60)
        click.echo(f"Accuracy:           {metrics['accuracy']:.1f}%")
        click.echo(f"Tests Passed:       {metrics['tests_passed']}/{metrics['tests_total']}")
        click.echo(f"Assertions Passed:  {metrics['assertions_passed']}/{metrics['assertions_total']}")
        click.echo(f"Avg Latency:        {metrics['avg_latency_ms']:.0f} ms")
        click.echo(f"Avg Tokens/Test:    {metrics['avg_tokens_per_test']['total']:.0f}")
        click.echo(f"Total Tokens:       {metrics['total_tokens']['total']}")
        click.echo("="*60)
        
        # Save results
        if save_results:
            results_path = skill_dir / "latest_eval.json"
            evaluator.save_evaluation_results(results, results_path)
            
            report = evaluator.generate_evaluation_report(results)
            report_path = skill_dir / "latest_eval.md"
            report_path.write_text(report)
            
            click.echo(f"\n💾 Results saved:")
            click.echo(f"   - {results_path}")
            click.echo(f"   - {report_path}")
        
        # Ask if they want to improve
        if metrics['accuracy'] < 100:
            if click.confirm("\n🔧 Skill could be improved. Run improvement?", default=True):
                ctx = click.get_current_context()
                ctx.invoke(
                    improve_skill,
                    skill_path=skill_path,
                    llm_url=llm_url,
                    llm_model=llm_model,
                    goals=["accuracy"]
                )
        
    except Exception as e:
        click.echo(f"❌ Evaluation failed: {e}", err=True)
        sys.exit(1)


@skill_llm.command(name="improve")
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--llm-url", help="LLM base URL")
@click.option("--llm-model", help="LLM model name")
@click.option("--goals", multiple=True, default=["accuracy"], help="Improvement goals (accuracy, latency, tokens)")
@click.option("--auto-evaluate", is_flag=True, default=True, help="Evaluate after improvement")
def improve_skill(
    skill_path: str,
    llm_url: Optional[str],
    llm_model: Optional[str],
    goals: tuple,
    auto_evaluate: bool
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
        
        result = improver.improve_skill(
            skill_dir,
            evaluation_results,
            list(goals)
        )
        
        # Save improved skill
        improver.save_improved_skill(
            skill_dir,
            result["improved_skill"],
            create_backup=True
        )
        
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
                save_results=True
            )


@skill_llm.command(name="list")
@click.option("--category", type=click.Choice(["development", "core", "agents"]), help="Filter by category")
def list_skills(category: Optional[str]):
    """List all skills."""
    skills_dir = Path("skills")
    
    if not skills_dir.exists():
        click.echo("No skills directory found")
        return
    
    categories = [category] if category else ["development", "core", "agents"]
    
    for cat in categories:
        cat_dir = skills_dir / cat
        if not cat_dir.exists():
            continue
        
        skills = [d for d in cat_dir.iterdir() if d.is_dir()]
        
        if not skills:
            continue
        
        click.echo(f"\n📁 {cat.upper()}")
        click.echo("─" * 60)
        
        for skill_dir in sorted(skills):
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


@skill_llm.command(name="info")
@click.argument("skill_path", type=click.Path(exists=True))
def skill_info(skill_path: str):
    """Show detailed information about a skill."""
    skill_dir = Path(skill_path)
    
    click.echo(f"\n📋 Skill: {skill_dir.name}")
    click.echo("="*60)
    
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
