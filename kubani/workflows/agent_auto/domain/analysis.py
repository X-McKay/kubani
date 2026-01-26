# kubani/workflows/agent_auto/domain/analysis.py
"""Pure functions for analyzing agent requirements and evaluation results."""

from .models import AgentEvaluationResult, AgentSpec, ImprovementSuggestions


def analyze_agent_requirements(description: str) -> AgentSpec:
    """
    Analyzes a high-level description to produce a concrete agent specification.

    NOTE: In a real implementation, this would use an LLM, but for the domain layer,
    we can simulate it or use a simple keyword-based approach to keep it pure.
    For this task, a simple, rule-based implementation is sufficient.
    """
    # Example rule-based implementation
    required_skills = []
    if "monitor" in description.lower() and "kubernetes" in description.lower():
        required_skills.append("k8s/pod/list")

    # Extract skill references from description (skill/name pattern)
    import re

    skill_pattern = r"skill/[a-zA-Z0-9_/]+"
    found_skills = re.findall(skill_pattern, description)
    required_skills.extend(found_skills)

    # Derive a name from the description
    name = "generated_agent"
    if description:
        # Create a simple slug from the first few words
        words = description.split()[:3]
        name = "_".join(w.lower() for w in words if w.isalnum())
        if not name:
            name = "generated_agent"

    return AgentSpec(
        name=name,
        description=description,
        required_skills=required_skills,
        config_patterns={"skills.allowed": ["*"], "model": "gpt-4.1-mini"},
    )


def analyze_evaluation_failures(
    eval_result: AgentEvaluationResult,
) -> ImprovementSuggestions:
    """
    Analyzes an evaluation result to generate concrete suggestions for improvement.
    This is a pure function.
    """
    suggestions = ImprovementSuggestions(
        prompt_clarifications=[],
        skill_additions=[],
        skill_removals=[],
        config_changes={},
    )

    if eval_result.missing_skills:
        suggestions.prompt_clarifications.append(
            f"Consider adding logic to the prompt to handle cases requiring "
            f"these missing skills: {eval_result.missing_skills}"
        )
        suggestions.skill_additions.extend(eval_result.missing_skills)

    if eval_result.extraneous_skills:
        suggestions.prompt_clarifications.append(
            f"The prompt may be too ambiguous, causing incorrect invocation of "
            f"these skills: {eval_result.extraneous_skills}"
        )
        # We might not want to automatically remove skills, but suggest it.

    return suggestions
