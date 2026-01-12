"""
Evaluation Suite Framework for Kubani Agents.

Provides YAML-based evaluation suite definitions with:
- Task definitions with inputs and success criteria
- Multiple grader types (code, model, human)
- Environment setup/teardown
- Results persistence and tracking

Based on best practices from Anthropic's agent evaluation guide.
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)


class GraderType(Enum):
    """Types of graders for evaluation."""

    CODE = "code"  # Programmatic assertions
    MODEL = "model"  # LLM-as-judge
    HUMAN = "human"  # Human review required


class TaskStatus(Enum):
    """Status of an evaluation task."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class Grader:
    """A grader for evaluating task outcomes."""

    type: GraderType
    name: str = ""
    # For code graders
    assertion: str = ""  # Python expression to evaluate
    # For model graders
    rubric: str = ""  # Evaluation rubric for LLM judge
    criteria: list[str] = field(default_factory=list)
    # For human graders
    instructions: str = ""
    # Common
    weight: float = 1.0
    required: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Grader":
        """Create a Grader from a dictionary."""
        grader_type = GraderType(data.get("type", "code"))
        return cls(
            type=grader_type,
            name=data.get("name", ""),
            assertion=data.get("assert", data.get("assertion", "")),
            rubric=data.get("rubric", ""),
            criteria=data.get("criteria", []),
            instructions=data.get("instructions", ""),
            weight=data.get("weight", 1.0),
            required=data.get("required", True),
        )


@dataclass
class EnvironmentSetup:
    """Environment setup/teardown configuration."""

    setup_commands: list[str] = field(default_factory=list)
    teardown_commands: list[str] = field(default_factory=list)
    fixtures: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 60

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnvironmentSetup":
        """Create EnvironmentSetup from a dictionary."""
        return cls(
            setup_commands=data.get("setup", []),
            teardown_commands=data.get("teardown", []),
            fixtures=data.get("fixtures", {}),
            timeout_seconds=data.get("timeout", 60),
        )


@dataclass
class EvalTask:
    """A single evaluation task."""

    name: str
    prompt: str
    description: str = ""
    graders: list[Grader] = field(default_factory=list)
    environment: EnvironmentSetup = field(default_factory=EnvironmentSetup)
    expected_tools: list[str] = field(default_factory=list)
    max_turns: int = 10
    timeout_seconds: int = 300
    trials: int = 3  # Number of trials for statistical significance
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalTask":
        """Create an EvalTask from a dictionary."""
        graders = [Grader.from_dict(g) for g in data.get("graders", [])]
        environment = EnvironmentSetup.from_dict(data.get("environment", {}))

        return cls(
            name=data["name"],
            prompt=data["prompt"],
            description=data.get("description", ""),
            graders=graders,
            environment=environment,
            expected_tools=data.get("expected_tools", []),
            max_turns=data.get("max_turns", 10),
            timeout_seconds=data.get("timeout", 300),
            trials=data.get("trials", 3),
            tags=data.get("tags", []),
        )

    def task_id(self) -> str:
        """Generate a unique task ID."""
        content = f"{self.name}:{self.prompt}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]


