"""Unit tests for CLI cluster operations commands."""

from typer.testing import CliRunner

from cluster_manager.cli import app

runner = CliRunner()


def test_provision_help():
    """Test that provision command help works."""
    result = runner.invoke(app, ["provision", "--help"])
    assert result.exit_code == 0
    assert "Execute Ansible playbook" in result.stdout
    assert "--playbook" in result.stdout
    assert "--check" in result.stdout
    assert "--tags" in result.stdout


def test_provision_missing_playbook():
    """Test that provision fails gracefully with missing playbook."""
    result = runner.invoke(app, ["provision", "--playbook", "nonexistent.yml"])
    assert result.exit_code == 1
    assert "Playbook not found" in result.stdout


def test_provision_missing_inventory():
    """Test that provision fails gracefully with missing inventory."""
    result = runner.invoke(app, ["provision", "--inventory", "nonexistent.yml"])
    assert result.exit_code == 1
    assert "Inventory file not found" in result.stdout


def test_status_help():
    """Test that status command help works."""
    result = runner.invoke(app, ["status", "--help"])
    assert result.exit_code == 0
    assert "Show cluster status" in result.stdout
    assert "--pods" in result.stdout
    assert "--namespace" in result.stdout


def test_status_no_kubeconfig():
    """Test that status fails gracefully without kubeconfig."""
    result = runner.invoke(app, ["status"], env={"KUBECONFIG": "/nonexistent/config"})
    # Should fail with kubeconfig error
    assert result.exit_code == 1
    assert "kubeconfig" in result.stdout.lower() or "error" in result.stdout.lower()
