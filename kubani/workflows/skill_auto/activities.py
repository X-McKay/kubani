"""Activities for the Skill Auto workflow."""

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
import yaml
from temporalio import activity

from kubani.framework.config import get_config

from .models import (
    EvalMetrics,
    OverlapResult,
    SkillOverlapError,
)

logger = logging.getLogger(__name__)


class SimpleLLMClient:
    """Simple LLM client using httpx for OpenAI-compatible APIs."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or "not-needed"  # Some local LLMs don't need a key
        self._client = httpx.AsyncClient(timeout=120.0)

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Send chat completion request."""
        headers = {"Authorization": f"Bearer {self.api_key}"}

        response = await self._client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()
        return {"content": data["choices"][0]["message"]["content"]}

    async def close(self) -> None:
        """Close the client."""
        await self._client.aclose()


def _get_llm_client(llm_client: Any | None = None) -> SimpleLLMClient:
    """Get or create an LLM client."""
    if llm_client is not None:
        return llm_client

    config = get_config()
    return SimpleLLMClient(
        base_url=config.llm.api_url,
        model=config.llm.model,
        api_key=config.llm.api_key,
    )


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


def _clean_llm_output(content: str) -> str:
    """Clean LLM output by removing thinking tags and code block markers."""
    content = content.strip()

    # Remove LLM thinking tags if present (e.g., <think>...</think>)
    content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)

    # Remove code block markers if present
    if content.startswith("```"):
        lines = content.split("\n")
        # Skip first line (```yaml or ```) and last line if it's closing ```
        if lines[-1].strip().startswith("```"):
            content = "\n".join(lines[1:-1])
        else:
            content = "\n".join(lines[1:])

    return content.strip()


