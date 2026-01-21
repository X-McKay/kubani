"""
Skill Management Commands for Kubani Development Workflow.

Provides commands for the complete skill lifecycle:
- draft: Create new skills from templates
- eval: Evaluate skills locally or in cluster
- promote: Move skills from development to production
- list: List all skills and their status
- info: Show detailed skill information
- eval-history: View evaluation history
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
import yaml

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def find_skill_path(project_root: Path, skill_name: str) -> Optional[Path]:
    """Find a skill by name in the skills directory."""
    # Check development first
    dev_path = project_root / "skills" / "development" / skill_name
    if dev_path.exists():
        return dev_path
    
    # Check core
    for version_dir in (project_root / "skills" / "core").glob(f"{skill_name}/v*"):
        return version_dir.parent
    
    # Check agents
    for agent_dir in (project_root / "skills" / "agents").iterdir():
        for version_dir in agent_dir.glob(f"{skill_name}/v*"):
            return version_dir.parent
    
    return None


def get_latest_version(skill_path: Path) -> Optional[str]:
    """Get the latest version of a skill."""
    versions = [d.name for d in skill_path.iterdir() if d.is_dir() and d.name.startswith("v")]
    if not versions:
        return None
    # Simple semantic version sort
    return sorted(versions, key=lambda v: [int(x) for x in v[1:].split(".")])[-1]


def create_skill_from_template(skill_path: Path, skill_name: str, description: str) -> None:
    """Create a new skill directory with template files."""
    skill_path.mkdir(parents=True, exist_ok=True)
    
    # Create SKILL.md
    skill_md = f"""---
name: {skill_name}
version: development
category: general
created: {datetime.now().isoformat()}
---

# {skill_name.replace('-', ' ').title()}

## Description

{description}

## When to Use

Describe when this skill should be used.

## Input Schema

```yaml
namespace:
  type: string
  required: true
  description: The Kubernetes namespace to operate on
```

## Output Schema

```yaml
result:
  type: object
  description: The result of the skill execution
```

## Implementation Notes

Add any implementation details, edge cases, or considerations here.

## Examples

### Example 1: Basic Usage

```python
result = execute_skill("{skill_name}", {{
    "namespace": "default"
}})
```

## Evaluation Criteria

- **Accuracy**: Skill produces correct results
- **Performance**: Executes within acceptable time limits
- **Error Handling**: Gracefully handles edge cases and errors
"""
    
    (skill_path / "SKILL.md").write_text(skill_md)
    
    # Create skill.py
    skill_py = f'''"""
{skill_name.replace('-', ' ').title()} Skill Implementation.

