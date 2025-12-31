"""
Shared pytest fixtures for core_agents tests.
"""

from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for memory config."""
    env = {
        "QDRANT_HOST": "localhost",
        "QDRANT_PORT": "6333",
        "QDRANT_COLLECTION": "test-collection",
        "NEO4J_URL": "bolt://localhost:7687",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "password",  # pragma: allowlist secret
        "VLLM_API_URL": "http://localhost:8000/v1",
        "VLLM_MODEL": "test-model",
        "EMBEDDINGS_API_URL": "http://localhost:8001/v1",
        "EMBEDDINGS_MODEL": "Qwen/Qwen3-Embedding-0.6B",
    }
    with patch.dict("os.environ", env, clear=False):
        yield env


@pytest.fixture
def sample_agent_info():
    """Create a sample AgentInfo for testing."""
    from core_agents.communication import AgentCapability, AgentInfo

    return AgentInfo(
        id="test-agent",
        name="Test Agent",
        description="A test agent for unit tests",
        endpoint="test-agent.ai-agents.svc.cluster.local",
        version="1.0.0",
        capabilities=[
            AgentCapability(
                name="test-capability",
                description="A test capability",
                input_schema={"input": "string"},
                output_schema={"output": "string"},
                tags=["test", "example"],
            ),
            AgentCapability(
                name="another-capability",
                description="Another test capability",
                input_schema={},
                output_schema={},
                tags=["test"],
            ),
        ],
    )


@pytest.fixture
def sample_capability():
    """Create a sample AgentCapability for testing."""
    from core_agents.communication import AgentCapability

    return AgentCapability(
        name="sample-capability",
        description="A sample capability for testing",
        input_schema={"query": "string"},
        output_schema={"result": "array"},
        tags=["sample", "test"],
    )


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client for memory tests."""
    mock = MagicMock()
    mock.scroll.return_value = ([], None)
    mock.search.return_value = []
    mock.upsert.return_value = None
    return mock


@pytest.fixture
def mock_neo4j_driver():
    """Mock Neo4j driver for graph memory tests."""
    mock = MagicMock()
    session = MagicMock()
    mock.session.return_value.__enter__ = MagicMock(return_value=session)
    mock.session.return_value.__exit__ = MagicMock(return_value=None)
    return mock


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for HTTP tests."""
    mock = MagicMock()
    mock.post.return_value = MagicMock(status_code=200, json=lambda: {"id": "test-id"})
    mock.get.return_value = MagicMock(status_code=200, json=lambda: {})
    return mock


@pytest.fixture
def sample_metric_data():
    """Sample metric data for intelligence tests."""
    return [
        {"timestamp": "2024-01-01T00:00:00Z", "value": 50.0},
        {"timestamp": "2024-01-01T01:00:00Z", "value": 52.0},
        {"timestamp": "2024-01-01T02:00:00Z", "value": 48.0},
        {"timestamp": "2024-01-01T03:00:00Z", "value": 55.0},
        {"timestamp": "2024-01-01T04:00:00Z", "value": 51.0},
    ]


@pytest.fixture
def sample_issue_record():
    """Create a sample issue record for pattern matching tests."""
    from datetime import datetime

    from core_agents.intelligence import IssueRecord

    return IssueRecord(
        issue_type="CrashLoopBackOff",
        resource="pod/test-pod",
        namespace="default",
        timestamp=datetime.now(UTC),
        metadata={"exit_code": 1, "container": "main"},
    )
