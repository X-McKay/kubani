"""Activities for the Skill Auto workflow."""

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from kubani.workflows.skill_auto.models import (
    OverlapResult,
)

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from text, handling markdown code blocks."""
    # Try to find JSON in code blocks first
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if json_match:
        text = json_match.group(1).strip()

    # Find JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return json.loads(text[start:end])

    raise ValueError(f"Could not extract JSON from: {text[:200]}")


async def detect_skill_overlap(
    description: str,
    existing_skills: list[dict[str, str]],
    llm_client: Any,
) -> OverlapResult:
    """
    Detect if a new skill overlaps with existing skills.

    Args:
        description: Description of the new skill
        existing_skills: List of existing skills with name and description
        llm_client: LLM client for analysis

    Returns:
        OverlapResult with overlap assessment
    """
    if not existing_skills:
        return OverlapResult(
            has_overlap=False,
            confidence=1.0,
            overlapping_skills=[],
            reasoning="No existing skills to compare against",
            recommendation="proceed",
        )

    # Format existing skills for prompt
    skills_text = "\n".join(
        f"- {s['name']}: {s.get('description', 'No description')}" for s in existing_skills
    )

    prompt = f"""Analyze whether this new skill overlaps with any existing skills.

NEW SKILL DESCRIPTION:
{description}

EXISTING SKILLS:
{skills_text}

Respond with a JSON object:
{{
    "has_overlap": boolean,
    "confidence": float (0.0-1.0),
    "overlapping_skills": ["skill-name", ...],
    "reasoning": "explanation of why overlap exists or not",
    "recommendation": "proceed" | "merge" | "abort"
}}

Consider skills as overlapping if they:
- Address the same problem domain
- Would be triggered by similar scenarios
- Provide redundant functionality

Recommend "merge" if the new skill could enhance an existing one.
Recommend "abort" if the new skill is essentially a duplicate.
Recommend "proceed" if the skill is sufficiently distinct."""

    response = await llm_client.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,  # Low temperature for consistent analysis
    )

    try:
        data = _extract_json(response["content"])
        return OverlapResult(
            has_overlap=data.get("has_overlap", False),
            confidence=data.get("confidence", 0.5),
            overlapping_skills=data.get("overlapping_skills", []),
            reasoning=data.get("reasoning", ""),
            recommendation=data.get("recommendation", "proceed"),
        )
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse overlap detection response: {e}")
        return OverlapResult(
            has_overlap=False,
            confidence=0.0,
            overlapping_skills=[],
            reasoning=f"Failed to analyze: {e}",
            recommendation="proceed",
        )


async def load_existing_skills(
    skills_path: Path,
    include_development: bool = True,
) -> list[dict[str, str]]:
    """
    Load metadata for all existing skills.

    Args:
        skills_path: Path to skills directory
        include_development: Whether to include _development skills

    Returns:
        List of skill metadata dicts with name, description, path
    """
    skills = []

    if not skills_path.exists():
        return skills

    for skill_md in skills_path.rglob("SKILL.md"):
        # Skip _development if not included
        if not include_development and "_development" in str(skill_md):
            continue

        try:
            content = skill_md.read_text()

            # Parse YAML frontmatter
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    skills.append(
                        {
                            "name": frontmatter.get("name", skill_md.parent.name),
                            "description": frontmatter.get("description", ""),
                            "path": str(skill_md.parent),
                            "triggers": frontmatter.get("triggers", []),
                        }
                    )
        except Exception as e:
            logger.warning(f"Failed to load skill {skill_md}: {e}")

    return skills


async def infer_skill_structure(
    description: str,
    llm_client: Any,
    context: str | None = None,
) -> dict[str, Any]:
    """
    Infer skill structure from a description.

    Uses LLM to generate a complete skill specification including
    name, inputs, outputs, steps, and example test cases.

    Args:
        description: Natural language description of the skill
        llm_client: LLM client for generation
        context: Optional additional context

    Returns:
        Skill specification dict
    """
    context_section = f"\n\nADDITIONAL CONTEXT:\n{context}" if context else ""

    prompt = f"""Generate a complete skill specification from this description.

SKILL DESCRIPTION:
{description}{context_section}

Respond with a JSON object:
{{
    "name": "kebab-case-name",
    "description": "One-line description of what the skill does",
    "inputs": {{
        "param_name": {{
            "type": "string|number|boolean|array|object",
            "description": "What this parameter is for",
            "required": true|false
        }}
    }},
    "outputs": {{
        "field_name": {{
            "type": "string|number|boolean|array|object",
            "description": "What this output contains"
        }}
    }},
    "steps": [
        "Step 1: What to do first",
        "Step 2: What to do next",
        ...
    ],
    "error_handling": [
        "Handle case when X fails",
        ...
    ],
    "examples": [
        {{
            "name": "Example name",
            "description": "What this example demonstrates",
            "input": {{"param": "value"}},
            "expected_output": {{"field": "expected value"}}
        }}
    ]
}}

