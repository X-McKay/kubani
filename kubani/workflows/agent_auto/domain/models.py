# kubani/workflows/agent_auto/domain/models.py
"""Domain models for the agent_auto workflow."""

from typing import Any, Literal

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


AgentAutoStatus = Literal[
    "pending",
    "drafting",
    "creating_skills",
    "writing_files",
    "improving",
    "publishing",
    "published",
    "failed",
    "finished_failed_to_meet_accuracy",
]


class AgentAutoInput(BaseModel):
    """Input for the AgentAutoWorkflow."""

    agent_name: str
    description: str
    test_cases: list[AgentTestCase] = Field(default_factory=list)
    max_iterations: int = 5
    target_accuracy: float = 0.80
    publish_options: dict[str, Any] = Field(default_factory=dict)
    notify: bool = True
    notify_channel: str = "agent-notifications"
    
    # Child workflow configuration for skill creation
    child_skill_max_iterations: int = Field(
        default=3,
        description="Maximum iterations for child SkillAutoWorkflow instances"
    )
    child_skill_target_accuracy: float = Field(
        default=0.70,
        description="Target accuracy for child SkillAutoWorkflow instances"
    )


class AgentAutoState(BaseModel):
    """The complete state of the agent_auto workflow."""

    agent_name: str
    description: str
    status: AgentAutoStatus = "pending"
    agent_path: str | None = None
    test_cases: list[AgentTestCase] = Field(default_factory=list)
    eval_history: list[AgentEvaluationResult] = Field(default_factory=list)
    iteration: int = 0
    error: str | None = None


class AgentAutoResult(BaseModel):
    """Final result of the AgentAutoWorkflow."""

    success: bool
    agent_path: str | None
    final_accuracy: float | None
    iterations_completed: int
    status: AgentAutoStatus
    error: str | None = None
