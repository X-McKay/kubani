"""Evaluation configuration for multi-configuration skill evaluation.

This module defines the configuration structures for running skill evaluations
across multiple LLM configurations (model size, thinking mode, etc.).

Uses kubani.framework.config for endpoint URLs, allowing environment-specific
configuration via config/default.yaml, config/local.yaml, etc.
"""

from dataclasses import dataclass, field

from kubani.framework.config import get_config


@dataclass
class EvalConfiguration:
    """Configuration for a single evaluation run.

    Defines the LLM settings to use for evaluating a skill, including
    model selection, endpoint, and thinking mode.
    """

    name: str
    """Short identifier for this configuration (e.g., 'large-thinking')."""

    display_name: str
    """Human-readable name for display (e.g., 'Large Model (Thinking)')."""

    model: str
    """Model name/path to use."""

    base_url: str
    """Base URL for the LLM API endpoint."""

    enable_thinking: bool
    """Whether to enable thinking mode for reasoning models."""

    timeout: int = 300
    """Request timeout in seconds."""

    description: str = ""
    """Optional description of this configuration's characteristics."""

    def __post_init__(self):
        """Set default description if not provided."""
        if not self.description:
            thinking_desc = "with extended reasoning" if self.enable_thinking else "direct response"
            self.description = f"{self.model} {thinking_desc}"


@dataclass
class EvalMode:
    """Defines an evaluation mode with its configurations."""

    name: str
    """Mode name (e.g., 'quick', 'full')."""

    description: str
    """Human-readable description of the mode."""

    configurations: list[EvalConfiguration]
    """List of configurations to run in this mode."""


def _get_endpoints() -> tuple[str, str, str, str]:
    """Get LLM endpoints and models from framework config.

    Returns:
        Tuple of (large_url, large_model, fast_url, fast_model)
    """
    config = get_config()

    # Primary LLM endpoint (large model)
    large_url = config.llm.api_url
    large_model = config.llm.model

    # Fast/small model endpoint - use same URL but different model if not configured separately
    # TODO: Add llm_fast config section when we have separate fast model endpoint
    fast_url = large_url
    fast_model = "Qwen/Qwen3-0.6B"  # Default fast model

    return large_url, large_model, fast_url, fast_model


def get_default_configurations() -> list[EvalConfiguration]:
    """Get the default set of evaluation configurations for full mode.

    Returns:
        List of 4 configurations:
        - Large model with thinking enabled
        - Large model with thinking disabled
        - Small model with thinking enabled
        - Small model with thinking disabled
    """
    large_url, large_model, fast_url, fast_model = _get_endpoints()

    return [
        EvalConfiguration(
            name="large-thinking",
            display_name="Large + Thinking",
            model=large_model,
            base_url=large_url,
            enable_thinking=True,
            timeout=300,
            description=f"{large_model} with extended reasoning - highest accuracy, highest cost",
        ),
        EvalConfiguration(
            name="large-no-think",
            display_name="Large - No Think",
            model=large_model,
            base_url=large_url,
            enable_thinking=False,
            timeout=240,
            description=f"{large_model} direct response - good accuracy, lower latency",
        ),
        EvalConfiguration(
            name="small-thinking",
            display_name="Small + Thinking",
            model=fast_model,
            base_url=fast_url,
            enable_thinking=True,
            timeout=180,
            description=f"{fast_model} with reasoning - moderate accuracy, fast",
        ),
        EvalConfiguration(
            name="small-no-think",
            display_name="Small - No Think",
            model=fast_model,
            base_url=fast_url,
            enable_thinking=False,
            timeout=120,
            description=f"{fast_model} direct response - lowest cost, fastest",
        ),
    ]


def get_quick_configuration(
    base_url: str | None = None,
    model: str | None = None,
) -> EvalConfiguration:
    """Get the default configuration for quick mode.

    Args:
        base_url: Optional custom base URL (defaults to large model endpoint)
        model: Optional custom model name (defaults to large model)

    Returns:
        Single configuration using large model with thinking enabled.
    """
    large_url, large_model, _, _ = _get_endpoints()

    return EvalConfiguration(
        name="default",
        display_name="Default (Large + Thinking)",
        model=model or large_model,
        base_url=base_url or large_url,
        enable_thinking=True,
        timeout=300,
    )


def get_eval_mode(mode_name: str) -> EvalMode:
    """Get an evaluation mode by name.

    Args:
        mode_name: Name of the mode ('quick' or 'full')

    Returns:
        EvalMode for the specified mode

    Raises:
        ValueError: If mode name is not recognized
    """
    if mode_name == "quick":
        return EvalMode(
            name="quick",
            description="Single evaluation with large model (thinking enabled)",
            configurations=[get_quick_configuration()],
        )
    elif mode_name == "full":
        return EvalMode(
            name="full",
            description="Compare 4 configurations: large/small models with/without thinking",
            configurations=get_default_configurations(),
        )
    else:
        raise ValueError(f"Unknown eval mode '{mode_name}'. Valid modes: quick, full")


