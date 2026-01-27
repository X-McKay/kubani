"""Detect if a new skill overlaps with existing skills.

This capability analyzes whether a proposed skill would duplicate or
significantly overlap with skills already in the registry.
"""

import json
import re
from typing import Any

from ..models import OverlapResult
from ..protocols import LLMClient

# =============================================================================
# Prompts
# =============================================================================

SYSTEM_PROMPT = """You are a skill analyst. Analyze whether skills overlap based on their functionality. Always respond with valid JSON."""

DETECT_OVERLAP_TEMPLATE = """Analyze whether this new skill overlaps with any existing skills.

NEW SKILL DESCRIPTION:
{description}

EXISTING SKILLS:
{skills_text}

Consider skills as overlapping if they:
- Address the same problem domain
- Would be triggered by similar scenarios
- Provide redundant functionality

Recommend "merge" if the new skill could enhance an existing one.
Recommend "abort" if the new skill is essentially a duplicate.
Recommend "proceed" if the skill is sufficiently distinct.

Respond with JSON:
{{
    "has_overlap": true/false,
    "confidence": 0.0-1.0,
    "overlapping_skills": ["skill-name"],
    "reasoning": "Explanation",
    "recommendation": "proceed|merge|abort"
}}"""


# =============================================================================
# Main Function
# =============================================================================


async def detect_skill_overlap(
    client: LLMClient,
    description: str,
    existing_skills: list[dict[str, Any]],
) -> OverlapResult:
    """
    Detect if a new skill overlaps with existing skills.

    Uses an LLM to analyze whether a proposed skill would duplicate
    or significantly overlap with skills already in the registry.

    Args:
        client: LLM client for analysis
        description: Description of the new skill being proposed
        existing_skills: List of existing skills with name and description

    Returns:
        OverlapResult indicating overlap status and recommendation
    """
    # Fast path: no existing skills means no overlap
    if not existing_skills:
        return OverlapResult(
            has_overlap=False,
            confidence=1.0,
            overlapping_skills=[],
            reasoning="No existing skills to compare against",
            recommendation="proceed",
        )

    skills_text = "\n".join(
        f"- {s['name']}: {s.get('description', 'No description')}" for s in existing_skills
    )

    user_prompt = DETECT_OVERLAP_TEMPLATE.format(
        description=description,
        skills_text=skills_text,
    )

    response = await client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,  # Low temperature for consistent analysis
        max_tokens=2000,
    )

    return _parse_overlap_response(response)


# =============================================================================
# Helper Functions
# =============================================================================


def _parse_overlap_response(response: str) -> OverlapResult:
    """Parse LLM response into an OverlapResult."""
    # Strip thinking tags if present
    response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
    response = response.strip()

    # Extract JSON from markdown code blocks
    if "```json" in response:
        json_start = response.find("```json") + 7
        json_end = response.find("```", json_start)
        response = response[json_start:json_end].strip()
    elif "```" in response:
        json_start = response.find("```") + 3
        json_end = response.find("```", json_start)
        response = response[json_start:json_end].strip()

    # Parse JSON
    try:
        data = json.loads(response)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in LLM response: {e}. Response: {response[:200]}") from e

    # Validate and normalize recommendation
    recommendation = data.get("recommendation", "proceed")
    if recommendation not in ("proceed", "merge", "abort"):
        recommendation = "proceed"  # Default to safe option

    return OverlapResult(
        has_overlap=data.get("has_overlap", False),
        confidence=float(data.get("confidence", 0.0)),
        overlapping_skills=data.get("overlapping_skills", []),
        reasoning=data.get("reasoning", ""),
        recommendation=recommendation,
    )


__all__ = ["detect_skill_overlap"]
