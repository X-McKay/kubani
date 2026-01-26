# kubani/workflows/agent_auto/domain/models.py
"""Domain models for the agent_auto workflow."""

from typing import Any

from pydantic import BaseModel, Field


class AgentSpec(BaseModel):
    """Specification for the agent to be generated."""

    name: str
    description: str
    required_skills: list[str]
    config_patterns: dict[str, Any]


class AgentTestCase(BaseModel):
    """A single test case for evaluating an agent."""

    name: str
    prompt: str
    expected_skills: list[str]
    expected_output: str  # Or a more complex structure


class AgentEvaluationResult(BaseModel):
    """The result of a single agent evaluation run."""

    objective_accuracy: float = Field(..., description="Overall score based on test case outcomes.")
    skill_precision: float = Field(..., description="Of the skills invoked, how many were correct?")
    skill_recall: float = Field(..., description="Of the skills required, how many were invoked?")
    invoked_skills: list[str]
    missing_skills: list[str]
    extraneous_skills: list[str]
    failures: list[str] = Field(..., description="List of failed test case names.")


class ImprovementSuggestions(BaseModel):
    """Suggestions for how to improve an agent based on an evaluation."""

    prompt_clarifications: list[str]
    skill_additions: list[str]
    skill_removals: list[str]
    config_changes: dict[str, Any]


class AgentAutoState(BaseModel):
    """The complete state of the agent_auto workflow."""

    agent_name: str
    description: str
    agent_path: str | None = None
    test_cases: list[AgentTestCase] = []
    eval_history: list[AgentEvaluationResult] = []
    # ... other state fields ...