@dataclass
class ConfigurationResult:
    """Result from evaluating a skill with a single configuration."""

    config: EvalConfiguration
    """The configuration used for this evaluation."""

    metrics: dict
    """Evaluation metrics (accuracy, latency, tokens, etc.)."""

    test_results: list[dict]
    """Per-test results with assertions and critic feedback."""

    error: str | None = None
    """Error message if evaluation failed."""

    @property
    def accuracy(self) -> float:
        """Get accuracy percentage."""
        return self.metrics.get("accuracy", 0.0)

    @property
    def avg_latency_ms(self) -> float:
        """Get average latency in milliseconds."""
        return self.metrics.get("avg_latency_ms", 0.0)

    @property
    def avg_tokens(self) -> float:
        """Get average tokens per test."""
        return self.metrics.get("avg_tokens_per_test", {}).get("total", 0.0)

    @property
    def total_tokens(self) -> int:
        """Get total tokens used."""
        return self.metrics.get("total_tokens", {}).get("total", 0)

    @property
    def tests_passed(self) -> int:
        """Get number of tests passed."""
        return self.metrics.get("tests_passed", 0)

    @property
    def tests_total(self) -> int:
        """Get total number of tests."""
        return self.metrics.get("tests_total", 0)


@dataclass
class ComparisonReport:
    """Aggregated comparison report from multi-configuration evaluation."""

    skill_name: str
    """Name of the evaluated skill."""

    mode: str
    """Evaluation mode used ('quick' or 'full')."""

    timestamp: str
    """ISO timestamp of the evaluation."""

    results: dict[str, ConfigurationResult] = field(default_factory=dict)
    """Config name -> ConfigurationResult mapping."""

    summary: str = ""
    """LLM-generated analysis summary."""

    @property
    def configurations(self) -> list[str]:
        """Get list of configuration names."""
        return list(self.results.keys())

    def get_result(self, config_name: str) -> ConfigurationResult | None:
        """Get result for a specific configuration."""
        return self.results.get(config_name)

    def get_comparison_matrix(self) -> dict[str, dict[str, float | str]]:
        """Generate a comparison matrix of metrics across configurations.

        Returns:
            Dict with metrics as keys, each containing config -> value mapping.
        """
        matrix: dict[str, dict[str, float | str]] = {
            "accuracy": {},
            "avg_latency_ms": {},
            "avg_tokens": {},
            "total_tokens": {},
            "tests_passed": {},
        }

        for config_name, result in self.results.items():
            if result.error:
                continue
            matrix["accuracy"][config_name] = result.accuracy
            matrix["avg_latency_ms"][config_name] = result.avg_latency_ms
            matrix["avg_tokens"][config_name] = result.avg_tokens
            matrix["total_tokens"][config_name] = result.total_tokens
            matrix["tests_passed"][config_name] = f"{result.tests_passed}/{result.tests_total}"

        return matrix

    def get_rankings(self) -> dict[str, list[str]]:
        """Rank configurations by each metric.

        Returns:
            Dict with metric name -> list of config names (best to worst).
        """
        rankings: dict[str, list[str]] = {}

        # Higher is better for accuracy
        accuracy_sorted = sorted(
            [(name, r.accuracy) for name, r in self.results.items() if not r.error],
            key=lambda x: x[1],
            reverse=True,
        )
        rankings["accuracy"] = [name for name, _ in accuracy_sorted]

        # Lower is better for latency
        latency_sorted = sorted(
            [(name, r.avg_latency_ms) for name, r in self.results.items() if not r.error],
            key=lambda x: x[1],
        )
        rankings["latency"] = [name for name, _ in latency_sorted]

        # Lower is better for tokens (cost)
        tokens_sorted = sorted(
            [(name, r.avg_tokens) for name, r in self.results.items() if not r.error],
            key=lambda x: x[1],
        )
        rankings["tokens"] = [name for name, _ in tokens_sorted]

        return rankings

    def to_dict(self) -> dict:
        """Convert report to dictionary for JSON serialization."""
        return {
            "skill_name": self.skill_name,
            "mode": self.mode,
            "timestamp": self.timestamp,
            "configurations": {
                name: {
                    "config": {
                        "name": result.config.name,
                        "display_name": result.config.display_name,
                        "model": result.config.model,
                        "enable_thinking": result.config.enable_thinking,
                    },
                    "metrics": result.metrics,
                    "test_results": result.test_results,
                    "error": result.error,
                }
                for name, result in self.results.items()
            },
            "comparison": self.get_comparison_matrix(),
            "rankings": self.get_rankings(),
            "summary": self.summary,
        }
