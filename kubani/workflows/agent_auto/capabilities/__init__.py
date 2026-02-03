"""Business logic capabilities for agent_auto."""

from .analysis import (
    analyze_agent_requirements,
    analyze_evaluation_failures,
    detect_embedded_business_logic,
    validate_skills_orchestrator_pattern,
)
from .draft_agent import DraftingService
from .draft_test_cases import draft_agent_test_cases
from .evaluate_agent import EvaluationService
from .generation import generate_agent_config, generate_agent_prompt
from .metrics import calculate_skill_precision, calculate_skill_recall

__all__ = [
    # Analysis
    "analyze_agent_requirements",
    "analyze_evaluation_failures",
    # Validation
    "validate_skills_orchestrator_pattern",
    "detect_embedded_business_logic",
    # Drafting
    "DraftingService",
    # Test Cases
    "draft_agent_test_cases",
    # Evaluation
    "EvaluationService",
    # Generation
    "generate_agent_config",
    "generate_agent_prompt",
    # Metrics
    "calculate_skill_precision",
    "calculate_skill_recall",
]
