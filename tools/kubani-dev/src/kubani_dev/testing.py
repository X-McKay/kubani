"""
Test Runner for Kubani Agents.

Provides integrated test execution with:
- pytest integration
- Coverage reporting
- Watch mode for continuous testing
- Filtering by test name
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TestRunner:
    """
    Runs tests for Kubani agents.

    Wraps pytest with additional features for agent testing.
    """

    def __init__(
        self,
        project_root: Path,
        agent_name: Optional[str] = None,
        coverage: bool = False,
        watch: bool = False,
        filter_pattern: Optional[str] = None,
    ):
        self.project_root = project_root
        self.agent_name = agent_name
        self.coverage = coverage
        self.watch = watch
        self.filter_pattern = filter_pattern

    def _get_test_paths(self) -> list[Path]:
        """Get paths to test directories."""
        if self.agent_name:
            agent_path = self.project_root / "agents" / self.agent_name / "tests"
            if agent_path.exists():
                return [agent_path]
            else:
                logger.warning(f"No tests found for {self.agent_name}")
                return []
        else:
            # All agent tests
            paths = []
            agents_dir = self.project_root / "agents"
            for agent_dir in agents_dir.iterdir():
                if agent_dir.is_dir():
                    test_dir = agent_dir / "tests"
                    if test_dir.exists():
                        paths.append(test_dir)
            return paths

    def _build_pytest_args(self) -> list[str]:
        """Build pytest command arguments."""
        args = ["python", "-m", "pytest"]

        # Add test paths
        for path in self._get_test_paths():
            args.append(str(path))

        # Verbosity
        args.append("-v")

        # Coverage
        if self.coverage:
            args.extend(["--cov", "--cov-report=term-missing"])

        # Filter
        if self.filter_pattern:
            args.extend(["-k", self.filter_pattern])

        # Color output
        args.append("--color=yes")

        return args

    def run(self) -> int:
        """Run tests and return exit code."""
        test_paths = self._get_test_paths()
        if not test_paths:
            logger.error("No test paths found")
            return 1

        args = self._build_pytest_args()
        logger.info(f"Running: {' '.join(args)}")

        if self.watch:
            return self._run_watch_mode(args)
        else:
            return self._run_once(args)

    def _run_once(self, args: list[str]) -> int:
        """Run tests once."""
        result = subprocess.run(args, cwd=self.project_root)
        return result.returncode

    def _run_watch_mode(self, args: list[str]) -> int:
        """Run tests in watch mode."""
        try:
            # Use pytest-watch if available
            watch_args = ["python", "-m", "pytest_watch", "--"] + args[3:]
            result = subprocess.run(watch_args, cwd=self.project_root)
            return result.returncode
        except FileNotFoundError:
            logger.warning("pytest-watch not installed, running once")
            return self._run_once(args)
