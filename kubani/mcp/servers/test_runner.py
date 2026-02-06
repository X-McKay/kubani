#!/usr/bin/env python3
"""
Unified test runner for MCP servers.

This CLI provides a standardized way to run all types of tests for MCP servers:
- Unit tests: Core business logic
- Contract tests: Tool interface validation
- Integration tests: Backend connectivity
- Property tests: Property-based testing
- Deployment tests: Post-deployment validation

Usage:
    # Run all tests for all servers
    python test_runner.py --all

    # Run tests for specific server
    python test_runner.py --server discord

    # Run specific test type
    python test_runner.py --server discord --unit
    python test_runner.py --server discord --integration
    python test_runner.py --server discord --contract

    # Run post-deployment tests
    python test_runner.py --deployed

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional


class TestType(Enum):
    """Types of tests that can be run."""

    UNIT = "unit"
    CONTRACT = "contract"
    INTEGRATION = "integration"
    PROPERTY = "property"
    COMPREHENSIVE = "comprehensive"
    DEPLOYED = "deployed"
    ALL = "all"


class TestStatus(Enum):
    """Test execution status."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestResult:
    """Result of a test execution."""

    server: str
    test_type: TestType
    status: TestStatus
    output: str
    exit_code: int


class MCPTestRunner:
    """Unified test runner for MCP servers."""

    # Available MCP servers
    SERVERS = ["discord", "memory", "temporal", "qdrant", "skills"]

    # Base directory for MCP servers
    BASE_DIR = Path(__file__).parent

    def __init__(self, verbose: bool = False):
        """
        Initialize test runner.

        Args:
            verbose: Enable verbose output
        """
        self.verbose = verbose
        self.results: List[TestResult] = []

    def discover_tests(self, server: str, test_type: TestType) -> Optional[Path]:
        """
        Discover test files for a server and test type.

        Args:
            server: Server name (discord, memory, etc.)
            test_type: Type of test to discover

        Returns:
            Path to test directory or file, or None if not found
        """
        server_dir = self.BASE_DIR / server

        if not server_dir.exists():
            return None

        tests_dir = server_dir / "tests"
        if not tests_dir.exists():
            return None

        # Map test types to test file patterns
        test_patterns = {
            TestType.UNIT: "test_*.py",
            TestType.CONTRACT: "../tests/test_contract_completeness.py",
            TestType.INTEGRATION: "test_integration.py",
            TestType.PROPERTY: "test_*.py",  # Property tests are mixed with unit tests
            TestType.COMPREHENSIVE: "test_comprehensive.py",
        }

        if test_type == TestType.CONTRACT:
            # Contract tests are in the shared tests directory
            contract_test = self.BASE_DIR / "tests" / "test_contract_completeness.py"
            return contract_test if contract_test.exists() else None

        if test_type == TestType.INTEGRATION:
            # Integration tests are in server-specific tests directory
            integration_test = tests_dir / "test_integration.py"
            return integration_test if integration_test.exists() else None

        if test_type == TestType.COMPREHENSIVE:
            # Comprehensive tests are in server-specific tests directory
            comprehensive_test = tests_dir / "test_comprehensive.py"
            return comprehensive_test if comprehensive_test.exists() else None

        # For unit and property tests, return the tests directory
        return tests_dir if tests_dir.exists() else None

    def run_pytest(
        self,
        server: str,
        test_path: Path,
        test_type: TestType,
        extra_args: Optional[List[str]] = None,
    ) -> TestResult:
        """
        Run pytest for a specific test path.

        Args:
            server: Server name
            test_path: Path to test file or directory
            test_type: Type of test being run
            extra_args: Additional pytest arguments

        Returns:
            TestResult with execution details
        """
        server_dir = self.BASE_DIR / server

        # Build pytest command
        cmd = ["uv", "run", "pytest", str(test_path), "-v"]

        # Add test type specific markers
        if test_type == TestType.INTEGRATION:
            cmd.extend(["-m", "integration"])
        elif test_type == TestType.PROPERTY:
            cmd.extend(["-k", "property"])
        elif test_type == TestType.CONTRACT:
            # Run contract tests for specific server
            cmd.extend(["-k", server])
        elif test_type == TestType.COMPREHENSIVE:
            cmd.extend(["-m", "comprehensive"])

        # Add extra arguments
        if extra_args:
            cmd.extend(extra_args)

        # Add coverage for unit tests
        if test_type == TestType.UNIT:
            cmd.extend(["--cov=src", "--cov-report=term-missing"])

        if self.verbose:
            print(f"Running: {' '.join(cmd)}")
            print(f"Working directory: {server_dir}")

        try:
            result = subprocess.run(
                cmd,
                cwd=server_dir,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            status = TestStatus.PASSED if result.returncode == 0 else TestStatus.FAILED
            output = result.stdout + result.stderr

            return TestResult(
                server=server,
                test_type=test_type,
                status=status,
                output=output,
                exit_code=result.returncode,
            )

        except subprocess.TimeoutExpired:
            return TestResult(
                server=server,
                test_type=test_type,
                status=TestStatus.ERROR,
                output="Test execution timed out after 5 minutes",
                exit_code=-1,
            )
        except Exception as e:
            return TestResult(
                server=server,
                test_type=test_type,
                status=TestStatus.ERROR,
                output=f"Error running tests: {str(e)}",
                exit_code=-1,
            )

    def run_server_tests(
        self, server: str, test_types: List[TestType]
    ) -> List[TestResult]:
        """
        Run tests for a specific server.

        Args:
            server: Server name
            test_types: List of test types to run

        Returns:
            List of test results
        """
        results = []

        for test_type in test_types:
            if test_type == TestType.DEPLOYED:
                # Deployment tests are handled separately
                continue

            print(f"\n{'='*60}")
            print(f"Running {test_type.value} tests for {server}")
            print(f"{'='*60}")

            test_path = self.discover_tests(server, test_type)

            if test_path is None:
                print(f"⚠️  No {test_type.value} tests found for {server}")
                results.append(
                    TestResult(
                        server=server,
                        test_type=test_type,
                        status=TestStatus.SKIPPED,
                        output=f"No {test_type.value} tests found",
                        exit_code=0,
                    )
                )
                continue

            result = self.run_pytest(server, test_path, test_type)
            results.append(result)

            # Print result
            status_icon = "✓" if result.status == TestStatus.PASSED else "✗"
            print(f"\n{status_icon} {test_type.value.upper()} tests: {result.status.value}")

            if self.verbose or result.status != TestStatus.PASSED:
                print("\nOutput:")
                print(result.output)

        return results

    def run_deployment_tests(self) -> TestResult:
        """
        Run post-deployment tests.

        Returns:
            TestResult for deployment tests
        """
        print(f"\n{'='*60}")
        print("Running post-deployment tests")
        print(f"{'='*60}")

        # Deployment tests are in the shared tests directory
        test_path = self.BASE_DIR / "tests" / "test_deployment.py"

        if not test_path.exists():
            print("⚠️  No deployment tests found")
            return TestResult(
                server="all",
                test_type=TestType.DEPLOYED,
                status=TestStatus.SKIPPED,
                output="No deployment tests found",
                exit_code=0,
            )

        cmd = ["uv", "run", "pytest", str(test_path), "-v", "-m", "deployment"]

        if self.verbose:
            print(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.BASE_DIR,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout for deployment tests
            )

            status = TestStatus.PASSED if result.returncode == 0 else TestStatus.FAILED
            output = result.stdout + result.stderr

            test_result = TestResult(
                server="all",
                test_type=TestType.DEPLOYED,
                status=status,
                output=output,
                exit_code=result.returncode,
            )

            status_icon = "✓" if status == TestStatus.PASSED else "✗"
            print(f"\n{status_icon} DEPLOYMENT tests: {status.value}")

            if self.verbose or status != TestStatus.PASSED:
                print("\nOutput:")
                print(output)

            return test_result

        except Exception as e:
            return TestResult(
                server="all",
                test_type=TestType.DEPLOYED,
                status=TestStatus.ERROR,
                output=f"Error running deployment tests: {str(e)}",
                exit_code=-1,
            )

    def print_summary(self):
        """Print test execution summary."""
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print(f"{'='*60}\n")

        # Group results by server
        servers = {}
        for result in self.results:
            if result.server not in servers:
                servers[result.server] = []
            servers[result.server].append(result)

        # Print results by server
        for server, results in sorted(servers.items()):
            print(f"{server}:")
            for result in results:
                status_icon = {
                    TestStatus.PASSED: "✓",
                    TestStatus.FAILED: "✗",
                    TestStatus.SKIPPED: "⊘",
                    TestStatus.ERROR: "⚠",
                }[result.status]

                print(f"  {status_icon} {result.test_type.value:12} {result.status.value}")

        # Print overall statistics
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in self.results if r.status == TestStatus.FAILED)
        skipped = sum(1 for r in self.results if r.status == TestStatus.SKIPPED)
        errors = sum(1 for r in self.results if r.status == TestStatus.ERROR)

        print(f"\n{'='*60}")
        print(f"Total: {total} | Passed: {passed} | Failed: {failed} | Skipped: {skipped} | Errors: {errors}")
        print(f"{'='*60}\n")

        # Return exit code
        return 0 if failed == 0 and errors == 0 else 1

    def run(
        self,
        servers: Optional[List[str]] = None,
        test_types: Optional[List[TestType]] = None,
        run_all: bool = False,
        run_deployed: bool = False,
    ) -> int:
        """
        Run tests based on configuration.

        Args:
            servers: List of servers to test (None = all servers)
            test_types: List of test types to run (None = all types)
            run_all: Run all tests for all servers
            run_deployed: Run post-deployment tests

        Returns:
            Exit code (0 = success, 1 = failure)
        """
        # Handle deployment tests
        if run_deployed:
            result = self.run_deployment_tests()
            self.results.append(result)
            return self.print_summary()

        # Determine servers to test
        if run_all or servers is None:
            servers = self.SERVERS
        else:
            # Validate server names
            invalid = [s for s in servers if s not in self.SERVERS]
            if invalid:
                print(f"Error: Unknown servers: {', '.join(invalid)}")
                print(f"Available servers: {', '.join(self.SERVERS)}")
                return 1

        # Determine test types to run
        if test_types is None or TestType.ALL in test_types:
            test_types = [TestType.UNIT, TestType.CONTRACT, TestType.INTEGRATION, TestType.PROPERTY, TestType.COMPREHENSIVE]

        # Run tests for each server
        for server in servers:
            results = self.run_server_tests(server, test_types)
            self.results.extend(results)

        return self.print_summary()


