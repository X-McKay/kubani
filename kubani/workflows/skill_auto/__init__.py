"""Skill Auto workflow - autonomous skill development.

This package provides workflows and models for autonomous skill development:
- SkillAutoWorkflow: Main workflow for skill creation and improvement
- PromoteWorkflow: Child workflow for promoting skills to production
- Various data models and scoring functions

The workflow orchestrates: create -> eval -> improve -> repeat until quality goals met.
"""

# Public API - Models
from .models import (
    EvalMetrics,
    IterationContext,
    IterationResult,
    OverlapResult,
    PromoteWorkflowInput,
    PromoteWorkflowResult,
    SkillAutoInput,
    SkillAutoResult,
    SkillAutoState,
    SkillOverlapError,
    SkillVersion,
    compute_score,
    detect_regression,
    is_plateau,
    should_continue_iteration,
)

# Public API - Workflows (from temporal module)
from .temporal.promote import PromoteWorkflow
from .temporal.worker import create_worker
from .temporal.workflow import SkillAutoWorkflow

__all__ = [
    # Workflows
    "SkillAutoWorkflow",
    "PromoteWorkflow",
    "create_worker",
    # Models
    "EvalMetrics",
    "IterationContext",
    "IterationResult",
    "OverlapResult",
    "PromoteWorkflowInput",
    "PromoteWorkflowResult",
    "SkillAutoInput",
    "SkillAutoResult",
    "SkillAutoState",
    "SkillOverlapError",
    "SkillVersion",
    # Scoring functions
    "compute_score",
    "detect_regression",
    "is_plateau",
    "should_continue_iteration",
]