@dataclass
class EvalSuite:
    """A collection of evaluation tasks."""

    name: str
    description: str = ""
    agent: str = ""
    version: str = "1.0"
    tasks: list[EvalTask] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> "EvalSuite":
        """Load an evaluation suite from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        tasks = [EvalTask.from_dict(t) for t in data.get("tasks", [])]

        return cls(
            name=data.get("suite", data.get("name", path.stem)),
            description=data.get("description", ""),
            agent=data.get("agent", ""),
            version=data.get("version", "1.0"),
            tasks=tasks,
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )

    def suite_id(self) -> str:
        """Generate a unique suite ID."""
        content = f"{self.name}:{self.version}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]


@dataclass
class TrialResult:
    """Result of a single trial."""

    trial_number: int
    status: TaskStatus
    score: float = 0.0
    grader_results: dict[str, Any] = field(default_factory=dict)
    transcript: list[dict[str, Any]] = field(default_factory=list)
    outcome: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    token_usage: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trial_number": self.trial_number,
            "status": self.status.value,
            "score": self.score,
            "grader_results": self.grader_results,
            "transcript": self.transcript,
            "outcome": self.outcome,
            "duration_seconds": self.duration_seconds,
            "token_usage": self.token_usage,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class TaskResult:
    """Aggregated result for a task across all trials."""

    task: EvalTask
    trials: list[TrialResult] = field(default_factory=list)
    pass_at_k: float = 0.0  # At least one trial passed
    pass_all_k: float = 0.0  # All trials passed
    mean_score: float = 0.0
    std_score: float = 0.0
    mean_duration: float = 0.0
    total_tokens: int = 0

    def compute_metrics(self) -> None:
        """Compute aggregate metrics from trials."""
        if not self.trials:
            return

        scores = [t.score for t in self.trials]
        passed = [t.status == TaskStatus.PASSED for t in self.trials]

        self.pass_at_k = 1.0 if any(passed) else 0.0
        self.pass_all_k = 1.0 if all(passed) else 0.0
        self.mean_score = sum(scores) / len(scores)

        if len(scores) > 1:
            mean = self.mean_score
            variance = sum((s - mean) ** 2 for s in scores) / len(scores)
            self.std_score = variance**0.5
        else:
            self.std_score = 0.0

        self.mean_duration = sum(t.duration_seconds for t in self.trials) / len(self.trials)
        self.total_tokens = sum(
            sum(t.token_usage.values()) for t in self.trials if t.token_usage
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_name": self.task.name,
            "task_id": self.task.task_id(),
            "trials": [t.to_dict() for t in self.trials],
            "pass_at_k": self.pass_at_k,
            "pass_all_k": self.pass_all_k,
            "mean_score": self.mean_score,
            "std_score": self.std_score,
            "mean_duration": self.mean_duration,
            "total_tokens": self.total_tokens,
        }


@dataclass
class SuiteResult:
    """Result of running an evaluation suite."""

    suite: EvalSuite
    task_results: list[TaskResult] = field(default_factory=list)
    overall_pass_rate: float = 0.0
    overall_score: float = 0.0
    total_duration: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_metrics(self) -> None:
        """Compute overall metrics from task results."""
        if not self.task_results:
            return

        # Compute metrics for each task
        for tr in self.task_results:
            tr.compute_metrics()

        # Overall pass rate (using pass@k)
        passed = sum(1 for tr in self.task_results if tr.pass_at_k > 0)
        self.overall_pass_rate = passed / len(self.task_results)

        # Overall score (weighted average)
        total_weight = len(self.task_results)
        self.overall_score = sum(tr.mean_score for tr in self.task_results) / total_weight

        # Total duration
        self.total_duration = sum(tr.mean_duration for tr in self.task_results)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "suite_name": self.suite.name,
            "suite_id": self.suite.suite_id(),
            "version": self.suite.version,
            "task_results": [tr.to_dict() for tr in self.task_results],
            "overall_pass_rate": self.overall_pass_rate,
            "overall_score": self.overall_score,
            "total_duration": self.total_duration,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }

    def save(self, path: Path) -> None:
        """Save results to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


class EvalSuiteLoader:
    """Loads evaluation suites from the filesystem."""

    def __init__(self, evals_dir: Path):
        self.evals_dir = evals_dir

    def list_suites(self, agent: str | None = None) -> list[Path]:
        """List all available evaluation suites."""
        if not self.evals_dir.exists():
            return []

        suites = []
        for yaml_file in self.evals_dir.rglob("*.yaml"):
            if agent:
                # Filter by agent directory
                if agent in yaml_file.parts:
                    suites.append(yaml_file)
            else:
                suites.append(yaml_file)

        return sorted(suites)

    def load_suite(self, name: str) -> EvalSuite | None:
        """Load a suite by name."""
        # Try exact path first
        path = self.evals_dir / f"{name}.yaml"
        if path.exists():
            return EvalSuite.from_yaml(path)

        # Try searching
        for yaml_file in self.evals_dir.rglob(f"{name}.yaml"):
            return EvalSuite.from_yaml(yaml_file)

        # Try with subdirectory
        for yaml_file in self.evals_dir.rglob("*.yaml"):
            if name in str(yaml_file):
                return EvalSuite.from_yaml(yaml_file)

        return None

    def load_all(self, agent: str | None = None) -> list[EvalSuite]:
        """Load all suites, optionally filtered by agent."""
        suites = []
        for path in self.list_suites(agent):
            try:
                suites.append(EvalSuite.from_yaml(path))
            except Exception as e:
                logger.warning(f"Failed to load suite {path}: {e}")
        return suites
