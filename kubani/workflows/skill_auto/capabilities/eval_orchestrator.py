"""Evaluation orchestrator for multi-configuration skill evaluation.

This module provides the EvalOrchestrator class that coordinates running
skill evaluations across multiple configurations (model sizes, thinking modes).

Supports two modes:
- quick: Single configuration evaluation using the default large model
- full: 4-configuration matrix evaluation (large/small x thinking on/off)

Usage:
    from kubani.workflows.skill_auto.capabilities.eval_orchestrator import EvalOrchestrator

    orchestrator = EvalOrchestrator()

    # Quick evaluation
    results = await orchestrator.run_quick(Path("kubani/skills/_development/my-skill"))

    # Full evaluation (parallel by default)
    results = await orchestrator.run_full(Path("kubani/skills/_development/my-skill"))
"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from kubani.workflows.skill_auto.capabilities.llm_evaluator import (
    EvaluationResult,
    SkillEvaluator,
)
from kubani.workflows.skill_auto.eval_config import (
    ComparisonReport,
    ConfigurationResult,
    EvalConfiguration,
    get_eval_mode,
    get_quick_configuration,
)

logger = logging.getLogger(__name__)


class EvalOrchestrator:
    """
    Orchestrate multi-configuration skill evaluation.

    Coordinates running evaluations across multiple LLM configurations,
    collecting results and generating comparison reports.
    """

    def __init__(
        self,
        enable_critic: bool = True,
        timeout_per_config: int = 600,
    ):
        """
        Initialize the orchestrator.

        Args:
            enable_critic: Whether to enable critic evaluation for semantic verification
            timeout_per_config: Maximum time (seconds) to wait for each configuration
        """
        self.enable_critic = enable_critic
        self.timeout_per_config = timeout_per_config

    async def run_quick(
        self,
        skill_path: Path,
        base_url: str | None = None,
        model: str | None = None,
    ) -> ConfigurationResult:
        """
        Run quick single-configuration evaluation.

        Uses the default large model with thinking enabled for fast feedback.

        Args:
            skill_path: Path to the skill directory
            base_url: Optional custom base URL
            model: Optional custom model name

        Returns:
            ConfigurationResult with evaluation metrics and test results
        """
        config = get_quick_configuration(base_url=base_url, model=model)
        logger.info(f"Running quick evaluation with config '{config.name}'")

        result = await self._run_with_config(skill_path, config)
        return result

    async def run_full(
        self,
        skill_path: Path,
        parallel: bool = True,
    ) -> ComparisonReport:
        """
        Run full 4-configuration matrix evaluation.

        Evaluates the skill with 4 configurations:
        - large-thinking: Large model with extended reasoning
        - large-no-think: Large model direct response
        - small-thinking: Small model with reasoning
        - small-no-think: Small model direct response

        Args:
            skill_path: Path to the skill directory
            parallel: Whether to run configurations in parallel (default True)

        Returns:
            ComparisonReport with results across all configurations
        """
        mode = get_eval_mode("full")
        configs = mode.configurations
        skill_name = skill_path.name

        logger.info(
            f"Running full evaluation with {len(configs)} configurations (parallel={parallel})"
        )

        results: dict[str, ConfigurationResult] = {}

        if parallel:
            # Run all configs concurrently
            tasks = [self._run_with_config(skill_path, config) for config in configs]
            config_results = await asyncio.gather(*tasks, return_exceptions=True)

            for config, result in zip(configs, config_results, strict=False):
                if isinstance(result, Exception):
                    logger.error(f"Config '{config.name}' failed: {result}")
                    results[config.name] = ConfigurationResult(
                        config=config,
                        metrics={},
                        test_results=[],
                        error=str(result),
                    )
                else:
                    results[config.name] = result
        else:
            # Run configs sequentially
            for config in configs:
                try:
                    result = await self._run_with_config(skill_path, config)
                    results[config.name] = result
                except Exception as e:
                    logger.error(f"Config '{config.name}' failed: {e}")
                    results[config.name] = ConfigurationResult(
                        config=config,
                        metrics={},
                        test_results=[],
                        error=str(e),
                    )

        # Build comparison report
        report = ComparisonReport(
            skill_name=skill_name,
            mode="full",
            timestamp=datetime.now(UTC).isoformat(),
            results=results,
        )

        logger.info(
            f"Full evaluation complete. Rankings by accuracy: {report.get_rankings().get('accuracy', [])}"
        )

        return report

    async def run_with_mode(
        self,
        skill_path: Path,
        mode: str = "quick",
        parallel: bool = True,
    ) -> ConfigurationResult | ComparisonReport:
        """
        Run evaluation with the specified mode.

        Args:
            skill_path: Path to the skill directory
            mode: Evaluation mode ("quick" or "full")
            parallel: Whether to run full mode in parallel

        Returns:
            ConfigurationResult for quick mode, ComparisonReport for full mode

        Raises:
            ValueError: If mode is invalid
        """
        if mode == "quick":
            return await self.run_quick(skill_path)
        elif mode == "full":
            return await self.run_full(skill_path, parallel=parallel)
        else:
            raise ValueError(f"Unknown evaluation mode: '{mode}'. Valid modes: quick, full")

    async def _run_with_config(
        self,
        skill_path: Path,
        config: EvalConfiguration,
    ) -> ConfigurationResult:
        """
        Run evaluation with a single configuration.

        Args:
            skill_path: Path to the skill directory
            config: Evaluation configuration

        Returns:
            ConfigurationResult with evaluation metrics
        """
        logger.info(f"Evaluating with config '{config.name}' ({config.model})")

        evaluator = SkillEvaluator(enable_critic=self.enable_critic)

        try:
            result: EvaluationResult = await asyncio.wait_for(
                evaluator.evaluate_skill(skill_path, config),
                timeout=self.timeout_per_config,
            )

            # Convert EvaluationResult to ConfigurationResult
            metrics = {
                "accuracy": result.accuracy,
                "avg_latency_ms": result.avg_latency_ms,
                "tests_passed": result.tests_passed,
                "tests_total": result.tests_total,
                "total_duration_ms": result.total_duration_ms,
                "avg_tokens_per_test": {"total": 0.0},  # Not available yet
                "total_tokens": result.tokens,
            }

            # Convert TestResult objects to dicts for serialization
            test_results = []
            for tr in result.test_results:
                test_dict = {
                    "name": tr.name,
                    "passed": tr.passed,
                    "latency_ms": tr.latency_ms,
                    "output": tr.output,
                    "error": tr.error,
                    "assertions_passed": [
                        {
                            "type": a.type,
                            "message": a.message,
                            "expected": a.expected,
                            "actual": a.actual,
                        }
                        for a in tr.assertions_passed
                    ],
                    "assertions_failed": [
                        {
                            "type": a.type,
                            "message": a.message,
                            "expected": a.expected,
                            "actual": a.actual,
                        }
                        for a in tr.assertions_failed
                    ],
                }
                if tr.critic_evaluation:
                    test_dict["critic_evaluation"] = tr.critic_evaluation
                test_results.append(test_dict)

            return ConfigurationResult(
                config=config,
                metrics=metrics,
                test_results=test_results,
                error=result.error,
            )

        except TimeoutError:
            logger.error(f"Config '{config.name}' timed out after {self.timeout_per_config}s")
            return ConfigurationResult(
                config=config,
                metrics={},
                test_results=[],
                error=f"Evaluation timed out after {self.timeout_per_config} seconds",
            )

        except Exception as e:
            logger.error(f"Config '{config.name}' failed: {e}")
            return ConfigurationResult(
                config=config,
                metrics={},
                test_results=[],
                error=str(e),
            )


# =============================================================================
# Convenience Functions
# =============================================================================


async def evaluate_quick(skill_path: Path | str) -> ConfigurationResult:
    """
    Convenience function for quick evaluation.

    Args:
        skill_path: Path to the skill directory

    Returns:
        ConfigurationResult with evaluation metrics
    """
    if isinstance(skill_path, str):
        skill_path = Path(skill_path)

    orchestrator = EvalOrchestrator()
    return await orchestrator.run_quick(skill_path)


async def evaluate_full(
    skill_path: Path | str,
    parallel: bool = True,
) -> ComparisonReport:
    """
    Convenience function for full evaluation.

    Args:
        skill_path: Path to the skill directory
        parallel: Whether to run configurations in parallel

    Returns:
        ComparisonReport with results across all configurations
    """
    if isinstance(skill_path, str):
        skill_path = Path(skill_path)

    orchestrator = EvalOrchestrator()
    return await orchestrator.run_full(skill_path, parallel=parallel)


__all__ = [
    "EvalOrchestrator",
    "evaluate_quick",
    "evaluate_full",
]
