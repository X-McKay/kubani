"""Tests for A2A client with circuit breaker."""

import time

import pytest

from core_agents.communication.a2a import (
    A2AClient,
    A2AClientConfig,
    A2AQueryResult,
    AgentCapability,
    AgentInfo,
    AgentRegistry,
    CircuitBreaker,
    CircuitState,
)


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_initial_state_is_closed(self):
        """Circuit breaker starts in closed state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_opens_after_threshold_failures(self):
        """Circuit opens after failure threshold is exceeded."""
        cb = CircuitBreaker(failure_threshold=3)

        # Record failures
        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_success_resets_failure_count(self):
        """Success resets failure count when closed."""
        cb = CircuitBreaker(failure_threshold=5)

        # Record some failures
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

        # Success resets count
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_half_open_after_recovery_timeout(self):
        """Circuit transitions to half-open after recovery timeout."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        # Open the circuit
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

        # Wait for recovery timeout
        time.sleep(0.15)

        # Should transition to half-open
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self):
        """Success in half-open state closes the circuit."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)

        # Open the circuit
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Wait and transition to half-open
        time.sleep(0.02)
        cb.can_execute()
        assert cb.state == CircuitState.HALF_OPEN

        # Success closes the circuit
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_failure_reopens_circuit(self):
        """Failure in half-open state reopens the circuit."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)

        # Open the circuit
        cb.record_failure()

        # Wait and transition to half-open
        time.sleep(0.02)
        cb.can_execute()
        assert cb.state == CircuitState.HALF_OPEN

        # Failure reopens the circuit
        cb.record_failure()
        assert cb.state == CircuitState.OPEN


class TestAgentRegistry:
    """Tests for AgentRegistry."""

    def test_register_and_get_agent(self):
        """Can register and retrieve an agent."""
        registry = AgentRegistry()

        agent = AgentInfo(
            id="test-agent",
            name="Test Agent",
            description="A test agent",
            capabilities=[
                AgentCapability(
                    name="test-capability",
                    description="A test capability",
                )
            ],
            endpoint="test-agent.ai-agents.svc.cluster.local",
        )

        registry.register_agent(agent)
        retrieved = registry.get_agent("test-agent")

        assert retrieved is not None
        assert retrieved.id == "test-agent"
        assert retrieved.name == "Test Agent"

    def test_find_agents_by_capability(self):
        """Can find agents by capability."""
        registry = AgentRegistry()

        agent1 = AgentInfo(
            id="agent-1",
            name="Agent 1",
            description="First agent",
            capabilities=[
                AgentCapability(name="pod-diagnosis", description="Diagnose pods"),
            ],
            endpoint="agent-1",
        )

        agent2 = AgentInfo(
            id="agent-2",
            name="Agent 2",
            description="Second agent",
            capabilities=[
                AgentCapability(name="pod-diagnosis", description="Also diagnoses pods"),
                AgentCapability(name="node-diagnosis", description="Diagnose nodes"),
            ],
            endpoint="agent-2",
        )

        registry.register_agent(agent1)
        registry.register_agent(agent2)

        # Find by capability
        pod_agents = registry.find_agents_for("pod-diagnosis")
        assert len(pod_agents) == 2

        node_agents = registry.find_agents_for("node-diagnosis")
        assert len(node_agents) == 1
        assert node_agents[0].id == "agent-2"

    def test_unregister_agent(self):
        """Can unregister an agent."""
        registry = AgentRegistry()

        agent = AgentInfo(
            id="test-agent",
            name="Test Agent",
            description="A test agent",
            capabilities=[],
            endpoint="test-agent",
        )

        registry.register_agent(agent)
        assert registry.get_agent("test-agent") is not None

        registry.unregister_agent("test-agent")
        assert registry.get_agent("test-agent") is None


