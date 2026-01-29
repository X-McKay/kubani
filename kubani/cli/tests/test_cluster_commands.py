"""Tests for cluster commands."""

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from kubani.cli.cli import app

runner = CliRunner()


class TestClusterDiscover:
    """Tests for cluster discover command."""

    @patch("kubani.cli.commands.cluster_impl.subprocess.run")
    def test_discover_shows_nodes(self, mock_run):
        """Test discover command shows tailscale nodes."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps(
                {
                    "Self": {
                        "HostName": "test-node",
                        "TailscaleIPs": ["100.64.0.1"],
                        "OS": "linux",
                    },
                    "Peer": {},
                }
            ),
            returncode=0,
        )

        result = runner.invoke(app, ["cluster", "discover"])

        assert result.exit_code == 0
        assert "test-node" in result.output

    @patch("kubani.cli.commands.cluster_impl.subprocess.run")
    def test_discover_handles_tailscale_error(self, mock_run):
        """Test discover handles tailscale errors gracefully."""
        mock_run.side_effect = FileNotFoundError()

        result = runner.invoke(app, ["cluster", "discover"])

        assert "Error" in result.output or "not found" in result.output

    @patch("kubani.cli.commands.cluster_impl.subprocess.run")
    def test_discover_shows_peers(self, mock_run):
        """Test discover shows peer nodes."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps(
                {
                    "Self": {
                        "HostName": "self-node",
                        "TailscaleIPs": ["100.64.0.1"],
                        "OS": "linux",
                    },
                    "Peer": {
                        "peer1": {
                            "HostName": "peer-node",
                            "TailscaleIPs": ["100.64.0.2"],
                            "OS": "linux",
                            "Online": True,
                        },
                    },
                }
            ),
            returncode=0,
        )

        result = runner.invoke(app, ["cluster", "discover"])

        assert result.exit_code == 0
        assert "self-node" in result.output
        assert "peer-node" in result.output


class TestClusterStatus:
    """Tests for cluster status command."""

    @patch("kubani.cli.commands.cluster_impl.subprocess.run")
    def test_status_shows_nodes(self, mock_run):
        """Test status command shows cluster nodes."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps(
                {
                    "items": [
                        {
                            "metadata": {
                                "name": "node1",
                                "creationTimestamp": "2024-01-01T00:00:00Z",
                                "labels": {"node-role.kubernetes.io/control-plane": ""},
                            },
                            "status": {
                                "conditions": [{"type": "Ready", "status": "True"}],
                                "nodeInfo": {"kubeletVersion": "v1.28.0"},
                            },
                        }
                    ]
                }
            ),
            returncode=0,
        )

        result = runner.invoke(app, ["cluster", "status"])

        assert result.exit_code == 0
        assert "node1" in result.output

    @patch("kubani.cli.commands.cluster_impl.subprocess.run")
    def test_status_handles_kubectl_error(self, mock_run):
        """Test status handles kubectl errors."""
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(1, "kubectl")

        result = runner.invoke(app, ["cluster", "status"])

        assert "Failed" in result.output or "Error" in result.output


class TestClusterAddNode:
    """Tests for cluster add-node command."""

    @patch("kubani.cli.commands.cluster_impl.INVENTORY_PATH")
    def test_add_node_to_inventory(self, mock_path, tmp_path):
        """Test add-node adds to inventory file."""
        import yaml

        # Create a temp inventory file
        inventory_file = tmp_path / "hosts.yml"
        inventory_file.write_text(
            yaml.dump(
                {
                    "all": {
                        "children": {
                            "workers": {"hosts": {}},
                            "control_plane": {"hosts": {}},
                        }
                    }
                }
            )
        )

        mock_path.__truediv__ = lambda self, x: tmp_path / x

        result = runner.invoke(app, ["cluster", "add-node", "new-node", "--role", "worker"])

        # Check the file was updated
        with open(inventory_file) as f:
            updated = yaml.safe_load(f)

        assert "new-node" in updated["all"]["children"]["workers"]["hosts"]


class TestClusterProvision:
    """Tests for cluster provision command."""

    def test_provision_help(self):
        """Test provision command shows help."""
        result = runner.invoke(app, ["cluster", "provision", "--help"])

        assert result.exit_code == 0
        assert "Run Ansible provisioning" in result.output
        assert "--tag" in result.output
        assert "--check" in result.output
