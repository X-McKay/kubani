# agent_auto domain layer
"""Pure, testable domain logic for agent automation."""

from .models import (
    AgentAutoState,
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
]
