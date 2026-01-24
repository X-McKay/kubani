"""Multi-configuration skill evaluation orchestrator.

This module provides the MultiConfigEvaluator class that orchestrates running
skill evaluations across multiple LLM configurations (model size, thinking mode).
Supports both sequential and parallel execution.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

from kubani_dev.eval_config import (
    ComparisonReport,
    ConfigurationResult,
    EvalConfiguration,
    get_default_configurations,
    get_quick_configuration,
)
from kubani_dev.llm_client import LLMClient
from kubani_dev.skill_evaluator_llm import SkillEvaluatorLLM

logger = logging.getLogger(__name__)


class MultiConfigEvaluator:
    """Orchestrates skill evaluation across multiple LLM configurations.

    This class manages running the same skill evaluation with different
    LLM configurations (e.g., large vs small model, thinking vs no-thinking)
    and aggregates the results for comparison.

    Attributes:
        configurations: List of evaluation configurations to run.
        parallel: Whether to run evaluations in parallel.
        max_workers: Maximum number of parallel workers.
    """

    def __init__(
        self,
        configurations: Optional[List[EvalConfiguration]] = None,
        parallel: bool = False,
        max_workers: int = 4,
    ):
        """Initialize the multi-configuration evaluator.

        Args:
            configurations: List of configurations to evaluate. Defaults to
                           the standard 4-configuration set for full mode.
            parallel: Whether to run evaluations concurrently.
            max_workers: Maximum number of parallel evaluation threads.
        """
        self.configurations = configurations or get_default_configurations()
        self.parallel = parallel
        self.max_workers = max_workers

    def evaluate(
        self,
        skill_dir: Path,
        verbose: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> ComparisonReport:
        """Evaluate a skill with all configurations.

        Args:
            skill_dir: Path to the skill directory containing SKILL.md and test_cases.yaml.
            verbose: Whether to print detailed output during evaluation.
            progress_callback: Optional callback(config_name, status) for progress updates.

        Returns:
            ComparisonReport containing results from all configurations.
        """
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        skill_name = skill_dir.name

        logger.info(
            f"Starting multi-config evaluation for '{skill_name}' "
            f"with {len(self.configurations)} configurations"
        )

        results = {}

        if self.parallel and len(self.configurations) > 1:
            results = self._run_parallel(skill_dir, verbose, progress_callback)
        else:
            results = self._run_sequential(skill_dir, verbose, progress_callback)

        # Build comparison report
        report = ComparisonReport(
            skill_name=skill_name,
            mode="full" if len(self.configurations) > 1 else "quick",
            timestamp=timestamp,
            results=results,
        )

        logger.info(f"Completed multi-config evaluation for '{skill_name}'")

        return report

    def _run_sequential(
        self,
        skill_dir: Path,
        verbose: bool,
        progress_callback: Optional[callable],
    ) -> dict:
        """Run evaluations sequentially.

        Args:
            skill_dir: Path to skill directory.
            verbose: Whether to print detailed output.
            progress_callback: Optional progress callback.

        Returns:
            Dict mapping config name to ConfigurationResult.
        """
        results = {}

        for i, config in enumerate(self.configurations, 1):
            logger.info(f"[{i}/{len(self.configurations)}] Evaluating with: {config.display_name}")

            if progress_callback:
                progress_callback(config.name, "running")

            try:
                result = self._evaluate_single_config(skill_dir, config, verbose)
                results[config.name] = result

                if progress_callback:
                    status = "completed" if not result.error else "failed"
                    progress_callback(config.name, status)

            except Exception as e:
                logger.error(f"Evaluation failed for {config.name}: {e}")
                results[config.name] = ConfigurationResult(
                    config=config,
                    metrics={},
                    test_results=[],
                    error=str(e),
                )
                if progress_callback:
                    progress_callback(config.name, "failed")

        return results

    def _run_parallel(
        self,
        skill_dir: Path,
        verbose: bool,
        progress_callback: Optional[callable],
    ) -> dict:
        """Run evaluations in parallel.

        Args:
            skill_dir: Path to skill directory.
            verbose: Whether to print detailed output (limited in parallel mode).
            progress_callback: Optional progress callback.

        Returns:
            Dict mapping config name to ConfigurationResult.
        """
        results = {}
        num_workers = min(self.max_workers, len(self.configurations))

        logger.info(
            f"Running {len(self.configurations)} evaluations in parallel with {num_workers} workers"
        )

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all evaluation tasks
            future_to_config = {
                executor.submit(
                    self._evaluate_single_config,
                    skill_dir,
                    config,
                    verbose=False,  # Disable verbose in parallel to avoid interleaved output
                ): config
                for config in self.configurations
            }

            if progress_callback:
                for config in self.configurations:
                    progress_callback(config.name, "queued")

            # Collect results as they complete
            for future in as_completed(future_to_config):
                config = future_to_config[future]

                if progress_callback:
                    progress_callback(config.name, "running")

                try:
                    result = future.result()
                    results[config.name] = result

                    if progress_callback:
                        status = "completed" if not result.error else "failed"
                        progress_callback(config.name, status)

                    logger.info(
                        f"Completed: {config.display_name} - Accuracy: {result.accuracy:.1f}%"
                    )

                except Exception as e:
                    logger.error(f"Evaluation failed for {config.name}: {e}")
                    results[config.name] = ConfigurationResult(
                        config=config,
                        metrics={},
                        test_results=[],
                        error=str(e),
                    )
                    if progress_callback:
                        progress_callback(config.name, "failed")

        return results

    def _evaluate_single_config(
        self,
        skill_dir: Path,
        config: EvalConfiguration,
        verbose: bool,
    ) -> ConfigurationResult:
        """Evaluate a skill with a single configuration.

        Args:
            skill_dir: Path to skill directory.
            config: The evaluation configuration to use.
            verbose: Whether to print detailed output.

        Returns:
            ConfigurationResult with evaluation metrics and test results.
        """
        # Create LLM client with this configuration
        llm_client = LLMClient(
            base_url=config.base_url,
            model=config.model,
            timeout=config.timeout,
            enable_thinking=config.enable_thinking,
        )

        # Create evaluator and run
        evaluator = SkillEvaluatorLLM(llm_client)

        try:
            eval_results = evaluator.evaluate_skill(skill_dir, verbose=verbose)

            return ConfigurationResult(
                config=config,
                metrics=eval_results.get("metrics", {}),
                test_results=eval_results.get("test_results", []),
            )

        except Exception as e:
            logger.error(f"Evaluation error with {config.name}: {e}")
            return ConfigurationResult(
                config=config,
                metrics={},
                test_results=[],
                error=str(e),
            )


def create_quick_evaluator(
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> MultiConfigEvaluator:
    """Create an evaluator for quick mode (single configuration).

    Args:
        base_url: Optional custom LLM endpoint URL.
        model: Optional custom model name.

    Returns:
        MultiConfigEvaluator configured for quick mode.
    """
    config = get_quick_configuration(base_url=base_url, model=model)
    return MultiConfigEvaluator(configurations=[config], parallel=False)


def create_full_evaluator(
    parallel: bool = True,
    max_workers: int = 4,
    custom_configs: Optional[List[EvalConfiguration]] = None,
) -> MultiConfigEvaluator:
    """Create an evaluator for full mode (4 configurations).

    Args:
        parallel: Whether to run evaluations in parallel.
        max_workers: Maximum number of parallel workers.
        custom_configs: Optional custom configurations (defaults to standard 4).

    Returns:
        MultiConfigEvaluator configured for full mode.
    """
    configs = custom_configs or get_default_configurations()
    return MultiConfigEvaluator(
        configurations=configs,
        parallel=parallel,
        max_workers=max_workers,
    )
