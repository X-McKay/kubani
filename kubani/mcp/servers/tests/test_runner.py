"""
Tests for the MCP test runner CLI.

Tests CLI argument parsing, test discovery logic, and output formatting.
Requirements: 2.1
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from kubani.mcp.servers.test_runner import (
    MCPTestRunner,
    TestType,
    TestStatus,
    TestResult,
)


class TestMCPTestRunner:
    """Tests for MCPTestRunner class."""

    def test_initialization(self):
        """Test that test runner initializes correctly."""
        runner = MCPTestRunner(verbose=False)
        assert runner.verbose is False
        assert runner.results == []

        runner_verbose = MCPTestRunner(verbose=True)
        assert runner_verbose.verbose is True

    def test_servers_list(self):
        """Test that all expected servers are in the list."""
        expected_servers = ["discord", "memory", "temporal", "qdrant", "skills"]
        assert MCPTestRunner.SERVERS == expected_servers

    def test_base_dir_exists(self):
        """Test that base directory is correctly set."""
        runner = MCPTestRunner()
        assert runner.BASE_DIR.exists()
        assert runner.BASE_DIR.name == "servers"

    def test_discover_tests_contract(self):
        """Test discovery of contract tests."""
        runner = MCPTestRunner()

        # Contract tests should be in shared tests directory
        test_path = runner.discover_tests("discord", TestType.CONTRACT)
        assert test_path is not None
        assert test_path.name == "test_contract_completeness.py"
        assert test_path.exists()

    def test_discover_tests_integration(self):
        """Test discovery of integration tests."""
        runner = MCPTestRunner()

        # Integration tests should be in server-specific tests directory
        test_path = runner.discover_tests("discord", TestType.INTEGRATION)
        if test_path:  # May not exist for all servers
            assert test_path.name == "test_integration.py"

    def test_discover_tests_unit(self):
        """Test discovery of unit tests."""
        runner = MCPTestRunner()

        # Unit tests should return the tests directory
        test_path = runner.discover_tests("discord", TestType.UNIT)
        if test_path:
            assert test_path.is_dir()
            assert test_path.name == "tests"

    def test_discover_tests_invalid_server(self):
        """Test that discovery returns None for invalid server."""
        runner = MCPTestRunner()

        test_path = runner.discover_tests("nonexistent", TestType.UNIT)
        assert test_path is None

    @patch("subprocess.run")
    def test_run_pytest_success(self, mock_run):
        """Test running pytest with successful result."""
        runner = MCPTestRunner()

        # Mock successful pytest run
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="test_example.py::test_something PASSED",
            stderr="",
        )

        test_path = Path("/fake/path/tests")
        result = runner.run_pytest("discord", test_path, TestType.UNIT)

        assert result.server == "discord"
        assert result.test_type == TestType.UNIT
        assert result.status == TestStatus.PASSED
        assert result.exit_code == 0
        assert "PASSED" in result.output

    @patch("subprocess.run")
    def test_run_pytest_failure(self, mock_run):
        """Test running pytest with failed result."""
        runner = MCPTestRunner()

        # Mock failed pytest run
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="test_example.py::test_something FAILED",
            stderr="AssertionError: expected True",
        )

        test_path = Path("/fake/path/tests")
        result = runner.run_pytest("discord", test_path, TestType.UNIT)

        assert result.server == "discord"
        assert result.test_type == TestType.UNIT
        assert result.status == TestStatus.FAILED
        assert result.exit_code == 1
        assert "FAILED" in result.output

    @patch("subprocess.run")
    def test_run_pytest_timeout(self, mock_run):
        """Test handling of pytest timeout."""
        runner = MCPTestRunner()

        # Mock timeout
        from subprocess import TimeoutExpired

        mock_run.side_effect = TimeoutExpired("pytest", 300)

        test_path = Path("/fake/path/tests")
        result = runner.run_pytest("discord", test_path, TestType.UNIT)

        assert result.status == TestStatus.ERROR
        assert "timed out" in result.output.lower()
        assert result.exit_code == -1

    @patch("subprocess.run")
    def test_run_pytest_exception(self, mock_run):
        """Test handling of pytest exception."""
        runner = MCPTestRunner()

        # Mock exception
        mock_run.side_effect = Exception("Something went wrong")

        test_path = Path("/fake/path/tests")
        result = runner.run_pytest("discord", test_path, TestType.UNIT)

        assert result.status == TestStatus.ERROR
        assert "Error running tests" in result.output
        assert result.exit_code == -1

    def test_print_summary_all_passed(self, capsys):
        """Test summary output when all tests pass."""
        runner = MCPTestRunner()

        # Add some passing results
        runner.results = [
            TestResult("discord", TestType.UNIT, TestStatus.PASSED, "", 0),
            TestResult("discord", TestType.CONTRACT, TestStatus.PASSED, "", 0),
            TestResult("memory", TestType.UNIT, TestStatus.PASSED, "", 0),
        ]

        exit_code = runner.print_summary()
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "TEST SUMMARY" in captured.out
        assert "discord:" in captured.out
        assert "memory:" in captured.out
        assert "Passed: 3" in captured.out
        assert "Failed: 0" in captured.out

    def test_print_summary_with_failures(self, capsys):
        """Test summary output when tests fail."""
        runner = MCPTestRunner()

        # Add mixed results
        runner.results = [
            TestResult("discord", TestType.UNIT, TestStatus.PASSED, "", 0),
            TestResult("discord", TestType.CONTRACT, TestStatus.FAILED, "", 1),
            TestResult("memory", TestType.UNIT, TestStatus.SKIPPED, "", 0),
        ]

        exit_code = runner.print_summary()
        assert exit_code == 1  # Should return 1 when there are failures

        captured = capsys.readouterr()
        assert "Passed: 1" in captured.out
        assert "Failed: 1" in captured.out
        assert "Skipped: 1" in captured.out

    def test_print_summary_with_errors(self, capsys):
        """Test summary output when tests have errors."""
        runner = MCPTestRunner()

        # Add error result
        runner.results = [
            TestResult("discord", TestType.UNIT, TestStatus.ERROR, "", -1),
        ]

        exit_code = runner.print_summary()
        assert exit_code == 1  # Should return 1 when there are errors

        captured = capsys.readouterr()
        assert "Errors: 1" in captured.out

    @patch.object(MCPTestRunner, "run_server_tests")
    def test_run_all_servers(self, mock_run_server_tests):
        """Test running tests for all servers."""
        runner = MCPTestRunner()

        # Mock server test results
        mock_run_server_tests.return_value = [
            TestResult("discord", TestType.UNIT, TestStatus.PASSED, "", 0)
        ]

        exit_code = runner.run(run_all=True)

        # Should call run_server_tests for each server
        assert mock_run_server_tests.call_count == len(MCPTestRunner.SERVERS)

    @patch.object(MCPTestRunner, "run_server_tests")
    def test_run_specific_server(self, mock_run_server_tests):
        """Test running tests for specific server."""
        runner = MCPTestRunner()

        # Mock server test results
        mock_run_server_tests.return_value = [
            TestResult("discord", TestType.UNIT, TestStatus.PASSED, "", 0)
        ]

        exit_code = runner.run(servers=["discord"])

        # Should call run_server_tests once for discord
        assert mock_run_server_tests.call_count == 1
        mock_run_server_tests.assert_called_with("discord", [
            TestType.UNIT,
            TestType.CONTRACT,
            TestType.INTEGRATION,
            TestType.PROPERTY,
        ])

    def test_run_invalid_server(self):
        """Test that invalid server name returns error."""
        runner = MCPTestRunner()

        exit_code = runner.run(servers=["invalid_server"])
        assert exit_code == 1

    @patch.object(MCPTestRunner, "run_deployment_tests")
    def test_run_deployment_tests(self, mock_run_deployment_tests):
        """Test running deployment tests."""
        runner = MCPTestRunner()

        # Mock deployment test result
        mock_run_deployment_tests.return_value = TestResult(
            "all", TestType.DEPLOYED, TestStatus.PASSED, "", 0
        )

        exit_code = runner.run(run_deployed=True)

        # Should call run_deployment_tests
        mock_run_deployment_tests.assert_called_once()

    @patch.object(MCPTestRunner, "run_server_tests")
    def test_run_specific_test_types(self, mock_run_server_tests):
        """Test running specific test types."""
        runner = MCPTestRunner()

        # Mock server test results
        mock_run_server_tests.return_value = [
            TestResult("discord", TestType.UNIT, TestStatus.PASSED, "", 0)
        ]

        exit_code = runner.run(
            servers=["discord"],
            test_types=[TestType.UNIT, TestType.CONTRACT],
        )

        # Should call run_server_tests with specific test types
        mock_run_server_tests.assert_called_with(
            "discord", [TestType.UNIT, TestType.CONTRACT]
        )


class TestCLIArgumentParsing:
    """Tests for CLI argument parsing."""

    @patch("sys.argv", ["test_runner.py", "--all"])
    @patch.object(MCPTestRunner, "run")
    def test_cli_all_flag(self, mock_run):
        """Test --all flag parsing."""
        from kubani.mcp.servers.test_runner import main

        mock_run.return_value = 0

        try:
            main()
        except SystemExit:
            pass

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["run_all"] is True

    @patch("sys.argv", ["test_runner.py", "--server", "discord"])
    @patch.object(MCPTestRunner, "run")
    def test_cli_server_flag(self, mock_run):
        """Test --server flag parsing."""
        from kubani.mcp.servers.test_runner import main

        mock_run.return_value = 0

        try:
            main()
        except SystemExit:
            pass

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["servers"] == ["discord"]

    @patch("sys.argv", ["test_runner.py", "--server", "discord", "--unit"])
    @patch.object(MCPTestRunner, "run")
    def test_cli_unit_flag(self, mock_run):
        """Test --unit flag parsing."""
        from kubani.mcp.servers.test_runner import main

        mock_run.return_value = 0

        try:
            main()
        except SystemExit:
            pass

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert TestType.UNIT in call_kwargs["test_types"]

    @patch("sys.argv", ["test_runner.py", "--deployed"])
    @patch.object(MCPTestRunner, "run")
    def test_cli_deployed_flag(self, mock_run):
        """Test --deployed flag parsing."""
        from kubani.mcp.servers.test_runner import main

        mock_run.return_value = 0

        try:
            main()
        except SystemExit:
            pass

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["run_deployed"] is True

    @patch("sys.argv", ["test_runner.py", "--server", "discord", "--verbose"])
    def test_cli_verbose_flag(self):
        """Test --verbose flag parsing."""
        from kubani.mcp.servers.test_runner import main

        # Check that runner is created with verbose=True
        with patch("kubani.mcp.servers.test_runner.MCPTestRunner") as mock_runner_class:
            mock_runner_instance = MagicMock()
            mock_runner_instance.run.return_value = 0
            mock_runner_class.return_value = mock_runner_instance
            # Mock the SERVERS class attribute
            mock_runner_class.SERVERS = ["discord", "memory", "temporal", "qdrant", "skills"]

            try:
                main()
            except SystemExit:
                pass

            # Verify MCPTestRunner was created with verbose=True
            mock_runner_class.assert_called_once_with(verbose=True)


class TestOutputFormatting:
    """Tests for output formatting."""

    def test_test_result_dataclass(self):
        """Test TestResult dataclass creation."""
        result = TestResult(
            server="discord",
            test_type=TestType.UNIT,
            status=TestStatus.PASSED,
            output="test output",
            exit_code=0,
        )

        assert result.server == "discord"
        assert result.test_type == TestType.UNIT
        assert result.status == TestStatus.PASSED
        assert result.output == "test output"
        assert result.exit_code == 0

    def test_test_status_enum(self):
        """Test TestStatus enum values."""
        assert TestStatus.PASSED.value == "passed"
        assert TestStatus.FAILED.value == "failed"
        assert TestStatus.SKIPPED.value == "skipped"
        assert TestStatus.ERROR.value == "error"

    def test_test_type_enum(self):
        """Test TestType enum values."""
        assert TestType.UNIT.value == "unit"
        assert TestType.CONTRACT.value == "contract"
        assert TestType.INTEGRATION.value == "integration"
        assert TestType.PROPERTY.value == "property"
        assert TestType.DEPLOYED.value == "deployed"
        assert TestType.ALL.value == "all"
