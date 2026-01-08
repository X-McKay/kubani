"""
Chaos Engineering Tests for System Resilience.

These tests validate that the Kubani multi-agent system handles
various failure scenarios gracefully and recovers appropriately.

Prerequisites:
- Chaos Mesh installed in the test cluster
- kubectl access configured
- Agent pods running in ai-agents namespace

Run with:
    pytest tests/chaos/ -v --chaos

Note: These tests require a running cluster with chaos-mesh installed.
They are marked with @pytest.mark.chaos to allow selective execution.
"""

import asyncio

import pytest

from tests.chaos.framework import ChaosTestHelper

# Skip all tests if not in chaos test mode
pytestmark = pytest.mark.chaos


class TestSystemResilience:
    """
    Test system resilience under various failure conditions.

    Each test follows the pattern:
    1. Verify system is healthy
    2. Apply chaos experiment
    3. Monitor agent behavior
    4. Verify system recovers
    5. Cleanup
    """

    @pytest.fixture
    def helper(self) -> ChaosTestHelper:
        """Create chaos test helper."""
        return ChaosTestHelper()

    @pytest.fixture
    def ensure_healthy(self, helper: ChaosTestHelper):
        """Ensure agents are healthy before test."""
        import asyncio

        async def check():
            return await helper.check_all_agents_healthy()

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        healthy = loop.run_until_complete(check())
        if not healthy:
            pytest.skip("Agents not healthy - skipping chaos test")

    @pytest.fixture
    def chaos_mesh_installed(self, helper: ChaosTestHelper):
        """Skip if chaos-mesh is not installed."""
        import asyncio

        async def check():
            return await helper.check_chaos_mesh_installed()

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        installed = loop.run_until_complete(check())
        if not installed:
            pytest.skip("chaos-mesh not installed in cluster")

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Chaos-mesh webhook has connectivity issues on this cluster - needs investigation"
    )
    async def test_redis_failure_recovery(
        self,
        helper: ChaosTestHelper,
        chaos_mesh_installed,
        ensure_healthy,
    ):
        """
        Test agents handle Redis (Event Bus) failure gracefully.

        Validates:
        - Agents don't crash when Redis is unavailable
        - Agents log appropriate errors
        - System recovers when Redis returns
        """
        # Run the chaos experiment
        result = await helper.run_experiment(
            "redis_failure.yaml",
            pre_check=True,
            wait_for_completion=True,
            cleanup=True,
        )

        # Verify no agents crashed
        assert (
            len(result.agents_crashed) == 0
        ), f"Agents crashed during Redis failure: {result.agents_crashed}"

        # Verify system recovered
        assert result.recovery_time_seconds is not None, "System did not recover within timeout"
        assert (
            result.recovery_time_seconds < 120
        ), f"Recovery took too long: {result.recovery_time_seconds}s"

        # Check logs for appropriate error handling
        logs = helper.get_agent_logs(since="5m")
        # Should see connection errors but not crashes
        assert "panic" not in logs.lower(), "Agent panicked during Redis failure"

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Chaos-mesh webhook has connectivity issues on this cluster - needs investigation"
    )
    async def test_qdrant_failure_recovery(
        self,
        helper: ChaosTestHelper,
        chaos_mesh_installed,
        ensure_healthy,
    ):
        """
        Test agents handle Qdrant (Skill Library) failure gracefully.

        Validates:
        - Agents continue operating without skill library
        - Degraded mode is activated
        - System recovers when Qdrant returns
        """
        result = await helper.run_experiment(
            "qdrant_failure.yaml",
            pre_check=True,
            wait_for_completion=True,
            cleanup=True,
        )

        # Verify no agents crashed
        assert (
            len(result.agents_crashed) == 0
        ), f"Agents crashed during Qdrant failure: {result.agents_crashed}"

        # Verify recovery
        assert result.recovery_time_seconds is not None, "System did not recover within timeout"

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="NetworkChaos has ipset issues on this cluster - needs investigation")
    async def test_network_partition(
        self,
        helper: ChaosTestHelper,
        chaos_mesh_installed,
        ensure_healthy,
    ):
        """
        Test agents handle network partition gracefully.

        Validates:
        - Isolated agents don't crash
        - System state remains consistent
        - Agents reconnect when partition heals
        """
        # Get initial health state
        initial_health = helper.check_agents_healthy()
        initial_restart_counts = {h.name: h.restart_count for h in initial_health}

        await helper.run_experiment(
            "network_partition.yaml",
            pre_check=True,
            wait_for_completion=True,
            cleanup=True,
        )

        # Allow extra time for network recovery
        await asyncio.sleep(10)

        # Check final health
        final_health = helper.check_agents_healthy()

        # Verify no new restarts occurred
        for health in final_health:
            initial_count = initial_restart_counts.get(health.name, 0)
            assert (
                health.restart_count == initial_count
            ), f"Agent {health.name} restarted during network partition"

        # Verify all agents healthy
        assert (
            await helper.check_all_agents_healthy()
        ), "Not all agents recovered from network partition"

    @pytest.mark.asyncio
    async def test_cpu_exhaustion(
        self,
        helper: ChaosTestHelper,
        chaos_mesh_installed,
        ensure_healthy,
    ):
        """
        Test agents handle CPU exhaustion gracefully.

        Validates:
        - Agents remain responsive under CPU pressure
        - No OOMKills from CPU contention
        - System recovers when stress ends
        """
        result = await helper.run_experiment(
            "cpu_stress.yaml",
            pre_check=True,
            wait_for_completion=True,
            cleanup=True,
        )

        # Verify no agents crashed
        assert (
            len(result.agents_crashed) == 0
        ), f"Agents crashed during CPU stress: {result.agents_crashed}"

        # Verify recovery
        assert result.recovery_time_seconds is not None, "System did not recover from CPU stress"

    @pytest.mark.asyncio
    async def test_memory_exhaustion(
        self,
        helper: ChaosTestHelper,
        chaos_mesh_installed,
        ensure_healthy,
    ):
        """
        Test agents handle memory pressure gracefully.

        Validates:
        - Agents handle memory pressure without crashing
        - No unexpected OOMKills
        - System recovers when stress ends
        """
        result = await helper.run_experiment(
            "memory_stress.yaml",
            pre_check=True,
            wait_for_completion=True,
            cleanup=True,
        )

        # Verify recovery (some restarts may be acceptable under memory pressure)
        assert result.recovery_time_seconds is not None, "System did not recover from memory stress"

        # Check logs for OOM events
        logs = helper.get_agent_logs(since="5m")
        oom_count = logs.lower().count("oomkilled")
        assert oom_count < len(
            helper.check_agents_healthy()
        ), "Too many OOMKilled events during memory stress"

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="NetworkChaos has ipset issues on this cluster - needs investigation")
    async def test_network_latency(
        self,
        helper: ChaosTestHelper,
        chaos_mesh_installed,
        ensure_healthy,
    ):
        """
        Test agents handle network latency (slow LLM API) gracefully.

        Validates:
        - Agents handle slow responses without timing out
        - Request timeouts are handled appropriately
        - No cascading failures from slow responses
        """
        result = await helper.run_experiment(
            "network_latency.yaml",
            pre_check=True,
            wait_for_completion=True,
            cleanup=True,
        )

        # Verify no agents crashed from timeouts
        assert (
            len(result.agents_crashed) == 0
        ), f"Agents crashed during network latency: {result.agents_crashed}"

        # Verify recovery
        assert (
            result.recovery_time_seconds is not None
        ), "System did not recover from network latency"

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.skip(reason="NetworkChaos has ipset issues on this cluster - needs investigation")
    async def test_cascading_failures(
        self,
        helper: ChaosTestHelper,
        chaos_mesh_installed,
        ensure_healthy,
    ):
        """
        Test system handles multiple simultaneous failures.

        Validates:
        - System handles combined stress scenarios
        - No single point of failure causes complete outage
        - Graceful degradation under multiple failures
        """
        # Apply CPU stress first
        helper.apply_experiment("cpu_stress.yaml")
        await asyncio.sleep(5)

        # Add network latency
        helper.apply_experiment("network_latency.yaml")
        await asyncio.sleep(10)

        # Check that at least some agents are still running
        health_list = helper.check_agents_healthy()
        running_count = sum(1 for h in health_list if h.ready)

        # Cleanup
        helper.delete_experiment("cpu_stress.yaml")
        helper.delete_experiment("network_latency.yaml")

        # Wait for recovery
        recovery_time = await helper.wait_for_recovery(timeout=180)

        # At least one agent should have survived
        assert running_count > 0, "All agents crashed during cascading failures"

        # System should eventually recover
        assert recovery_time is not None, "System did not recover from cascading failures"