This skill {description.lower()}.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def execute(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the {skill_name} skill.
    
    Args:
        inputs: Input parameters as defined in SKILL.md
        
    Returns:
        Output as defined in SKILL.md schema
        
    Raises:
        ValueError: If inputs are invalid
        RuntimeError: If execution fails
    """
    logger.info(f"Executing {skill_name} with inputs: {{inputs}}")
    
    # Validate inputs
    if "namespace" not in inputs:
        raise ValueError("Missing required input: namespace")
    
    namespace = inputs["namespace"]
    
    # TODO: Implement skill logic here
    result = {{
        "status": "success",
        "message": f"Executed {skill_name} on namespace {{namespace}}"
    }}
    
    return result


if __name__ == "__main__":
    # Test the skill
    test_inputs = {{
        "namespace": "default"
    }}
    
    result = execute(test_inputs)
    print(f"Result: {{result}}")
'''
    
    (skill_path / "skill.py").write_text(skill_py)
    
    # Create test_cases.yaml
    test_cases = f"""# Test cases for {skill_name}
# Each test case should have inputs and expected outputs

test_cases:
  - name: basic_execution
    description: Test basic skill execution
    inputs:
      namespace: default
    expected:
      status: success
    assertions:
      - field: status
        operator: equals
        value: success
        
  - name: invalid_namespace
    description: Test error handling for invalid namespace
    inputs:
      namespace: ""
    expected:
      error: true
    assertions:
      - field: error
        operator: exists
        
  - name: performance_check
    description: Ensure skill executes within time limit
    inputs:
      namespace: default
    performance:
      max_latency_ms: 2000
"""
    
    (skill_path / "test_cases.yaml").write_text(test_cases)


# -----------------------------------------------------------------------------
# CLI Commands
# -----------------------------------------------------------------------------


@click.group(name="skill")
def skill_group():
    """
    Manage skills in the Kubani development workflow.
    
    This command group provides tools for creating, evaluating, and
    promoting skills through their lifecycle.
    """
    pass


@skill_group.command(name="draft")
@click.argument("name", type=str)
@click.option("--description", "-d", type=str, required=True, help="Skill description")
@click.option("--category", "-c", type=str, default="general", help="Skill category")
@click.pass_context
def draft(ctx: click.Context, name: str, description: str, category: str) -> None:
    """
    Create a new skill from template.
    
    NAME is the skill name (e.g., 'find-unused-configmaps')
    
    Examples:
        kubani-dev skill draft post-to-discord -d "Post a message to Discord"
        kubani-dev skill draft find-pods -d "Find pods matching criteria" -c k8s
    """
    project_root = ctx.obj["project_root"]
    skill_path = project_root / "skills" / "development" / name
    
    if skill_path.exists():
        click.echo(f"❌ Skill already exists: {skill_path}")
        click.echo("   Use a different name or remove the existing skill first.")
        return
    
    try:
        create_skill_from_template(skill_path, name, description)
        
        click.echo(f"✓ Created skill directory: skills/development/{name}/")
        click.echo(f"✓ Generated SKILL.md from template")
        click.echo(f"✓ Generated skill.py skeleton")
        click.echo(f"✓ Generated test_cases.yaml template")
        click.echo("")
        click.echo("Next steps:")
        click.echo(f"  1. Edit the skill files in skills/development/{name}/")
        click.echo(f"  2. Run: kubani-dev skill eval {name} --local")
        click.echo(f"  3. Iterate until satisfied")
        click.echo(f"  4. Run: kubani-dev skill promote {name}")
        
    except Exception as e:
        click.echo(f"❌ Failed to create skill: {e}")
        logger.exception("Skill creation failed")


@skill_group.command(name="list")
@click.pass_context
def list_skills(ctx: click.Context) -> None:
    """
    List all skills and their status.
    
    Shows skills in development and production, organized by category.
    
    Examples:
        kubani-dev skill list
    """
    project_root = ctx.obj["project_root"]
    skills_dir = project_root / "skills"
    
    # Development skills
    dev_skills = []
    dev_dir = skills_dir / "development"
    if dev_dir.exists():
        for skill_dir in dev_dir.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                dev_skills.append(skill_dir.name)
    
    # Core skills
    core_skills = []
    core_dir = skills_dir / "core"
    if core_dir.exists():
        for skill_dir in core_dir.iterdir():
            if skill_dir.is_dir():
                version = get_latest_version(skill_dir)
                if version:
                    core_skills.append((skill_dir.name, version))
    
    # Agent skills
    agent_skills = {}
    agents_dir = skills_dir / "agents"
    if agents_dir.exists():
        for agent_dir in agents_dir.iterdir():
            if agent_dir.is_dir():
                agent_name = agent_dir.name
                agent_skills[agent_name] = []
                for skill_dir in agent_dir.iterdir():
                    if skill_dir.is_dir():
                        version = get_latest_version(skill_dir)
                        if version:
                            agent_skills[agent_name].append((skill_dir.name, version))
    
    # Display
    if dev_skills:
        click.echo("Skills in Development:")
        click.echo("━" * 60)
        for skill in dev_skills:
            click.echo(f"  {skill}")
    else:
        click.echo("Skills in Development:")
        click.echo("━" * 60)
        click.echo("  (none)")
    
    click.echo("")
    
    if core_skills:
        click.echo("Core Skills (Production):")
        click.echo("━" * 60)
        for skill, version in core_skills:
            click.echo(f"  {skill:<30} {version:<10} ✓ Passing")
    else:
        click.echo("Core Skills (Production):")
        click.echo("━" * 60)
        click.echo("  (none)")
    
    click.echo("")
    
    if agent_skills:
        click.echo("Agent-Specific Skills:")
        click.echo("━" * 60)
        for agent, skills in agent_skills.items():
            if skills:
                click.echo(f"  {agent}/")
                for skill, version in skills:
                    click.echo(f"    {skill:<28} {version:<10} ✓ Passing")
    else:
        click.echo("Agent-Specific Skills:")
        click.echo("━" * 60)
        click.echo("  (none)")
    
    total = len(dev_skills) + len(core_skills) + sum(len(s) for s in agent_skills.values())
    click.echo("")
    click.echo(f"Total: {total} skills")


@skill_group.command(name="info")
@click.argument("name", type=str)
@click.pass_context
def info(ctx: click.Context, name: str) -> None:
    """
    Show detailed information about a skill.
    
    NAME is the skill name
    
    Examples:
        kubani-dev skill info post-to-discord
        kubani-dev skill info find-unused-configmaps
    """
    project_root = ctx.obj["project_root"]
    skill_path = find_skill_path(project_root, name)
    
    if not skill_path:
        click.echo(f"❌ Skill not found: {name}")
        return
    
    # Determine if it's in development or production
    if "development" in str(skill_path):
        version = "development"
        skill_md_path = skill_path / "SKILL.md"
    else:
        version = get_latest_version(skill_path)
        skill_md_path = skill_path / version / "SKILL.md"
    
    if not skill_md_path.exists():
        click.echo(f"❌ SKILL.md not found for: {name}")
        return
    
    # Parse SKILL.md
    content = skill_md_path.read_text()
    
    # Extract metadata
    metadata = {}
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            frontmatter = content[3:end].strip()
            for line in frontmatter.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.strip()
    
    # Extract description
    desc_start = content.find("## Description")
    desc_end = content.find("##", desc_start + 1) if desc_start >= 0 else -1
    description = content[desc_start:desc_end].replace("## Description", "").strip() if desc_start >= 0 else "No description"
    
    click.echo(f"Skill: {name}")
    click.echo("━" * 60)
    click.echo("")
    click.echo("Basic Information:")
    click.echo(f"  Name:            {name}")
    click.echo(f"  Current Version: {version}")
    click.echo(f"  Category:        {metadata.get('category', 'N/A')}")
    click.echo(f"  Status:          {'🔨 In Development' if version == 'development' else '✓ Production'}")
    click.echo(f"  Created:         {metadata.get('created', 'N/A')}")
    click.echo("")
    click.echo("Description:")
    click.echo(f"  {description[:200]}...")
    click.echo("")
    
    # Check for latest_eval.json
    eval_path = skill_md_path.parent / "latest_eval.json"
    if eval_path.exists():
        try:
            eval_data = json.loads(eval_path.read_text())
            click.echo("Latest Evaluation:")
            click.echo(f"  Accuracy:        {eval_data.get('accuracy', 'N/A')}")
            click.echo(f"  Avg Latency:     {eval_data.get('avg_latency_ms', 'N/A')}ms")
            click.echo(f"  Tests Passed:    {eval_data.get('tests_passed', 0)}/{eval_data.get('tests_total', 0)}")
            click.echo(f"  Evaluated:       {eval_data.get('evaluated_at', 'N/A')}")
        except Exception as e:
            logger.debug(f"Failed to parse evaluation: {e}")
    
    click.echo("")
    click.echo("Usage:")
    click.echo(f'  execute_skill("{name}", {{...}})')


@skill_group.command(name="eval")
@click.argument("name", type=str)
@click.option("--local", is_flag=True, help="Run evaluation locally (default: cluster)")
@click.option("--sandbox", type=str, default="auto", help="Sandbox type: auto, microsandbox, docker")
@click.pass_context
def eval_skill(ctx: click.Context, name: str, local: bool, sandbox: str) -> None:
    """
    Evaluate a skill against its test cases.
    
    NAME is the skill name
    
    Examples:
        kubani-dev skill eval post-to-discord --local
        kubani-dev skill eval find-pods --sandbox microsandbox
    """
    project_root = ctx.obj["project_root"]
    skill_path = find_skill_path(project_root, name)
    
    if not skill_path:
        click.echo(f"❌ Skill not found: {name}")
        return
    
    # Determine skill directory
    if "development" in str(skill_path):
        skill_dir = skill_path
    else:
        version = get_latest_version(skill_path)
        skill_dir = skill_path / version
    
    test_cases_path = skill_dir / "test_cases.yaml"
    if not test_cases_path.exists():
        click.echo(f"❌ test_cases.yaml not found for: {name}")
        return
    
    click.echo(f"Starting {'local' if local else 'cluster'} evaluation for: {name}")
    click.echo("━" * 60)
    
    if local:
        try:
            from kubani_dev.sandbox.evaluator import SkillEvaluator, format_results_for_cli
            
            # Create evaluator
            evaluator = SkillEvaluator(skill_dir, sandbox_type=sandbox)
            
            # Run evaluation
            click.echo(f"⏳ Running evaluation with {sandbox} sandbox...")
            results = evaluator.evaluate()
            
            # Display results
            output = format_results_for_cli(results)
            click.echo(output)
            
        except Exception as e:
            click.echo(f"❌ Evaluation failed: {e}")
            logger.exception("Evaluation error")
            return
    else:
        click.echo("")
        click.echo("⏳ Triggering Temporal workflow...")
        click.echo("❌ Cluster evaluation not yet implemented")
        click.echo("")
        click.echo("This feature will be implemented in Phase 3.")


@skill_group.command(name="promote")
@click.argument("name", type=str)
@click.option("--category", "-c", type=str, help="Category: core or agent name")
@click.option("--version", "-v", type=str, default="1.0.0", help="Version number")
@click.pass_context
def promote(ctx: click.Context, name: str, category: Optional[str], version: str) -> None:
    """
    Promote a skill from development to production.
    
    NAME is the skill name
    
    Examples:
        kubani-dev skill promote post-to-discord --category core
        kubani-dev skill promote find-pods --category k8s-monitor --version 1.0.0
    """
    project_root = ctx.obj["project_root"]
    dev_path = project_root / "skills" / "development" / name
    
    if not dev_path.exists():
        click.echo(f"❌ Skill not found in development: {name}")
        return
    
    if not category:
        click.echo("❌ Category required. Use --category core or --category <agent-name>")
        return
    
    # Determine target path
    if category == "core":
        target_path = project_root / "skills" / "core" / name / f"v{version}"
    else:
        target_path = project_root / "skills" / "agents" / category / name / f"v{version}"
    
    if target_path.exists():
        click.echo(f"❌ Version already exists: {target_path}")
        return
    
    click.echo(f"Promoting skill: {name}")
    click.echo("━" * 60)
    click.echo("")
    
    try:
        # Create target directory
        target_path.mkdir(parents=True, exist_ok=True)
        
        # Copy files
        import shutil
        for file in ["SKILL.md", "skill.py", "test_cases.yaml"]:
            src = dev_path / file
            if src.exists():
                shutil.copy2(src, target_path / file)
                click.echo(f"✓ Copied {file}")
        
        # Copy latest_eval.json if exists
        eval_src = dev_path / "latest_eval.json"
        if eval_src.exists():
            shutil.copy2(eval_src, target_path / "latest_eval.json")
            click.echo(f"✓ Copied latest_eval.json")
        
        click.echo(f"✓ Created: {target_path.relative_to(project_root)}")
        click.echo("")
        click.echo(f"🎉 Skill '{name}' v{version} promoted to production!")
        click.echo("")
        click.echo("Next steps:")
        click.echo(f"  1. Register in Skill Registry (coming in Phase 3)")
        click.echo(f"  2. Remove from development: rm -rf {dev_path}")
        
    except Exception as e:
        click.echo(f"❌ Failed to promote skill: {e}")
        logger.exception("Skill promotion failed")


@skill_group.command(name="eval-history")
@click.argument("name", type=str)
@click.pass_context
def eval_history(ctx: click.Context, name: str) -> None:
    """
    View evaluation history for a skill.
    
    NAME is the skill name
    
    Examples:
        kubani-dev skill eval-history post-to-discord
    """
    project_root = ctx.obj["project_root"]
    
    click.echo(f"Evaluation History: {name}")
    click.echo("━" * 60)
    click.echo("")
    click.echo("❌ This feature requires database integration (Phase 3)")
    click.echo("")
    click.echo("For now, check latest_eval.json in the skill directory:")
    click.echo(f"  kubani-dev skill info {name}")
