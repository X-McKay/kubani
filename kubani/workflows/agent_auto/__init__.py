# kubani/workflows/agent_auto/__init__.py
"""agent_auto workflow - Automated agent generation and evaluation.

This workflow provides services for:
- Drafting new agents based on requirements
- Evaluating agents against test cases
- Analyzing failures and suggesting improvements
- Orchestrating the full agent creation lifecycle via Temporal
"""

from .domain import (
    AgentAutoInput,
    AgentAutoResult,
    AgentAutoState,
    AgentAutoStatus,
    AgentEvaluationResult,
    AgentSpec,
    AgentTestCase,
    ImprovementSuggestions,
)
from .services import DraftingService, EvaluationService
from .workflow import AgentAutoWorkflow

__all__ = [
    # Domain models
    "AgentSpec",
    "AgentTestCase",
    "AgentEvaluationResult",
    "ImprovementSuggestions",
    "AgentAutoState",
    "AgentAutoInput",
    "AgentAutoResult",
    "AgentAutoStatus",
    # Services
    "DraftingService",
    "EvaluationService",
    # Workflow
    "AgentAutoWorkflow",
]