Make the skill focused and specific. Include 2-3 diverse examples that cover:
- A typical happy path case
- An edge case or boundary condition
- An error case if applicable"""

    response = await llm_client.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    return _extract_json(response["content"])


async def generate_test_cases(
    spec: dict[str, Any],
    llm_client: Any,
    seed_tests: str | None = None,
) -> str:
    """
    Generate test cases YAML from skill specification.

    Args:
        spec: Skill specification with examples
        llm_client: LLM client for generation
        seed_tests: Optional seed test cases to expand from

    Returns:
        YAML string with test cases
    """
    seed_section = ""
    if seed_tests:
        seed_section = f"""
SEED TEST CASES (expand from these):
{seed_tests}
"""

    examples_text = yaml.dump(spec.get("examples", []), default_flow_style=False)

    prompt = f"""Generate test cases for this skill specification.

SKILL: {spec.get("name")}
DESCRIPTION: {spec.get("description")}

INPUTS:
{yaml.dump(spec.get("inputs", {}), default_flow_style=False)}

OUTPUTS:
{yaml.dump(spec.get("outputs", {}), default_flow_style=False)}

EXAMPLES FROM SPEC:
{examples_text}
{seed_section}

Generate a YAML file with 3-5 test cases that cover:
1. Happy path - typical successful usage
2. Edge case - boundary conditions or unusual inputs
3. Error handling - invalid inputs or failure scenarios

Each test case should have:
- name: snake_case identifier
- description: What this test validates
- inputs: Input values for the test
- expected: Expected output fields (can be partial)
- assertions: List of checks with type, field, and description

Assertion types available:
- equals: Exact value match
- contains: Substring or membership check
- exists: Field is present
- not_empty: Field has a truthy value
- type: Check field type (string, number, boolean, list, dict)

Respond with ONLY the YAML content, no code blocks or explanation."""

    response = await llm_client.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    content = response["content"].strip()

    # Remove code block markers if present
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    return content


def _format_params(params: dict[str, Any]) -> str:
    """Format input/output parameters as markdown."""
    if not params:
        return "None"

    lines = []
    for name, info in params.items():
        if isinstance(info, dict):
            type_str = info.get("type", "any")
            desc = info.get("description", "")
            required = " (required)" if info.get("required") else ""
            lines.append(f"- **{name}** ({type_str}){required}: {desc}")
        else:
            lines.append(f"- **{name}**: {info}")

    return "\n".join(lines)


async def write_skill_files(
    spec: dict[str, Any],
    test_cases: str,
    output_dir: Path,
) -> str:
    """
    Write skill files to disk.

    Creates:
    - SKILL.md with frontmatter and content
    - test_cases.yaml with test definitions
    - metadata.json with creation info

    Args:
        spec: Skill specification
        test_cases: Test cases YAML content
        output_dir: Directory to write to (e.g., kubani/skills/_development)

    Returns:
        Path to created skill directory
    """
    from datetime import datetime

    skill_name = spec["name"]
    skill_dir = output_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Generate SKILL.md
    frontmatter = {
        "name": skill_name,
        "description": spec.get("description", ""),
        "version": "0.1.0",
        "category": "_development",
        "triggers": spec.get("triggers", []),
    }

    steps_text = "\n".join(f"{i}. {step}" for i, step in enumerate(spec.get("steps", []), 1))

    error_handling = spec.get("error_handling", ["Handle errors gracefully"])
    error_text = "\n".join(f"- {e}" for e in error_handling)

    skill_content = f"""---
{yaml.dump(frontmatter, default_flow_style=False).strip()}
---

# {skill_name.replace("-", " ").title()}

{spec.get("description", "")}

## Inputs

{_format_params(spec.get("inputs", {}))}

## Outputs

{_format_params(spec.get("outputs", {}))}

## Steps

{steps_text}

## Error Handling