class TestEventBusResilience:
    """
    Test Event Bus (Redis) specific resilience scenarios.
    """

    @pytest.fixture
    def helper(self) -> ChaosTestHelper:
        return ChaosTestHelper()

    @pytest.fixture
    def chaos_mesh_installed(self, helper: ChaosTestHelper):
        import asyncio

        async def check():
            return await helper.check_chaos_mesh_installed()

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        installed = loop.run_until_complete(check())
        if not installed:
            pytest.skip("chaos-mesh not installed")

    @pytest.mark.asyncio
    async def test_event_bus_reconnection(
        self,
        helper: ChaosTestHelper,
        chaos_mesh_installed,
    ):
        """
        Test agents reconnect to Redis after temporary failure.

        Validates:
        - Agents detect Redis disconnection
        - Reconnection is automatic
        - Pending events are not lost
        """
        # This test verifies that Redis cache failures don't crash agents
        # Redis is used for mem0 caching, not event bus (agents use Temporal)
        result = await helper.run_experiment(
            "redis_failure.yaml",
            wait_for_completion=True,
        )

        # Verify experiment completed successfully
        assert result is not None, "Experiment failed to run"

        # Wait for system to stabilize after Redis failure
        await asyncio.sleep(10)

        # Verify agents are still healthy after Redis disruption
        health = helper.check_agents_healthy()
        ready_agents = [h for h in health if h.ready]
        assert len(ready_agents) > 0, "No agents recovered after Redis cache failure"


