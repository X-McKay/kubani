# agent_auto domain layer
"""Pure, testable domain logic for agent automation."""

from .models import (
    AgentAutoInput,
    AgentAutoResult,
    AgentAutoState,
    AgentAutoStatus,
    AgentEvaluationResult,
    AgentSpec,
    AgentTestCase,
    ImprovementSuggestions,
)

__all__ = [
    "AgentSpec",
    "AgentTestCase",
    "AgentEvaluationResult",
    "ImprovementSuggestions",
    "AgentAutoState",
    "AgentAutoInput",
    "AgentAutoResult",
    "AgentAutoStatus",
]