def main():
    """Main entry point for test runner CLI."""
    parser = argparse.ArgumentParser(
        description="Unified test runner for MCP servers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests for all servers
  %(prog)s --all

  # Run tests for specific server
  %(prog)s --server discord

  # Run specific test type
  %(prog)s --server discord --unit
  %(prog)s --server discord --integration

  # Run multiple test types
  %(prog)s --server memory --unit --contract

  # Run post-deployment tests
  %(prog)s --deployed

  # Run with verbose output
  %(prog)s --server discord --unit --verbose
        """,
    )

    # Server selection
    parser.add_argument(
        "--server",
        "-s",
        action="append",
        choices=MCPTestRunner.SERVERS,
        help="Server to test (can be specified multiple times)",
    )

    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Run tests for all servers",
    )

    # Test type selection
    parser.add_argument(
        "--unit",
        "-u",
        action="store_true",
        help="Run unit tests only",
    )

    parser.add_argument(
        "--contract",
        "-c",
        action="store_true",
        help="Run contract tests only",
    )

    parser.add_argument(
        "--integration",
        "-i",
        action="store_true",
        help="Run integration tests only",
    )

    parser.add_argument(
        "--property",
        "-p",
        action="store_true",
        help="Run property-based tests only",
    )

    parser.add_argument(
        "--comprehensive",
        action="store_true",
        help="Run comprehensive pre-deployment tests only",
    )

    parser.add_argument(
        "--deployed",
        "-d",
        action="store_true",
        help="Run post-deployment tests",
    )

    # Output options
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.all and not args.server and not args.deployed:
        parser.error("Must specify --all, --server, or --deployed")

    # Determine test types
    test_types = []
    if args.unit:
        test_types.append(TestType.UNIT)
    if args.contract:
        test_types.append(TestType.CONTRACT)
    if args.integration:
        test_types.append(TestType.INTEGRATION)
    if args.property:
        test_types.append(TestType.PROPERTY)
    if args.comprehensive:
        test_types.append(TestType.COMPREHENSIVE)

    # If no test type specified, run all
    if not test_types and not args.deployed:
        test_types = [TestType.ALL]

    # Create and run test runner
    runner = MCPTestRunner(verbose=args.verbose)

    exit_code = runner.run(
        servers=args.server,
        test_types=test_types if test_types else None,
        run_all=args.all,
        run_deployed=args.deployed,
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
