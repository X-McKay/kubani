"""Pytest configuration and shared fixtures."""

import pytest
from hypothesis import Verbosity, settings

# Configure Hypothesis for property-based testing
settings.register_profile("default", max_examples=100, verbosity=Verbosity.normal)
settings.register_profile("ci", max_examples=1000, verbosity=Verbosity.verbose)
settings.register_profile("dev", max_examples=10, verbosity=Verbosity.verbose)

# Load the default profile
settings.load_profile("default")


@pytest.fixture
def sample_inventory_data():
    """Sample inventory data for testing."""
    return {
        "all": {
            "vars": {
                "k3s_version": "v1.28.5+k3s1",
                "cluster_name": "test-cluster",
                "tailscale_network": "100.64.0.0/10",
            },
            "children": {
                "control_plane": {
                    "hosts": {
                        "test-cp": {
                            "ansible_host": "100.64.0.1",
                            "tailscale_ip": "100.64.0.1",
                            "node_labels": {"node-role": "control-plane"},
                        }
                    }
                },
                "workers": {
                    "hosts": {
                        "test-worker": {
                            "ansible_host": "100.64.0.2",
                            "tailscale_ip": "100.64.0.2",
                            "reserved_cpu": "2",
                            "reserved_memory": "4Gi",
                            "node_labels": {"node-role": "worker"},
                        }
                    }
                },
            },
        }
    }
