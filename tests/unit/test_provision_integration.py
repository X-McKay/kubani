"""Integration tests for provision command with ansible-runner."""

from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from cluster_manager.cli import app

runner = CliRunner()


@patch("ansible_runner.run")
def test_provision_executes_ansible_runner(mock_run):
    """Test that provision command calls ansible-runner with correct parameters."""
    # Setup mock
    mock_run_result = Mock()
    mock_run_result.status = "successful"
    mock_run_result.rc = 0
    mock_run_result.stats = {
        "test-node": {"ok": 5, "changed": 2, "unreachable": 0, "failures": 0, "skipped": 1}
    }
    mock_run.return_value = mock_run_result

    # Create temporary test files
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create playbook directory
        playbook_dir = Path(tmpdir) / "ansible" / "playbooks"
        playbook_dir.mkdir(parents=True)

        # Create a test playbook
        test_playbook = playbook_dir / "test.yml"
        test_playbook.write_text("---\n- hosts: all\n  tasks: []\n")

        # Create inventory file
        inventory_file = Path(tmpdir) / "inventory.yml"
        inventory_file.write_text("all:\n  hosts:\n    test:\n")

        # Change to temp directory
        original_dir = os.getcwd()
        try:
            os.chdir(tmpdir)

            # Run provision command
            result = runner.invoke(
                app, ["provision", "--playbook", "test.yml", "--inventory", str(inventory_file)]
            )

            # Verify ansible-runner was called
            assert mock_run.called
            call_args = mock_run.call_args[1]

            # Check parameters
            assert "playbook" in call_args
            assert "test.yml" in call_args["playbook"]
            assert "inventory" in call_args

            # Check result
            assert result.exit_code == 0
            assert "successful" in result.stdout.lower() or "completed" in result.stdout.lower()

        finally:
            os.chdir(original_dir)


@patch("ansible_runner.run")
def test_provision_with_check_mode(mock_run):
    """Test that provision command passes check mode to ansible-runner."""
    mock_run_result = Mock()
    mock_run_result.status = "successful"
    mock_run_result.rc = 0
    mock_run_result.stats = {}
    mock_run.return_value = mock_run_result

    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        playbook_dir = Path(tmpdir) / "ansible" / "playbooks"
        playbook_dir.mkdir(parents=True)
        test_playbook = playbook_dir / "test.yml"
        test_playbook.write_text("---\n- hosts: all\n  tasks: []\n")
        inventory_file = Path(tmpdir) / "inventory.yml"
        inventory_file.write_text("all:\n  hosts:\n    test:\n")

        original_dir = os.getcwd()
        try:
            os.chdir(tmpdir)
            runner.invoke(
                app,
                [
                    "provision",
                    "--playbook",
                    "test.yml",
                    "--inventory",
                    str(inventory_file),
                    "--check",
                ],
            )

            assert mock_run.called
            call_args = mock_run.call_args[1]
            assert "cmdline" in call_args
            assert "--check" in call_args["cmdline"]

        finally:
            os.chdir(original_dir)


@patch("ansible_runner.run")
def test_provision_with_tags(mock_run):
    """Test that provision command passes tags to ansible-runner."""
    mock_run_result = Mock()
    mock_run_result.status = "successful"
    mock_run_result.rc = 0
    mock_run_result.stats = {}
    mock_run.return_value = mock_run_result

    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        playbook_dir = Path(tmpdir) / "ansible" / "playbooks"
        playbook_dir.mkdir(parents=True)
        test_playbook = playbook_dir / "test.yml"
        test_playbook.write_text("---\n- hosts: all\n  tasks: []\n")
        inventory_file = Path(tmpdir) / "inventory.yml"
        inventory_file.write_text("all:\n  hosts:\n    test:\n")

        original_dir = os.getcwd()
        try:
            os.chdir(tmpdir)
            runner.invoke(
                app,
                [
                    "provision",
                    "--playbook",
                    "test.yml",
                    "--inventory",
                    str(inventory_file),
                    "--tags",
                    "k3s,networking",
                ],
            )

            assert mock_run.called
            call_args = mock_run.call_args[1]
            assert "tags" in call_args
            assert call_args["tags"] == "k3s,networking"

        finally:
            os.chdir(original_dir)


@patch("ansible_runner.run")
def test_provision_handles_failure(mock_run):
    """Test that provision command handles ansible-runner failures."""
    mock_run_result = Mock()
    mock_run_result.status = "failed"
    mock_run_result.rc = 2
    mock_run_result.stats = {}
    mock_run.return_value = mock_run_result

    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        playbook_dir = Path(tmpdir) / "ansible" / "playbooks"
        playbook_dir.mkdir(parents=True)
        test_playbook = playbook_dir / "test.yml"
        test_playbook.write_text("---\n- hosts: all\n  tasks: []\n")
        inventory_file = Path(tmpdir) / "inventory.yml"
        inventory_file.write_text("all:\n  hosts:\n    test:\n")

        original_dir = os.getcwd()
        try:
            os.chdir(tmpdir)
            result = runner.invoke(
                app, ["provision", "--playbook", "test.yml", "--inventory", str(inventory_file)]
            )

            # Should exit with error code
            assert result.exit_code != 0
            assert "failed" in result.stdout.lower()

        finally:
            os.chdir(original_dir)


# Note: Status command tests with kubernetes mocking are complex and would require
# extensive mocking of the kubernetes client library. The basic CLI tests already
# verify the command structure works correctly. Integration testing with a real
# cluster would be more valuable than complex mocking here.
