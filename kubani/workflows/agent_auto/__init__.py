# kubani/workflows/agent_auto/__init__.py
"""agent_auto workflow - Automated agent generation and evaluation.

This workflow provides services for:
- Drafting new agents based on requirements
- Evaluating agents against test cases
- Analyzing failures and suggesting improvements
"""

from .domain import (
    AgentAutoState,
    AgentEvaluationResult,
    AgentSpec,
    AgentTestCase,
    ImprovementSuggestions,
)
from .services import DraftingService, EvaluationService

__all__ = [
    # Domain models
    "AgentSpec",
    "AgentTestCase",
    "AgentEvaluationResult",
    "ImprovementSuggestions",
    "AgentAutoState",
    # Services
    "DraftingService",
    "EvaluationService",
]
