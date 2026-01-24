"""Model comparison matrix for skill evaluation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from skill_dev_tools.llm import LLMClientWrapper
from skill_dev_tools.skill_executor import SkillExecutor
from skill_dev_tools.trace import ExecutionTrace

logger = logging.getLogger(__name__)


@dataclass
class MatrixConfig:
    """Configuration for a matrix dimension."""

    name: str
    values: list[Any]


@dataclass
class MatrixResult:
    """Result from a single matrix cell."""

    config: dict[str, Any]  # e.g., {"model": "opus", "thinking": True}
    trace: ExecutionTrace | None
    metrics: dict[str, Any]  # accuracy, latency, tokens


@dataclass
class MatrixReport:
    """Complete matrix evaluation report."""

    skill_name: str
    dimensions: list[str]
    results: list[MatrixResult]
    summary: dict[str, Any] = field(default_factory=dict)

    def to_table(self) -> list[list[str]]:
        """Convert to table format for display."""
        if not self.results:
            return []

        # Build header
        headers = list(self.results[0].config.keys()) + [
            "Accuracy",
            "Latency (ms)",
            "Tokens",
        ]

        rows = [headers]
        for r in self.results:
            row = list(str(v) for v in r.config.values())
            row.extend(
                [
                    f"{r.metrics.get('accuracy', 0):.1%}",
                    f"{r.metrics.get('latency_ms', 0):.0f}",
                    str(r.metrics.get("tokens", 0)),
                ]
            )
            rows.append(row)

        return rows


class ModelMatrix:
    """
    Run skill evaluations across a matrix of configurations.

    Enables comparison across:
    - Models (opus, haiku, local)
    - Settings (thinking on/off, temperature)
    - Any other configurable dimension

    Example:
        matrix = ModelMatrix(
            dimensions=[
                MatrixConfig("model", ["opus", "haiku"]),
                MatrixConfig("thinking", [True, False]),
            ]
        )
        report = await matrix.evaluate(executor, skill_name, suite)
    """

    # Known model configurations
    MODEL_CONFIGS = {
        "opus": {
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-opus-4-5-20251101",
        },
        "sonnet": {
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-sonnet-4-20250514",
        },
        "haiku": {
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-3-5-haiku-20241022",
        },
        "local": {
            "base_url": "https://llm.almckay.io/v1",
            "model": "nvidia/Qwen3-14B-FP4",
        },
    }

    def __init__(self, dimensions: list[MatrixConfig]):
        """
        Initialize matrix evaluator.

        Args:
            dimensions: List of matrix dimensions to evaluate
        """
        self.dimensions = dimensions

    @classmethod
    def from_string(cls, matrix_str: str) -> ModelMatrix:
        """
        Parse matrix from string format.

        Format: "dim1:val1,val2 dim2:val1,val2"
        Example: "model:opus,haiku thinking:on,off"
        """
        dimensions = []

        for part in matrix_str.split():
            if ":" not in part:
                continue

            name, values_str = part.split(":", 1)
            values = []

            for v in values_str.split(","):
                # Convert special values
                if v.lower() in ("on", "true", "yes"):
                    values.append(True)
                elif v.lower() in ("off", "false", "no"):
                    values.append(False)
                else:
                    values.append(v)

            dimensions.append(MatrixConfig(name, values))

        return cls(dimensions)

    def _generate_configs(self) -> list[dict[str, Any]]:
        """Generate all configuration combinations."""
        if not self.dimensions:
            return [{}]

        configs = [{}]
        for dim in self.dimensions:
            new_configs = []
            for config in configs:
                for value in dim.values:
                    new_config = config.copy()
                    new_config[dim.name] = value
                    new_configs.append(new_config)
            configs = new_configs

        return configs

    async def evaluate(
        self,
        skill_executor: SkillExecutor,
        skill_name: str,
        test_cases: list[dict[str, Any]],
    ) -> MatrixReport:
        """
        Run evaluation across all matrix configurations.

        Args:
            skill_executor: Base skill executor
            skill_name: Name of skill to evaluate
            test_cases: Test cases to run

        Returns:
            MatrixReport with all results
        """
        configs = self._generate_configs()
        results = []

        for config in configs:
            logger.info(f"Evaluating with config: {config}")

            # Create LLM client for this config
            llm_client = self._create_llm_client(config)

            # Create executor with this client
            executor = SkillExecutor(
                skills_dir=skill_executor.skills_dir,
                llm_client=llm_client,
            )

            # Run test cases
            case_results = []
            total_tokens = 0
            total_latency = 0
            passed = 0

            for case in test_cases:
                try:
                    trace = await executor.execute(
                        skill_name,
                        context=case.get("context", {}),
                    )

                    # Check assertions if present
                    case_passed = self._check_assertions(
                        trace.output,
                        case.get("expected", {}),
                    )

                    if case_passed:
                        passed += 1

                    total_tokens += trace.total_tokens
                    total_latency += trace.duration_ms or 0

                    case_results.append(trace)

                except Exception as e:
                    logger.error(f"Test case failed: {e}")

            # Close client
            if hasattr(llm_client, "close"):
                await llm_client.close()

            # Aggregate metrics
            metrics = {
                "accuracy": passed / len(test_cases) if test_cases else 0,
                "latency_ms": total_latency / len(test_cases) if test_cases else 0,
                "tokens": total_tokens,
                "passed": passed,
                "total": len(test_cases),
            }

            results.append(
                MatrixResult(
                    config=config,
                    trace=case_results[-1] if case_results else None,
                    metrics=metrics,
                )
            )

        return MatrixReport(
            skill_name=skill_name,
            dimensions=[d.name for d in self.dimensions],
            results=results,
        )

    def _create_llm_client(self, config: dict[str, Any]) -> LLMClientWrapper:
        """Create LLM client for a configuration."""
        # Get model config
        model_name = config.get("model", "local")
        model_config = self.MODEL_CONFIGS.get(model_name, self.MODEL_CONFIGS["local"])

        # Apply thinking setting
        enable_thinking = config.get("thinking", True)

        return LLMClientWrapper(
            base_url=model_config["base_url"],
            model=model_config["model"],
            enable_thinking=enable_thinking,
        )

    def _check_assertions(
        self,
        output: dict[str, Any],
        expected: dict[str, Any],
    ) -> bool:
        """Check if output matches expected assertions."""
        if not expected:
            return True

        for key, expected_value in expected.items():
            actual_value = output.get(key)

            if isinstance(expected_value, str) and expected_value.startswith("contains:"):
                # Check if value contains substring
                search = expected_value[9:]
                if search not in str(actual_value):
                    return False
            elif actual_value != expected_value:
                return False

        return True
