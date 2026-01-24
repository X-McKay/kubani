---
name: testing
description: Testing patterns, fixtures, and best practices for Kubani. Use this skill when writing or running tests.
---

# Testing Guide

This skill documents testing patterns, fixtures, and best practices for Kubani.

## Test Structure

```
tests/
├── unit/                    # Fast, isolated tests
│   ├── test_config.py
│   ├── test_mcp_client.py
│   └── test_learning.py
├── integration/             # Tests with real services
│   ├── test_temporal.py
│   └── test_memory.py
├── e2e/                     # End-to-end tests
│   └── test_remediation.py
└── conftest.py              # Shared fixtures
```

## Running Tests

```bash
# Run all tests
just test

# Run specific test file
pytest tests/unit/test_config.py

# Run with coverage
pytest --cov=kubani tests/

# Run agent-specific tests
kubani-dev test k8s-monitor

# Run evaluation suite
kubani-dev eval run --suite evaluations/k8s/pod_remediation.yaml
```

## Common Fixtures

### Configuration Fixture

```python
import pytest
from unittest.mock import patch

@pytest.fixture
def test_config():
    """Provide test configuration."""
    with patch.dict("os.environ", {
        "KUBANI_ENVIRONMENT": "test",
        "KUBANI_LLM__API_URL": "http://localhost:8000/v1",
    }):
        from kubani.framework.config import get_config, reload_config
        reload_config()
        yield get_config()
```

### MCP Client Fixture

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_mcp_client():
    """Mock MCP client for isolated testing."""
    with patch("kubani.framework.mcp.get_mcp_client") as mock:
        client = AsyncMock()
        
        # Configure default responses
        client.memory.store_learning.return_value = {"id": "learning-123"}
        client.memory.query_learnings.return_value = []
        client.temporal.list_workflows.return_value = []
        client.discord.send_message.return_value = {"id": "msg-123"}
        
        mock.return_value = client
        yield client
```

### Agent Factory Fixture

```python
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_agent():
    """Mock agent for testing."""
    agent = AsyncMock()
    agent.name = "test-agent"
    agent.invoke.return_value = {"response": "test response"}
    return agent

@pytest.fixture
def agent_factory(mock_agent):
    """Mock agent factory."""
    with patch("kubani.framework.get_agent_factory") as mock:
        factory = AsyncMock()
        factory.create_agent.return_value = mock_agent
        mock.return_value = factory
        yield factory
```

### Temporal Fixtures

```python
import pytest
from temporalio.testing import WorkflowEnvironment

@pytest.fixture
async def temporal_env():
    """Provide Temporal test environment."""
    async with await WorkflowEnvironment.start_local() as env:
        yield env

@pytest.fixture
async def temporal_client(temporal_env):
    """Provide Temporal client for testing."""
    return temporal_env.client
```

## Unit Test Patterns

### Testing Configuration

```python
import pytest
from kubani.framework.config import KubaniConfig

class TestConfiguration:
    def test_default_values(self):
        """Test default configuration values."""
        config = KubaniConfig()
        
        assert config.environment == "development"
        assert config.llm.api_url is not None
        assert config.temporal.enabled is True
    
    def test_environment_override(self, monkeypatch):
        """Test environment variable overrides."""
        monkeypatch.setenv("KUBANI_LLM__API_URL", "http://custom:8000")
        
        config = KubaniConfig()
        
        assert config.llm.api_url == "http://custom:8000"
```

### Testing MCP Client

```python
import pytest
from kubani.framework.mcp.client import MCPClient

class TestMCPClient:
    @pytest.mark.asyncio
    async def test_store_learning(self, mock_mcp_client):
        """Test learning storage."""
        result = await mock_mcp_client.memory.store_learning(
            agent_id="test-agent",
            learning_type="pattern",
            content="test content",
            confidence=0.85,
        )
        
        assert result["id"] == "learning-123"
    
    @pytest.mark.asyncio
    async def test_query_learnings(self, mock_mcp_client):
        """Test learning query."""
        mock_mcp_client.memory.query_learnings.return_value = [
            {"id": "1", "content": "learning 1"},
            {"id": "2", "content": "learning 2"},
        ]
        
        results = await mock_mcp_client.memory.query_learnings(
            query="test query",
            limit=10,
        )
        
        assert len(results) == 2
```

### Testing Learning System

```python
import pytest
from kubani.framework.learning.voyager import CriticAgent

class TestCriticAgent:
    @pytest.fixture
    def critic(self, mock_mcp_client):
        """Create critic agent with mocked dependencies."""
        return CriticAgent()
    
    @pytest.mark.asyncio
    async def test_evaluate_success(self, critic):
        """Test successful execution evaluation."""
        result = await critic.evaluate_execution(
            agent_id="test-agent",
            task_description="Test task",
            execution_result={"status": "success"},
            context={},
        )
        
        assert result.success is True
        assert 0 <= result.score <= 1
    
    @pytest.mark.asyncio
    async def test_evaluate_failure(self, critic):
        """Test failed execution evaluation."""
        result = await critic.evaluate_execution(
            agent_id="test-agent",
            task_description="Test task",
            execution_result={"status": "error", "error": "Something failed"},
            context={},
        )
        
        assert result.success is False
        assert len(result.improvement_suggestions) > 0
