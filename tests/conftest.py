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


# ============================================================================
# Additional fixtures for new features (feature/manus-20260111)
# ============================================================================

import os
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment variables before each test."""
    original_env = os.environ.copy()
    os.environ["KUBANI_ENVIRONMENT"] = "development"  # Use valid environment
    os.environ["KUBANI_LOG_LEVEL"] = "DEBUG"
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_config():
    """Provide a mock configuration object."""
    config = MagicMock()
    config.environment = "test"
    config.agent_name = "test-agent"
    config.log_level = "DEBUG"
    config.temporal.host = "localhost:7233"
    config.temporal.namespace = "test"
    config.temporal.enabled = True
    config.memory.qdrant.host = "localhost"
    config.memory.qdrant.port = 6333
    config.memory.neo4j.uri = "bolt://localhost:7687"
    config.memory.redis.host = "localhost"
    config.memory.redis.port = 6379
    config.llm.api_url = "http://localhost:8000/v1"
    config.llm.model = "test-model"
    config.mcp.temporal_url = "http://localhost:8081"
    config.mcp.qdrant_url = "http://localhost:8082"
    config.mcp.memory_url = "http://localhost:8083"
    config.mcp.discord_url = "http://localhost:8084"
    config.discord.alerts_channel = "test-alerts"
    config.discord.digest_channel = "test-digest"
    config.get_mcp_servers.return_value = {
        "temporal": "http://localhost:8081",
        "qdrant": "http://localhost:8082",
        "memory": "http://localhost:8083",
        "discord": "http://localhost:8084",
    }
    return config


@pytest.fixture
def mock_mcp_client():
    """Provide a mock MCP client."""
    client = MagicMock()
    client.temporal = MagicMock()
    client.temporal.list_workflows = AsyncMock(return_value=[])
    client.temporal.start_workflow = AsyncMock(return_value={"workflow_id": "test-123"})
    client.temporal.signal_workflow = AsyncMock(return_value=True)
    client.temporal.health_check = AsyncMock(return_value=True)
    client.qdrant = MagicMock()
    client.qdrant.search_vectors = AsyncMock(return_value=[])
    client.qdrant.upsert_vectors = AsyncMock(return_value=True)
    client.qdrant.health_check = AsyncMock(return_value=True)
    client.memory = MagicMock()
    client.memory.store_learning = AsyncMock(return_value="learning-123")
    client.memory.query_learnings = AsyncMock(return_value=[])
    client.memory.store_knowledge = AsyncMock(return_value="knowledge-123")
    client.memory.health_check = AsyncMock(return_value=True)
    client.discord = MagicMock()
    client.discord.send_message = AsyncMock(return_value={"id": "msg-123"})
    client.discord.send_embed = AsyncMock(return_value={"id": "msg-123"})
    client.discord.add_reaction = AsyncMock(return_value=True)
    client.discord.get_reactions = AsyncMock(return_value={})
    client.discord.health_check = AsyncMock(return_value=True)
    client.registry = MagicMock()
    client.registry.health_check = AsyncMock(return_value=True)
    client.health_check_all = AsyncMock(
        return_value={
            "temporal": True,
            "qdrant": True,
            "memory": True,
            "discord": True,
            "registry": True,
        }
    )
    return client


@pytest.fixture
def sample_evaluation_suite():
    """Provide a sample evaluation suite for testing."""
    return {
        "name": "test-suite",
        "description": "Test evaluation suite",
        "version": "1.0.0",
        "agent": "k8s-monitor",
        "test_cases": [
            {
                "name": "test-case-1",
                "description": "Test OOM detection",
                "input": {"scenario": "pod_oom_killed", "pod_name": "test-pod"},
                "expected": {"action_type": "increase_memory", "success": True},
                "evaluators": [{"type": "automated", "criteria": {"action_type_match": True}}],
            },
        ],
    }


@pytest.fixture
def temp_config_dir(tmp_path):
    """Provide a temporary directory for config files."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    default_config = config_dir / "config.default.yaml"
    default_config.write_text("""
environment: test
agent_name: test-agent
log_level: DEBUG
temporal:
  host: localhost:7233
  namespace: test
memory:
  qdrant:
    host: localhost
    port: 6333
llm:
  api_url: http://localhost:8000/v1
  model: test-model
""")
    return config_dir