class TestA2AClientConfig:
    """Tests for A2AClientConfig."""

    def test_default_config(self):
        """Default config has reasonable values."""
        config = A2AClientConfig()

        assert config.default_timeout == 5.0
        assert config.max_retries == 3
        assert config.retry_backoff == 0.5
        assert config.circuit_breaker_threshold == 5
        assert config.circuit_breaker_recovery == 30.0

    def test_custom_config(self):
        """Can customize config values."""
        config = A2AClientConfig(
            default_timeout=2.0,
            max_retries=5,
            retry_backoff=1.0,
            circuit_breaker_threshold=10,
            circuit_breaker_recovery=60.0,
        )

        assert config.default_timeout == 2.0
        assert config.max_retries == 5
        assert config.retry_backoff == 1.0
        assert config.circuit_breaker_threshold == 10
        assert config.circuit_breaker_recovery == 60.0


class TestA2AQueryResult:
    """Tests for A2AQueryResult."""

    def test_successful_result(self):
        """Can create a successful result."""
        result = A2AQueryResult(
            success=True,
            data={"foo": "bar"},
            agent_id="test-agent",
            latency_ms=50.0,
        )

        assert result.success is True
        assert result.data == {"foo": "bar"}
        assert result.error is None
        assert result.agent_id == "test-agent"
        assert result.latency_ms == 50.0

    def test_failed_result(self):
        """Can create a failed result."""
        result = A2AQueryResult(
            success=False,
            error="Connection refused",
            agent_id="test-agent",
            latency_ms=100.0,
            retries=3,
        )

        assert result.success is False
        assert result.data is None
        assert result.error == "Connection refused"
        assert result.retries == 3


class TestA2AClient:
    """Tests for A2AClient."""

    @pytest.fixture
    def registry_with_agent(self):
        """Create a registry with a test agent."""
        registry = AgentRegistry()
        agent = AgentInfo(
            id="test-agent",
            name="Test Agent",
            description="A test agent",
            capabilities=[
                AgentCapability(name="query", description="Handle queries"),
            ],
            endpoint="http://test-agent:9000",
        )
        registry.register_agent(agent)
        return registry

    def test_client_initialization(self):
        """Client initializes with default config."""
        client = A2AClient()

        assert client.config.default_timeout == 5.0
        assert client._circuit_breakers == {}

    def test_get_circuit_state_default(self):
        """Default circuit state is closed."""
        client = A2AClient()
        state = client.get_circuit_state("unknown-agent")
        assert state == CircuitState.CLOSED

    def test_reset_circuit_breaker(self, registry_with_agent):
        """Can reset a circuit breaker."""
        client = A2AClient(registry=registry_with_agent)

        # Create a circuit breaker by getting one
        cb = client._get_circuit_breaker("test-agent")
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

        # Reset it
        client.reset_circuit_breaker("test-agent")

        # Check it's reset
        new_cb = client._get_circuit_breaker("test-agent")
        assert new_cb.failure_count == 0
        assert new_cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_query_agent_not_found(self):
        """Query returns error if agent not found."""
        client = A2AClient(registry=AgentRegistry())

        result = await client.query(
            agent="nonexistent-agent",
            query="test",
        )

        assert result.success is False
        assert "not found" in result.error.lower()
        await client.close()

    @pytest.mark.asyncio
    async def test_query_circuit_breaker_open(self, registry_with_agent):
        """Query returns error if circuit breaker is open."""
        client = A2AClient(
            registry=registry_with_agent,
            config=A2AClientConfig(circuit_breaker_threshold=1),
        )

        # Open the circuit breaker
        cb = client._get_circuit_breaker("test-agent")
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Query should fail due to open circuit
        result = await client.query(
            agent="test-agent",
            query="test",
        )

        assert result.success is False
        assert "circuit breaker" in result.error.lower()
        await client.close()


class TestCircuitStateEnum:
    """Tests for CircuitState enum."""

    def test_circuit_state_values(self):
        """CircuitState enum has expected values."""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"

    def test_circuit_state_is_string_enum(self):
        """CircuitState can be used as string."""
        assert CircuitState.CLOSED == "closed"
        assert CircuitState.OPEN == "open"
        assert CircuitState.HALF_OPEN == "half_open"