```

## Integration Test Patterns

### Testing with Real Temporal

```python
import pytest
from temporalio.testing import WorkflowEnvironment
from my_agent.workflows import RemediationWorkflow

class TestRemediationWorkflow:
    @pytest.mark.asyncio
    async def test_workflow_execution(self, temporal_env):
        """Test workflow with real Temporal."""
        async with Worker(
            temporal_env.client,
            task_queue="test-queue",
            workflows=[RemediationWorkflow],
            activities=[investigate_pod, execute_remediation],
        ):
            result = await temporal_env.client.execute_workflow(
                RemediationWorkflow.run,
                RemediationInput(pod_name="test-pod"),
                id="test-workflow",
                task_queue="test-queue",
            )
            
            assert result.success is True
```

### Testing with Real Memory

```python
import pytest
from kubani.framework.memory.shared import SharedMemory

class TestSharedMemory:
    @pytest.fixture
    async def memory(self):
        """Create real memory connection for integration tests."""
        memory = SharedMemory()
        await memory.initialize()
        yield memory
        await memory.cleanup()
    
    @pytest.mark.asyncio
    async def test_store_and_query(self, memory):
        """Test storing and querying learnings."""
        # Store
        await memory.store_learning(
            agent_id="test-agent",
            learning_type="pattern",
            content="Integration test learning",
            confidence=0.9,
        )
        
        # Query
        results = await memory.query_learnings(
            query="integration test",
            limit=10,
        )
        
        assert len(results) >= 1
        assert "integration" in results[0].content.lower()
```

## Evaluation Tests

### Testing with Evaluation Suites

```python
import pytest
from kubani_dev.eval_harness import EvaluationHarness

class TestPodRemediation:
    @pytest.fixture
    def harness(self):
        """Create evaluation harness."""
        return EvaluationHarness()
    
    @pytest.mark.asyncio
    async def test_oom_detection(self, harness):
        """Test OOM kill detection evaluation."""
        result = await harness.run_test_case(
            suite="evaluations/k8s/pod_remediation.yaml",
            test_case="oom-kill-detection",
        )
        
        assert result.passed is True
        assert result.metrics["accuracy"] >= 0.8
```

## Mocking Patterns

### Mocking External Services

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_kubernetes():
    """Mock Kubernetes client."""
    with patch("kubernetes.client.CoreV1Api") as mock:
        api = AsyncMock()
        api.read_namespaced_pod.return_value = Mock(
            status=Mock(phase="Running"),
            metadata=Mock(name="test-pod"),
        )
        mock.return_value = api
        yield api

@pytest.fixture
def mock_discord():
    """Mock Discord client."""
    with patch("discord.Client") as mock:
        client = AsyncMock()
        client.send_message.return_value = Mock(id="msg-123")
        mock.return_value = client
        yield client
```

### Mocking LLM Responses

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_llm():
    """Mock LLM for deterministic testing."""
    with patch("kubani.framework.llm.get_llm_client") as mock:
        client = AsyncMock()
        client.generate.return_value = {
            "content": "Test response",
            "usage": {"tokens": 100},
        }
        mock.return_value = client
        yield client
```

## Best Practices

### 1. Test Isolation

```python
# Good: Each test is independent
@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons between tests."""
    from kubani.framework.config import _config_instance
    _config_instance = None
    yield
```

### 2. Descriptive Test Names

```python
# Good: Clear what's being tested
def test_critic_identifies_memory_leak_pattern():
    ...

# Bad: Vague name
def test_critic():
    ...
```

### 3. Arrange-Act-Assert

```python
@pytest.mark.asyncio
async def test_learning_storage():
    # Arrange
    memory = SharedMemory()
    learning = Learning(content="test", confidence=0.9)
    
    # Act
    result = await memory.store(learning)
    
    # Assert
    assert result.id is not None
    assert result.stored_at is not None
```

### 4. Test Edge Cases

```python
class TestSkillLibrary:
    @pytest.mark.asyncio
    async def test_find_skill_not_found(self, library):
        """Test behavior when skill doesn't exist."""
        result = await library.find_skill("nonexistent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_find_skill_empty_triggers(self, library):
        """Test behavior with empty triggers."""
        result = await library.find_skill(triggers=[])
        assert result is not None  # Should return default
```

### 5. Use Parametrized Tests

```python
@pytest.mark.parametrize("error_type,expected_action", [
    ("OOMKilled", "increase_memory"),
    ("CrashLoopBackOff", "check_logs"),
    ("ImagePullBackOff", "verify_image"),
])
@pytest.mark.asyncio
async def test_remediation_actions(error_type, expected_action, agent):
    """Test remediation actions for different error types."""
    result = await agent.diagnose(error_type)
    assert result.recommended_action == expected_action
```

## Running Tests in CI

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install uv
          uv pip install -e ".[dev]"
          uv pip install -e kubani/
      
      - name: Run tests
        run: pytest --cov=kubani --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
```
