"""Pure functions for analyzing agent requirements and evaluation results."""

import ast
import re
from pathlib import Path
from typing import Any

import yaml

from ..models import AgentEvaluationResult, AgentSpec, ImprovementSuggestions


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


# =============================================================================
# SkillsOrchestrator Pattern Validation
# =============================================================================


def validate_skills_orchestrator_pattern(agent_path: str | Path) -> tuple[bool, list[str], list[str]]:
    """
    Validate that an agent follows the SkillsOrchestrator pattern.

    Checks:
    - Agent inherits from SkillsOrchestrator
    - Has SKILLS_DOMAIN and SKILLS_CATEGORY class attributes
    - config.yaml exists and matches class attributes
    - Skills can be discovered with the configured domain/category

    Args:
        agent_path: Path to agent directory

    Returns:
        Tuple of (is_valid, errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []
    agent_dir = Path(agent_path)

    if not agent_dir.is_dir():
        errors.append(f"Not a directory: {agent_path}")
        return False, errors, warnings

    # Check agent.py exists
    agent_file = agent_dir / "agent.py"
    if not agent_file.exists():
        errors.append("Missing agent.py")
        return False, errors, warnings

    content = agent_file.read_text()

    # Parse the Python file to extract class info
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        errors.append(f"Syntax error in agent.py: {e}")
        return False, errors, warnings

    # Find the agent class
    agent_class = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check if it inherits from SkillsOrchestrator
            for base in node.bases:
                base_name = ""
                if isinstance(base, ast.Name):
                    base_name = base.id
                elif isinstance(base, ast.Attribute):
                    base_name = base.attr
                if base_name == "SkillsOrchestrator":
                    agent_class = node
                    break

    if not agent_class:
        # Check if SkillsOrchestrator is imported but not used
        if "SkillsOrchestrator" in content:
            errors.append("SkillsOrchestrator is imported but agent class does not inherit from it")
        else:
            errors.append("Agent does not inherit from SkillsOrchestrator")
        return False, errors, warnings

    # Extract class attributes
    class_attrs = _extract_class_attributes(agent_class)
    skills_domain = class_attrs.get("SKILLS_DOMAIN")
    skills_category = class_attrs.get("SKILLS_CATEGORY")

    if skills_domain is None:
        errors.append("Missing SKILLS_DOMAIN class attribute")
    if skills_category is None:
        errors.append("Missing SKILLS_CATEGORY class attribute")

    # Check config.yaml exists and matches
    config_file = agent_dir / "config.yaml"
    if not config_file.exists():
        warnings.append("Missing config.yaml")
    else:
        try:
            config = yaml.safe_load(config_file.read_text())
            config_errors, config_warnings = _validate_config_consistency(
                config, skills_domain, skills_category
            )
            errors.extend(config_errors)
            warnings.extend(config_warnings)
        except yaml.YAMLError as e:
            errors.append(f"Invalid config.yaml: {e}")

    return len(errors) == 0, errors, warnings


def _extract_class_attributes(class_node: ast.ClassDef) -> dict[str, Any]:
    """Extract class-level attribute assignments from an AST ClassDef."""
    attrs = {}
    for node in class_node.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            # Annotated assignment: SKILLS_DOMAIN: str = "news"
            attr_name = node.target.id
            if node.value:
                attrs[attr_name] = _extract_value(node.value)
        elif isinstance(node, ast.Assign):
            # Simple assignment: SKILLS_DOMAIN = "news"
            for target in node.targets:
                if isinstance(target, ast.Name):
                    attrs[target.id] = _extract_value(node.value)
    return attrs


def _extract_value(node: ast.expr) -> Any:
    """Extract a literal value from an AST node."""
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Str):  # Python 3.7 compatibility
        return node.s
    elif isinstance(node, ast.Num):  # Python 3.7 compatibility
        return node.n
    elif isinstance(node, ast.List):
        return [_extract_value(elt) for elt in node.elts]
    elif isinstance(node, ast.Dict):
        return {
            _extract_value(k): _extract_value(v)
            for k, v in zip(node.keys, node.values)
            if k is not None
        }
    return None


def _validate_config_consistency(
    config: dict[str, Any],
    skills_domain: str | None,
    skills_category: str | None,
) -> tuple[list[str], list[str]]:
    """Validate config.yaml is consistent with class attributes."""
    errors: list[str] = []
    warnings: list[str] = []

    # Check skills section exists
    skills_config = config.get("skills", {})

    # Check domain matches
    config_domain = skills_config.get("domain")
    if config_domain and skills_domain and config_domain != skills_domain:
        errors.append(
            f"config.yaml skills.domain '{config_domain}' doesn't match "
            f"class SKILLS_DOMAIN '{skills_domain}'"
        )

    # Check category matches
    config_category = skills_config.get("category")
    if config_category and skills_category and config_category != skills_category:
        errors.append(
            f"config.yaml skills.category '{config_category}' doesn't match "
            f"class SKILLS_CATEGORY '{skills_category}'"
        )

    # Check allowed patterns are consistent
    allowed = skills_config.get("allowed", [])
    if allowed and skills_domain and skills_category:
        expected_pattern = f"{skills_domain}/{skills_category}/*"
        if allowed and expected_pattern not in allowed and f"{skills_domain}/*" not in allowed:
            warnings.append(
                f"skills.allowed patterns {allowed} may not include skills from "
                f"domain={skills_domain}, category={skills_category}"
            )

    # Check required fields
    required_fields = ["name", "version", "description"]
    for field in required_fields:
        if field not in config:
            warnings.append(f"config.yaml missing recommended field: {field}")

    return errors, warnings


def detect_embedded_business_logic(agent_path: str | Path) -> tuple[list[str], list[str]]:
    """
    Detect potential embedded business logic that should be in skills.

    Looks for patterns that indicate business logic is embedded in the agent
    rather than delegated to skills.

    Args:
        agent_path: Path to agent directory

    Returns:
        Tuple of (potential_issues, recommendations)
    """
    issues: list[str] = []
    recommendations: list[str] = []
    agent_dir = Path(agent_path)

    agent_file = agent_dir / "agent.py"
    if not agent_file.exists():
        return issues, recommendations

    content = agent_file.read_text()
    lines = content.split("\n")

    # Check for hardcoded lists that could be configuration or skills
    hardcoded_patterns = [
        (r"keywords?\s*=\s*\[", "Hardcoded keyword lists should be in skills or config"),
        (r"patterns?\s*=\s*\{", "Hardcoded pattern dicts should be in skills or config"),
        (r"threshold\s*=\s*\d+", "Hardcoded thresholds should be in config.yaml"),
        (r"categories?\s*=\s*\[", "Hardcoded categories could be skill-driven"),
    ]

    for pattern, recommendation in hardcoded_patterns:
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line, re.IGNORECASE):
                issues.append(f"Line {i}: {line.strip()[:80]}")
                if recommendation not in recommendations:
                    recommendations.append(recommendation)

    # Check for large method bodies (>50 lines) that could be skills
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                method_lines = node.end_lineno - node.lineno if hasattr(node, 'end_lineno') else 0
                if method_lines > 50:
                    issues.append(f"Method '{node.name}' is {method_lines} lines - consider extracting to skill")
    except SyntaxError:
        pass

    # Check for direct API calls that should go through MCP
    api_patterns = [
        (r"requests\.(get|post|put|delete)", "Direct HTTP calls should use MCP servers"),
        (r"httpx\.(get|post|put|delete|AsyncClient)", "Direct HTTP calls should use MCP servers"),
        (r"redis\.", "Direct Redis calls should use MCP Memory server"),
    ]

    for pattern, recommendation in api_patterns:
        if re.search(pattern, content):
            if recommendation not in recommendations:
                recommendations.append(recommendation)

    return issues, recommendations