{error_text}
"""

    (skill_dir / "SKILL.md").write_text(skill_content)
    (skill_dir / "test_cases.yaml").write_text(test_cases)

    # Write metadata
    metadata = {
        "name": skill_name,
        "version": "0.1.0",
        "status": "development",
        "created_at": datetime.now().isoformat(),
        "created_by": "auto-mode",
        "allowed_tools": ["read", "search", "web_fetch"],
    }
    (skill_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    return str(skill_dir)


async def run_evaluation(
    skill_path: str,
    llm_client: Any,
    evaluator: Any | None = None,
) -> "EvalMetrics":
    """
    Run skill evaluation and return metrics.

    Wrapper for SkillEvaluatorLLM that provides Temporal activity interface.

    Args:
        skill_path: Path to skill directory
        llm_client: LLM client for evaluation
        evaluator: Optional evaluator instance (for testing)

    Returns:
        EvalMetrics with evaluation results
    """
    from kubani.workflows.skill_auto.models import EvalMetrics

    if evaluator is None:
        from kubani_dev.skill_evaluator_llm import SkillEvaluatorLLM

        evaluator = SkillEvaluatorLLM(llm_client=llm_client)

    result = evaluator.evaluate_skill(skill_path)

    return EvalMetrics(
        accuracy=result.get("accuracy", 0.0),
        latency_ms=result.get("average_latency_ms", 0.0),
        tests_passed=result.get("passed_tests", 0),
        tests_total=result.get("total_tests", 0),
        critic_confidence=result.get("average_critic_confidence", 0.0),
        tokens_prompt=result.get("total_tokens", {}).get("prompt", 0),
        tokens_completion=result.get("total_tokens", {}).get("completion", 0),
    )


async def run_improvement(
    skill_path: str,
    feedback: str,
    llm_client: Any,
    improver: Any | None = None,
) -> dict[str, Any]:
    """
    Run skill improvement and return results.

    Creates timestamped backup before modifying skill files.
    Wrapper for SkillImprover that provides Temporal activity interface.

    Args:
        skill_path: Path to skill directory
        feedback: Evaluation feedback to address
        llm_client: LLM client for improvement
        improver: Optional improver instance (for testing)

    Returns:
        Dict with improvement results
    """
    from datetime import datetime

    skill_dir = Path(skill_path)

    # Create backup before modification
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = skill_dir / f"SKILL.md.backup.{timestamp}"
        backup_path.write_text(skill_md.read_text())

    if improver is None:
        from kubani_dev.skill_improver import SkillImprover

        improver = SkillImprover(llm_client=llm_client)

    result = improver.improve_skill(skill_path, feedback=feedback)

    # Apply improvements if any
    if result.get("improved") and result.get("new_content"):
        skill_md.write_text(result["new_content"])

    return result


async def send_notification(
    event: str,
    skill_name: str,
    channel: str,
    discord_client: Any,
    iteration: int | None = None,
    metrics: Any | None = None,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Send Discord notification for workflow events.

    Args:
        event: Event type (started, iteration_complete, complete, failed)
        skill_name: Name of the skill being developed
        channel: Discord channel name
        discord_client: Discord MCP client
        iteration: Current iteration number
        metrics: EvalMetrics for the iteration
        error: Error message if failed
        result: Final result dict if complete

    Returns:
        Dict with sent status and message_id
    """
    # Build embed based on event type
    if event == "started":
        embed = {
            "title": f"🚀 Skill Development Started: {skill_name}",
            "description": "Auto-mode skill development workflow has begun.",
            "color": 0x3498DB,  # Blue
            "fields": [],
        }
    elif event == "iteration_complete":
        accuracy_pct = f"{metrics.accuracy * 100:.1f}%" if metrics else "N/A"
        embed = {
            "title": f"📊 Iteration {iteration} Complete: {skill_name}",
            "description": f"Evaluation completed with accuracy: {accuracy_pct}",
            "color": 0xF39C12,  # Orange
            "fields": [
                {"name": "Accuracy", "value": accuracy_pct, "inline": True},
                {
                    "name": "Tests Passed",
                    "value": f"{metrics.tests_passed}/{metrics.tests_total}" if metrics else "N/A",
                    "inline": True,
                },
                {
                    "name": "Latency",
                    "value": f"{metrics.latency_ms:.0f}ms" if metrics else "N/A",
                    "inline": True,
                },
            ],
        }
    elif event == "complete":
        final_accuracy = result.get("final_metrics", {}).get("accuracy", 0) if result else 0
        embed = {
            "title": f"✅ Skill Development Complete: {skill_name}",
            "description": f"Final accuracy: {final_accuracy * 100:.1f}%",
            "color": 0x2ECC71,  # Green
            "fields": [
                {
                    "name": "Iterations",
                    "value": str(result.get("iterations_completed", 0)) if result else "N/A",
                    "inline": True,
                },
                {
                    "name": "Stop Reason",
                    "value": result.get("stop_reason", "Unknown") if result else "N/A",
                    "inline": True,
                },
            ],
        }
    elif event == "failed":
        embed = {
            "title": f"❌ Skill Development Failed: {skill_name}",
            "description": error or "Unknown error",
            "color": 0xE74C3C,  # Red
            "fields": [],
        }
    else:
        embed = {
            "title": f"📝 Skill Update: {skill_name}",
            "description": f"Event: {event}",
            "color": 0x9B59B6,  # Purple
            "fields": [],
        }

    try:
        response = await discord_client.send_embed(
            channel_name=channel,
            embed=embed,
        )
        return {"sent": True, "message_id": response.get("message_id")}
    except Exception as e:
        logger.warning(f"Failed to send Discord notification: {e}")
        return {"sent": False, "error": str(e)}
