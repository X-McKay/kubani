"""agent_auto workflow - Automated agent generation and evaluation.

This workflow provides capabilities for:
- Drafting new agents based on requirements
- Evaluating agents against test cases
- Analyzing failures and suggesting improvements
- Orchestrating the full agent creation lifecycle via Temporal
"""

from .capabilities import DraftingService, EvaluationService
from .models import (
    # Constants
    ACCURACY_WEIGHT,
    PLATEAU_THRESHOLD,
    PLATEAU_WINDOW,
    PRECISION_WEIGHT,
    RECALL_WEIGHT,
    REGRESSION_THRESHOLD,
    # Dataclasses
    AgentAutoInput,
    AgentAutoResult,
    AgentAutoState,
    AgentAutoStatus,
    AgentEvalMetrics,
    # Pydantic Models
    AgentEvaluationResult,
    AgentIterationResult,
    AgentSpec,
    AgentTestCase,
    AgentVersion,
    ContinueDecision,
    ImprovementSuggestions,
    IterationContext,
    # Scoring Functions
    compute_agent_score,
    detect_regression,
    is_plateau,
    # Decision Functions
    make_continue_decision,
    should_continue_iteration,
)
from .temporal import AgentAutoWorkflow

__all__ = [
    # Dataclasses
    "AgentEvalMetrics",
    "AgentVersion",
    "AgentIterationResult",
    "AgentAutoInput",
    "AgentAutoState",
    "AgentAutoResult",
    "IterationContext",
    "ContinueDecision",
    # Pydantic Models
    "AgentSpec",
    "AgentTestCase",
    "AgentEvaluationResult",
    "ImprovementSuggestions",
    # Type aliases
    "AgentAutoStatus",
    # Constants
    "ACCURACY_WEIGHT",
    "PRECISION_WEIGHT",
    "RECALL_WEIGHT",
    "PLATEAU_THRESHOLD",
    "PLATEAU_WINDOW",
    "REGRESSION_THRESHOLD",
    # Scoring Functions
    "compute_agent_score",
    "is_plateau",
    "detect_regression",
    # Decision Functions
    "should_continue_iteration",
    "make_continue_decision",
    # Capabilities
    "DraftingService",
    "EvaluationService",
    # Workflow
    "AgentAutoWorkflow",
]
