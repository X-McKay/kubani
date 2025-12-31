"""
Integration tests for core_agents with mocked external services.

These tests verify that the various components work together correctly
without requiring actual external services (Qdrant, Neo4j, vLLM).
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


class TestMemoryConfigIntegration:
    """Integration tests for memory configuration."""

    def test_config_can_be_used_with_mem0(self, mock_env_vars):
        """Test that generated config is valid for mem0.Memory."""
        from core_agents.memory import get_mem0_config

        config = get_mem0_config()

        # Verify structure is compatible with mem0
        assert isinstance(config, dict)
        assert config["llm"]["provider"] in ["openai", "anthropic"]
        assert config["embedder"]["provider"] in ["openai", "lmstudio"]
        assert config["vector_store"]["provider"] in ["qdrant", "pgvector"]

    def test_graph_config_can_be_used_with_mem0(self, mock_env_vars):
        """Test that graph config is valid for mem0.Memory."""
        from core_agents.memory import get_graph_mem0_config

        config = get_graph_mem0_config()

        # Verify graph store is included
        assert "graph_store" in config
        assert config["graph_store"]["provider"] == "neo4j"

        # Verify base config is still valid
        assert "llm" in config
        assert "embedder" in config
        assert "vector_store" in config


class TestAgentRegistrationIntegration:
    """Integration tests for agent registration workflow."""

    @pytest.mark.asyncio
    async def test_full_registration_workflow(self, sample_agent_info):
        """Test complete agent registration and discovery workflow."""
        from core_agents.communication import (
            get_agent_registry,
            register_agent_on_startup,
        )

        # Clear registry
        registry = get_agent_registry()
        registry._agents.clear()
        registry._capability_index.clear()

        # Register agent
        await register_agent_on_startup(sample_agent_info)

        # Verify discovery works
        agent = registry.get_agent("test-agent")
        assert agent is not None

        # Verify capability lookup works
        found = registry.find_agent_for("test-capability")
        assert found is not None
        assert found.id == "test-agent"

        # Verify endpoint resolution works
        url = agent.a2a_url
        assert "test-agent" in url

    def test_multiple_agent_registration(self):
        """Test registering multiple agents."""
        from core_agents.communication import (
            AgentCapability,
            AgentInfo,
            AgentRegistry,
        )

        registry = AgentRegistry()

        agents = [
            AgentInfo(
                id=f"agent-{i}",
                name=f"Agent {i}",
                description=f"Agent {i} description",
                endpoint=f"agent-{i}.svc",
                capabilities=[
                    AgentCapability(
                        name=f"cap-{i}",
                        description=f"Capability {i}",
                    )
                ],
            )
            for i in range(3)
        ]

        for agent in agents:
            registry.register_agent(agent)

        assert len(registry.list_agents()) == 3

        # Verify each has its own capability
        for i in range(3):
            found = registry.find_agent_for(f"cap-{i}")
            assert found is not None
            assert found.id == f"agent-{i}"


class TestObservabilityIntegration:
    """Integration tests for observability hooks."""

    def test_hooks_creation(self):
        """Test that observability hooks can be created and have expected interface."""
        from core_agents.observability import create_observability_hooks

        hooks = create_observability_hooks()

        assert hooks is not None
        # ObservabilityHooks uses Strands HookProvider pattern with register_hooks method
        assert hasattr(hooks, "register_hooks")
        # Should have callbacks configured
        assert hasattr(hooks, "_on_request_complete")
        assert hasattr(hooks, "_on_tool_call")

    def test_metrics_aggregator(self):
        """Test metrics aggregator functionality."""
        from core_agents.observability import MetricsAggregator, RequestMetrics

        aggregator = MetricsAggregator()
        now = datetime.now(UTC)

        # Record some metrics using the record() method with RequestMetrics
        aggregator.record(
            RequestMetrics(
                request_id="test-1",
                agent_name="test-agent",
                start_time=now,
                end_time=now + timedelta(milliseconds=100),
                total_duration_ms=100.0,
                total_tokens=50,
                total_prompt_tokens=40,
                total_completion_tokens=10,
                model_call_count=1,
                tool_call_count=0,
            )
        )
        aggregator.record(
            RequestMetrics(
                request_id="test-2",
                agent_name="test-agent",
                start_time=now,
                end_time=now + timedelta(milliseconds=150),
                total_duration_ms=150.0,
                total_tokens=75,
                total_prompt_tokens=60,
                total_completion_tokens=15,
                model_call_count=2,
                tool_call_count=1,
            )
        )

        stats = aggregator.get_stats()

        assert stats["total_requests"] == 2
        assert stats["total_tokens"] == 125  # 50 + 75
        assert stats["avg_duration_ms"] == 125.0  # (100 + 150) / 2


class TestBaseUtilsIntegration:
    """Integration tests for base utilities."""

    def test_create_model_with_env_vars(self, mock_env_vars):
        """Test model creation respects environment variables."""
        # Mock the OpenAIModel class since it tries to connect
        with patch("core_agents.base.OpenAIModel") as mock_model_class:
            mock_model = MagicMock()
            mock_model_class.return_value = mock_model

            from core_agents import create_model

            create_model()

            # Should have attempted to create OpenAIModel
            mock_model_class.assert_called()
            # Verify it used environment variables
            call_args = mock_model_class.call_args
            assert call_args.kwargs["model_id"] == "test-model"

    def test_create_agent_returns_agent(self, mock_env_vars):
        """Test agent creation returns valid agent."""
        # Mock the Agent class and model creation
        with (
            patch("core_agents.base.Agent") as mock_agent_class,
            patch("core_agents.base.OpenAIModel") as mock_model_class,
        ):
            mock_agent = MagicMock()
            mock_agent_class.return_value = mock_agent
            mock_model_class.return_value = MagicMock()

            from core_agents import create_agent

            agent = create_agent(
                name="test",
                description="Test agent",
                system_prompt="You are a test agent",
                tools=[],
            )

            assert agent is not None
            mock_agent_class.assert_called()


class TestCrossModuleIntegration:
    """Tests for cross-module functionality."""

    def test_communication_uses_standard_patterns(self, sample_agent_info):
        """Test that communication module uses standard patterns."""
        from core_agents.communication import AgentRegistry

        registry = AgentRegistry()
        registry.register_agent(sample_agent_info)

        # Verify Temporal task queue naming convention
        from core_agents.communication import get_task_queue_for_agent

        queue = get_task_queue_for_agent("test-agent")
        assert queue == "test-agent"

    def test_intelligence_modules_work_together(self):
        """Test that intelligence modules can work together."""
        from core_agents.intelligence import (
            CapacityPlanner,
            PatternMatcher,
            ResourceUsage,
        )

        # Scenario: High resource usage leads to OOMKilled issues
        planner = CapacityPlanner()
        matcher = PatternMatcher()

        now = datetime.now(UTC)

        # Record high memory usage
        for i in range(5):
            planner.record_usage(
                ResourceUsage(
                    node_name="node-1",
                    cpu_cores_used=4.0,
                    cpu_cores_total=8.0,
                    memory_gb_used=13.0 + i * 0.5,  # Growing memory usage
                    memory_gb_total=16.0,
                    timestamp=now + timedelta(hours=i),
                )
            )

            # Record corresponding OOMKilled issues
            matcher.record_issue(
                issue_type="OOMKilled",
                resource="pod/memory-pod",
                namespace="default",
                timestamp=now + timedelta(hours=i),
            )

        # Both should have data
        assert planner.get_current_usage("node-1") is not None

        # Get patterns (uses get_patterns() not detect_patterns())
        patterns = matcher.get_patterns()

        # Should be able to get recommendations
        recommendations = planner.get_recommendations()

        # Verify we can access the data (exact numbers depend on thresholds)
        assert isinstance(recommendations, list)
        assert isinstance(patterns, list)


class TestModuleExports:
    """Test that all expected symbols are exported from modules."""

    def test_core_agents_exports(self):
        """Test main package exports."""
        import core_agents

        # Base utilities
        assert hasattr(core_agents, "create_model")
        assert hasattr(core_agents, "create_agent")

        # Memory config
        assert hasattr(core_agents, "get_mem0_config")
        assert hasattr(core_agents, "get_graph_mem0_config")

    def test_communication_exports(self):
        """Test communication module exports."""
        from core_agents import communication

        # A2A components
        assert hasattr(communication, "AgentCapability")
        assert hasattr(communication, "AgentInfo")
        assert hasattr(communication, "AgentRegistry")
        assert hasattr(communication, "get_agent_registry")

        # Registration
        assert hasattr(communication, "register_agent_on_startup")
        assert hasattr(communication, "register_agent_on_startup_sync")

        # Saga patterns
        assert hasattr(communication, "Saga")
        assert hasattr(communication, "SagaStep")
        assert hasattr(communication, "SagaResult")

    def test_intelligence_exports(self):
        """Test intelligence module exports."""
        from core_agents import intelligence

        # Anomaly detection
        assert hasattr(intelligence, "AnomalyDetector")
        assert hasattr(intelligence, "AnomalyAlert")
        assert hasattr(intelligence, "get_anomaly_detector")

        # Capacity planning
        assert hasattr(intelligence, "CapacityPlanner")
        assert hasattr(intelligence, "ResourceUsage")
        assert hasattr(intelligence, "get_capacity_planner")

        # Pattern matching
        assert hasattr(intelligence, "PatternMatcher")
        assert hasattr(intelligence, "IssueRecord")
        assert hasattr(intelligence, "get_pattern_matcher")
        assert hasattr(intelligence, "suggest_prevention")

    def test_observability_exports(self):
        """Test observability module exports."""
        from core_agents import observability

        assert hasattr(observability, "create_observability_hooks")
        assert hasattr(observability, "ObservabilityHooks")
        assert hasattr(observability, "MetricsAggregator")
        assert hasattr(observability, "RequestMetrics")