@activity.defn
async def detect_skill_overlap(
    description: str,
    existing_skills: list[dict[str, Any]],
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

    client = _get_llm_client(llm_client)
    response = await client.chat(
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


@activity.defn
async def load_existing_skills(
    skills_path: str,
    include_development: bool = True,
) -> list[dict[str, Any]]:
    """
    Load metadata for all existing skills.

    Args:
        skills_path: Path to skills directory (as string for Temporal serialization)
        include_development: Whether to include _development skills

    Returns:
        List of skill metadata dicts with name, description, path, triggers
    """
    skills = []
    skills_path_obj = Path(skills_path)

    if not skills_path_obj.exists():
        return skills

    for skill_md in skills_path_obj.rglob("SKILL.md"):
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


@activity.defn
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

    client = _get_llm_client(llm_client)
    response = await client.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    return _extract_json(response["content"])


@activity.defn
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

Generate a YAML file with test_cases key containing 3-5 test cases that cover:
1. Happy path - typical successful usage
2. Edge case - boundary conditions or unusual inputs
3. Error handling - invalid inputs or failure scenarios

The YAML must have this structure:
test_cases:
  - name: snake_case_identifier
    description: What this test validates
    inputs:
      # Input values for the test
    expected:
      # Expected output fields (can be partial)
    assertions:
      - type: equals
        field: some_field
        description: Why this check matters

Assertion types available:
- equals: Exact value match
- contains: Substring or membership check
- exists: Field is present
- not_empty: Field has a truthy value
- type: Check field type (string, number, boolean, list, dict)

Respond with ONLY the YAML content, no code blocks or explanation."""

    client = _get_llm_client(llm_client)
    response = await client.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    content = _clean_llm_output(response["content"])

    # Ensure proper YAML structure with test_cases key
    try:
        data = yaml.safe_load(content)
        if isinstance(data, list):
            # Wrap list in test_cases key
            content = yaml.dump({"test_cases": data}, default_flow_style=False)
    except yaml.YAMLError:
        pass  # Return as-is if parsing fails

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


@activity.defn
async def write_skill_files(
    spec: dict[str, Any],
    test_cases: str,
    output_dir: str,
) -> dict[str, str]:
    """
    Write skill files to disk.

    Creates:
    - SKILL.md with frontmatter and content
    - test_cases.yaml with test definitions
    - metadata.json with creation info

    Args:
        spec: Skill specification
        test_cases: Test cases YAML content
        output_dir: Directory to write to (as string for Temporal serialization)

    Returns:
        Dict with path, content, and test_cases for workflow state
    """
    from datetime import datetime

    skill_name = spec["name"]
    output_dir_path = Path(output_dir)
    skill_dir = output_dir_path / skill_name
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

    # Return both path and content for workflow state
    return {
        "path": str(skill_dir),
        "content": skill_content,
        "test_cases": test_cases,
    }


@activity.defn
async def read_file_content(file_path: str) -> str:
    """
    Read file content as a string.

    Simple activity to read files, keeping I/O out of workflow code.

    Args:
        file_path: Path to file to read

    Returns:
        File content as string
    """
    return Path(file_path).read_text()


@activity.defn
async def write_file_content(file_path: str, content: str) -> None:
    """
    Write content to a file.

    Simple activity to write files, keeping I/O out of workflow code.

    Args:
        file_path: Path to file to write
        content: Content to write
    """
    Path(file_path).write_text(content)


@activity.defn
async def run_evaluation(
    skill_path: str,
    llm_client: Any,
    evaluator: Any | None = None,
) -> EvalMetrics:
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
    if evaluator is None:
        from kubani_dev.skill_evaluator_llm import SkillEvaluatorLLM

        evaluator = SkillEvaluatorLLM(llm_client=llm_client)

    # Convert str to Path for SkillEvaluatorLLM
    result = evaluator.evaluate_skill(Path(skill_path))

    return EvalMetrics(
        accuracy=result.get("accuracy", 0.0),
        latency_ms=result.get("average_latency_ms", 0.0),
        tests_passed=result.get("passed_tests", 0),
        tests_total=result.get("total_tests", 0),
        critic_confidence=result.get("average_critic_confidence", 0.0),
        tokens_prompt=result.get("total_tokens", {}).get("prompt", 0),
        tokens_completion=result.get("total_tokens", {}).get("completion", 0),
    )


@activity.defn
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


@activity.defn
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


# =============================================================================
# Phase 4: Promotion Activities
# =============================================================================


@activity.defn
async def check_promotion_overlap(
    skill_name: str,
    skill_description: str,
    production_skills: list[dict[str, str]],
    llm_client: Any,
    allow_overlap: bool = False,
) -> OverlapResult:
    """
    Check if a skill overlaps with production skills before promotion.

    Unlike detect_skill_overlap (which warns), this activity blocks promotion
    by raising SkillOverlapError when overlap is detected, unless allow_overlap=True.

    Args:
        skill_name: Name of the skill to promote
        skill_description: Description of the skill
        production_skills: List of production skills with name and description
        llm_client: LLM client for analysis
        allow_overlap: If True, return warning instead of raising

    Returns:
        OverlapResult if no overlap or allow_overlap=True

    Raises:
        SkillOverlapError: If overlap detected and allow_overlap=False
    """
    # No overlap possible if no production skills exist
    if not production_skills:
        return OverlapResult(
            has_overlap=False,
            confidence=1.0,
            overlapping_skills=[],
            reasoning="No production skills to compare against",
            recommendation="proceed",
        )

    # Check for overlap using LLM
    overlap_result = await detect_skill_overlap(
        description=skill_description,
        existing_skills=production_skills,
        llm_client=llm_client,
    )

    # If overlap detected and not allowed, raise error
    if overlap_result.has_overlap and not allow_overlap:
        raise SkillOverlapError(
            skill_name=skill_name,
            overlapping=overlap_result.overlapping_skills,
            reasoning=overlap_result.reasoning,
        )

    return overlap_result


@activity.defn
async def promote_skill(
    skill_path: str,
    target_category: str,
    skills_root: str,
) -> dict[str, Any]:
    """
    Promote a skill from _development to production location.

    Moves the skill directory, updates metadata status to 'production',
    and adds promotion timestamp.

    Args:
        skill_path: Path to the development skill directory
        target_category: Target category directory (e.g., "general", "k8s")
        skills_root: Root skills directory (e.g., "kubani/skills")

    Returns:
        Dict with success status, promoted_path, and any errors
    """
    import shutil
    from datetime import datetime
    from pathlib import Path

    try:
        source = Path(skill_path)
        skill_name = source.name
        target = Path(skills_root) / target_category / skill_name

        # Ensure target category exists
        target.parent.mkdir(parents=True, exist_ok=True)

        # Move skill directory
        shutil.move(str(source), str(target))

        # Update metadata
        metadata_path = target / "metadata.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
        else:
            metadata = {}

        metadata["status"] = "production"
        metadata["promoted_at"] = datetime.now().isoformat()
        metadata["category"] = target_category
        metadata_path.write_text(json.dumps(metadata, indent=2))

        return {
            "success": True,
            "promoted_path": str(target),
            "skill_name": skill_name,
        }

    except Exception as e:
        logger.error(f"Failed to promote skill: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@activity.defn
async def await_approval(
    channel_id: str,
    message_id: str,
    discord_client: Any,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """
    Wait for approval reaction on a Discord message.

    Adds checkmark (✅) and X (❌) reactions to the message, then waits
    for a user to react with one of them.

    Args:
        channel_id: Discord channel ID containing the message
        message_id: Message ID to watch for reactions
        discord_client: Discord MCP client
        timeout_seconds: How long to wait for reaction (default 5 minutes)

    Returns:
        Dict with approved/rejected/timeout status and reviewer info
    """
    CHECKMARK = "\u2705"  # ✅
    X_MARK = "\u274c"  # ❌

    try:
        # Add reaction options to message
        await discord_client.add_reaction(
            channel_id=channel_id,
            message_id=message_id,
            emoji=CHECKMARK,
        )
        await discord_client.add_reaction(
            channel_id=channel_id,
            message_id=message_id,
            emoji=X_MARK,
        )

        # Wait for reaction
        reaction = await discord_client.await_reaction(
            channel_id=channel_id,
            message_id=message_id,
            valid_emojis=[CHECKMARK, X_MARK],
            timeout_seconds=timeout_seconds,
        )

        if reaction is None:
            return {
                "approved": False,
                "rejected": False,
                "timeout": True,
            }

        emoji = reaction.get("emoji", "")
        reviewer = reaction.get("user_name", "unknown")

        if emoji == CHECKMARK:
            return {
                "approved": True,
                "rejected": False,
                "timeout": False,
                "reviewer": reviewer,
            }
        else:
            return {
                "approved": False,
                "rejected": True,
                "timeout": False,
                "reviewer": reviewer,
            }

    except Exception as e:
        logger.error(f"Error awaiting approval: {e}")
        return {
            "approved": False,
            "rejected": False,
            "timeout": False,
            "error": str(e),
        }


@activity.defn
async def sync_registry(
    skill_path: str,
    registry_client: Any,
) -> dict[str, Any]:
    """
    Sync a promoted skill to the registry.

    Reads skill metadata and registers it with the central registry.

    Args:
        skill_path: Path to the skill directory
        registry_client: Registry client for registration

    Returns:
        Dict with sync status
    """
    from pathlib import Path

    try:
        skill_dir = Path(skill_path)

        # Load skill metadata
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return {"synced": False, "error": "SKILL.md not found"}

        content = skill_md.read_text()

        # Parse frontmatter
        metadata = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                metadata = yaml.safe_load(parts[1])

        # Load additional metadata
        metadata_json = skill_dir / "metadata.json"
        if metadata_json.exists():
            extra = json.loads(metadata_json.read_text())
            metadata.update(extra)

        metadata["path"] = str(skill_dir)

        # Register with registry
        result = await registry_client.register_skill(metadata)

        return {
            "synced": True,
            "skill_id": result.get("skill_id"),
        }

    except Exception as e:
        logger.error(f"Failed to sync to registry: {e}")
        return {
            "synced": False,
            "error": str(e),
        }


@activity.defn
async def send_promotion_request(
    skill_name: str,
    skill_path: str,
    metrics: Any,  # EvalMetrics
    iterations: int,
    channel: str,
    discord_client: Any,
) -> dict[str, Any]:
    """
    Send a promotion request message to Discord.

    Creates a rich embed with skill metrics and instructions for approval.

    Args:
        skill_name: Name of the skill
        skill_path: Path to the skill
        metrics: Final evaluation metrics
        iterations: Number of iterations completed
        channel: Discord channel name
        discord_client: Discord MCP client

    Returns:
        Dict with sent status and message_id
    """
    accuracy_pct = f"{metrics.accuracy * 100:.1f}%" if metrics else "N/A"
    tests_info = f"{metrics.tests_passed}/{metrics.tests_total}" if metrics else "N/A"
    latency_info = f"{metrics.latency_ms:.0f}ms" if metrics else "N/A"

    embed = {
        "title": f"🔔 Promotion Request: {skill_name}",
        "description": (
            f"Skill **{skill_name}** is ready for promotion to production.\n\n"
            "React with ✅ to approve or ❌ to reject."
        ),
        "color": 0x9B59B6,  # Purple
        "fields": [
            {"name": "Accuracy", "value": accuracy_pct, "inline": True},
            {"name": "Tests Passed", "value": tests_info, "inline": True},
            {"name": "Latency", "value": latency_info, "inline": True},
            {"name": "Iterations", "value": str(iterations), "inline": True},
            {"name": "Path", "value": f"`{skill_path}`", "inline": False},
        ],
        "footer": {"text": "Skill Auto-Development | Awaiting approval"},
    }

    try:
        response = await discord_client.send_embed(
            channel_name=channel,
            embed=embed,
        )
        return {"sent": True, "message_id": response.get("message_id")}
    except Exception as e:
        logger.warning(f"Failed to send promotion request: {e}")
        return {"sent": False, "error": str(e)}


# =============================================================================
# Phase 5: Hardening Activities
# =============================================================================


@activity.defn
async def generate_harder_tests(
    skill_name: str,
    current_test_cases: str,
    metrics: Any,  # EvalMetrics
    failing_tests: list[dict[str, str]],
    llm_client: Any,
    count: int = 2,
) -> str:
    """
    Generate harder test cases targeting identified weaknesses.

    Used when plateau is detected to try to break through by
    adding more challenging tests.

    Args:
        skill_name: Name of the skill
        current_test_cases: Current test cases YAML
        metrics: Current evaluation metrics
        failing_tests: List of failing tests with name and reason
        llm_client: LLM client for generation
        count: Number of new tests to generate

    Returns:
        YAML string with new test cases
    """
    # Format failing tests for prompt
    failures_text = "\n".join(
        f"- {t['name']}: {t.get('reason', 'Unknown reason')}" for t in failing_tests
    )

    prompt = f"""Generate {count} harder test cases for the skill "{skill_name}".

CURRENT TEST CASES:
{current_test_cases}

CURRENT PERFORMANCE:
- Accuracy: {metrics.accuracy * 100:.1f}%
- Tests passed: {metrics.tests_passed}/{metrics.tests_total}

FAILING TESTS AND REASONS:
{failures_text}

Generate {count} NEW test cases that:
1. Target the identified weaknesses and failure patterns
2. Test edge cases and boundary conditions
3. Are harder than the current tests
4. Will help improve the skill's robustness

Each test should have:
- name: snake_case identifier starting with "edge_case_" or "stress_"
- description: What weakness this test targets
- inputs: Test input values
- expected: Expected output
- assertions: Validation checks

Respond with ONLY the YAML content for the new test cases, no code blocks."""

    client = _get_llm_client(llm_client)
    response = await client.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    content = _clean_llm_output(response["content"])
    return content


@activity.defn
async def revert_to_best_version(
    skill_path: str,
    best_version: Any,  # SkillVersion
) -> dict[str, Any]:
    """
    Revert skill files to a previous best version.

    Creates a backup of current content before reverting.

    Args:
        skill_path: Path to the skill directory
        best_version: SkillVersion object with content to restore

    Returns:
        Dict with revert status
    """
    from datetime import datetime
    from pathlib import Path

    try:
        skill_dir = Path(skill_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Backup current files
        skill_md = skill_dir / "SKILL.md"
        test_yaml = skill_dir / "test_cases.yaml"

        if skill_md.exists():
            backup_skill = skill_dir / f"SKILL.md.backup.{timestamp}"
            backup_skill.write_text(skill_md.read_text())

        if test_yaml.exists():
            backup_tests = skill_dir / f"test_cases.yaml.backup.{timestamp}"
            backup_tests.write_text(test_yaml.read_text())

        # Restore best version content
        skill_md.write_text(best_version.content)
        test_yaml.write_text(best_version.test_cases)

        return {
            "reverted": True,
            "reverted_to_iteration": best_version.iteration,
            "backup_timestamp": timestamp,
        }

    except Exception as e:
        logger.error(f"Failed to revert to best version: {e}")
        return {
            "reverted": False,
            "error": str(e),
        }


@activity.defn
async def save_iteration_result(
    skill_path: str,
    iteration_result: Any,  # IterationResult
) -> dict[str, Any]:
    """
    Save iteration result to a JSON file for auditing.

    Creates iteration_N.json in the skill directory.

    Args:
        skill_path: Path to the skill directory
        iteration_result: IterationResult to save

    Returns:
        Dict with save status
    """
    from datetime import datetime
    from pathlib import Path

    try:
        skill_dir = Path(skill_path)
        iteration_file = skill_dir / f"iteration_{iteration_result.iteration}.json"

        # Convert to dict, handling nested dataclasses
        data = {
            "iteration": iteration_result.iteration,
            "score": iteration_result.score,
            "improved": iteration_result.improved,
            "action": iteration_result.action,
            "error": iteration_result.error,
            "saved_at": datetime.now().isoformat(),
        }

        # Add metrics if available
        if iteration_result.metrics:
            data["metrics"] = {
                "accuracy": iteration_result.metrics.accuracy,
                "latency_ms": iteration_result.metrics.latency_ms,
                "tests_passed": iteration_result.metrics.tests_passed,
                "tests_total": iteration_result.metrics.tests_total,
                "critic_confidence": iteration_result.metrics.critic_confidence,
            }

        iteration_file.write_text(json.dumps(data, indent=2))

        return {
            "saved": True,
            "file": str(iteration_file),
        }

    except Exception as e:
        logger.error(f"Failed to save iteration result: {e}")
        return {
            "saved": False,
            "error": str(e),
        }


@activity.defn
async def load_iteration_history(
    skill_path: str,
) -> list[dict[str, Any]]:
    """
    Load all iteration history files from a skill directory.

    Args:
        skill_path: Path to the skill directory

    Returns:
        List of iteration result dicts, sorted by iteration number
    """
    from pathlib import Path

    try:
        skill_dir = Path(skill_path)
        history = []

        for iteration_file in skill_dir.glob("iteration_*.json"):
            try:
                data = json.loads(iteration_file.read_text())
                history.append(data)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Failed to load {iteration_file}: {e}")

        # Sort by iteration number
        history.sort(key=lambda x: x.get("iteration", 0))

        return history

    except Exception as e:
        logger.error(f"Failed to load iteration history: {e}")
        return []