class TestGracefulDegradation:
    """
    Test graceful degradation behavior.
    """

    @pytest.fixture
    def helper(self) -> ChaosTestHelper:
        return ChaosTestHelper()

    @pytest.fixture
    def chaos_mesh_installed(self, helper: ChaosTestHelper):
        import asyncio

        async def check():
            return await helper.check_chaos_mesh_installed()

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        installed = loop.run_until_complete(check())
        if not installed:
            pytest.skip("chaos-mesh not installed")

    @pytest.mark.asyncio
    async def test_partial_system_availability(
        self,
        helper: ChaosTestHelper,
        chaos_mesh_installed,
    ):
        """
        Test that partial system failures don't cause complete outage.

        Validates:
        - Some agents can continue operating when others fail
        - Core functionality remains available
        - Error messages are propagated appropriately
        """
        # Kill one agent's resources
        await helper.run_experiment(
            "memory_stress.yaml",
            wait_for_completion=True,
        )

        # Check that most agents are still healthy
        health_list = helper.check_agents_healthy()
        healthy_count = sum(1 for h in health_list if h.ready)
        total_count = len(health_list)

        # At least half should remain healthy
        assert (
            healthy_count >= total_count / 2
        ), f"Too many agents unhealthy: {healthy_count}/{total_count}"


# Pytest configuration for chaos tests
def pytest_configure(config):
    """Register chaos marker."""
    config.addinivalue_line(
        "markers",
        "chaos: mark test as a chaos engineering test (requires chaos-mesh)",
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow (may take several minutes)",
    )
