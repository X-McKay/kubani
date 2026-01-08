"""Tests for the AgentFactory."""

import os
from unittest.mock import MagicMock, patch

from core_agents.config import reset_config
from core_agents.factory import (
    AgentConfig,
    AgentFactory,
    ModelConfig,
    SwarmConfig,
    create_agent,
    create_model,
    create_swarm,
    get_agent_factory,
    quick_agent,
)


class TestModelConfig:
    """Tests for ModelConfig."""

    def setup_method(self):
        """Reset config before each test."""
        reset_config()

    def teardown_method(self):
        """Reset config after each test."""
        reset_config()

    def test_defaults_from_environment(self):
        """Test that ModelConfig reads from centralized config environment."""
        # Use KUBANI_ prefix for centralized config
        with patch.dict(
            os.environ,
            {
                "KUBANI_VLLM_API_URL": "http://test:8000/v1",
                "KUBANI_DEFAULT_MODEL_ID": "test-model",
            },
        ):
            reset_config()  # Clear cached config
            config = ModelConfig()
            assert config.base_url == "http://test:8000/v1"
            assert config.model_id == "test-model"
            assert config.stream is True

    def test_explicit_values_override_env(self):
        """Test that explicit values override environment."""
        with patch.dict(
            os.environ,
            {
                "KUBANI_VLLM_API_URL": "http://env:8000/v1",
                "KUBANI_DEFAULT_MODEL_ID": "env-model",
            },
        ):
            reset_config()  # Clear cached config
            config = ModelConfig(
                base_url="http://explicit:8000/v1",
                model_id="explicit-model",
                temperature=0.7,
            )
            assert config.base_url == "http://explicit:8000/v1"
            assert config.model_id == "explicit-model"
            assert config.temperature == 0.7

    def test_fallback_defaults(self):
        """Test fallback defaults when env vars not set."""
        reset_config()  # Clear cached config
        config = ModelConfig()
        assert "llm-api.vllm.svc.cluster.local" in config.base_url
        assert "Qwen" in config.model_id


class TestAgentConfig:
    """Tests for AgentConfig."""

    def test_required_fields(self):
        """Test that required fields are enforced."""
        config = AgentConfig(
            name="test-agent",
            description="Test description",
            system_prompt="You are a test agent.",
        )
        assert config.name == "test-agent"
        assert config.description == "Test description"
        assert config.system_prompt == "You are a test agent."
        assert config.tools == []
        assert config.enable_observability is True

    def test_optional_fields(self):
        """Test optional field defaults."""
        config = AgentConfig(
            name="test",
            description="test",
            system_prompt="test",
            enable_observability=False,
            observability_debug=True,
        )
        assert config.enable_observability is False
        assert config.observability_debug is True
        assert config.hooks is None
        assert config.hooks_factory is None


class TestSwarmConfig:
    """Tests for SwarmConfig."""

    def test_defaults(self):
        """Test swarm config defaults."""
        mock_agent1 = MagicMock(name="agent1")
        mock_agent2 = MagicMock(name="agent2")

        config = SwarmConfig(
            agents=[mock_agent1, mock_agent2],
            entry_point=mock_agent1,
        )
        assert len(config.agents) == 2
        assert config.entry_point == mock_agent1
        assert config.max_handoffs == 10
        assert config.max_iterations == 20
        assert config.execution_timeout == 300.0
        assert config.node_timeout == 120.0

    def test_custom_guardrails(self):
        """Test custom guardrail configuration."""
        mock_agent = MagicMock()

        config = SwarmConfig(
            agents=[mock_agent],
            entry_point=mock_agent,
            max_handoffs=5,
            max_iterations=10,
            execution_timeout=60.0,
            node_timeout=30.0,
        )
        assert config.max_handoffs == 5
        assert config.max_iterations == 10
        assert config.execution_timeout == 60.0
        assert config.node_timeout == 30.0


class TestAgentFactory:
    """Tests for AgentFactory."""

    def test_create_model(self):
        """Test model creation."""
        factory = AgentFactory()

        with patch("core_agents.factory.OpenAIModel") as MockModel:  # noqa: N806
            mock_model = MagicMock()
            MockModel.return_value = mock_model

            config = ModelConfig(
                base_url="http://test:8000/v1",
                model_id="test-model",
            )
            factory.create_model(config)

            MockModel.assert_called_once()
            call_kwargs = MockModel.call_args
            assert call_kwargs.kwargs["model_id"] == "test-model"
            assert "test:8000" in str(call_kwargs.kwargs["client_args"]["base_url"])

    def test_model_caching(self):
        """Test that models are cached."""
        factory = AgentFactory()

        with patch("core_agents.factory.OpenAIModel") as MockModel:  # noqa: N806
            mock_model = MagicMock()
            MockModel.return_value = mock_model

            config = ModelConfig(
                base_url="http://test:8000/v1",
                model_id="test-model",
            )

            # Create same model twice
            model1 = factory.create_model(config)
            model2 = factory.create_model(config)

            # Should only create once
            assert MockModel.call_count == 1
            assert model1 is model2

    def test_create_agent(self):
        """Test agent creation."""
        factory = AgentFactory(default_observability=False)

        with patch("core_agents.factory.OpenAIModel") as MockModel:  # noqa: N806, SIM117
            with patch("core_agents.factory.Agent") as MockAgent:  # noqa: N806
                mock_model = MagicMock()
                MockModel.return_value = mock_model
                mock_agent = MagicMock()
                MockAgent.return_value = mock_agent

                config = AgentConfig(
                    name="test-agent",
                    description="Test agent",
                    system_prompt="You are a test.",
                    tools=[MagicMock()],
                    enable_observability=False,
                )

                factory.create_agent(config)

                MockAgent.assert_called_once()
                call_kwargs = MockAgent.call_args.kwargs
                assert call_kwargs["name"] == "test-agent"
                assert call_kwargs["description"] == "Test agent"
                assert call_kwargs["system_prompt"] == "You are a test."
                assert len(call_kwargs["tools"]) == 1

    def test_create_agent_with_hooks_factory(self):
        """Test agent creation with hooks factory."""
        factory = AgentFactory(default_observability=False)

        mock_hooks = [MagicMock()]
        hooks_factory = MagicMock(return_value=mock_hooks)

        with patch("core_agents.factory.OpenAIModel"):  # noqa: SIM117
            with patch("core_agents.factory.Agent") as MockAgent:  # noqa: N806
                config = AgentConfig(
                    name="test",
                    description="test",
                    system_prompt="test",
                    hooks_factory=hooks_factory,
                    enable_observability=False,
                )

                factory.create_agent(config)

                hooks_factory.assert_called_once()
                call_kwargs = MockAgent.call_args.kwargs
                assert call_kwargs["hooks"] == mock_hooks

    def test_create_agent_with_mcp_clients(self):
        """Test agent creation with MCP clients."""
        factory = AgentFactory(default_observability=False)

        mock_mcp = MagicMock()
        mock_tool = MagicMock()

        with patch("core_agents.factory.OpenAIModel"):  # noqa: SIM117
            with patch("core_agents.factory.Agent") as MockAgent:  # noqa: N806
                config = AgentConfig(
                    name="test",
                    description="test",
                    system_prompt="test",
                    tools=[mock_tool],
                    mcp_clients=[mock_mcp],
                    enable_observability=False,
                )

                factory.create_agent(config)

                call_kwargs = MockAgent.call_args.kwargs
                assert len(call_kwargs["tools"]) == 2
                assert mock_tool in call_kwargs["tools"]
                assert mock_mcp in call_kwargs["tools"]

    def test_create_agent_with_observability(self):
        """Test agent creation with observability enabled."""
        factory = AgentFactory(default_observability=True)

        with patch("core_agents.factory.OpenAIModel"):  # noqa: SIM117
            with patch("core_agents.factory.Agent") as MockAgent:  # noqa: N806
                # Patch where it's imported from (inside the function)
                with patch("core_agents.observability.create_observability_hooks") as MockObs:  # noqa: N806
                    mock_obs_hooks = MagicMock()
                    MockObs.return_value = mock_obs_hooks

                    config = AgentConfig(
                        name="test",
                        description="test",
                        system_prompt="test",
                        enable_observability=True,
                    )

                    factory.create_agent(config)

                    MockObs.assert_called_once_with(enable_debug_logging=False)
                    call_kwargs = MockAgent.call_args.kwargs
                    assert mock_obs_hooks in call_kwargs["hooks"]

    def test_create_swarm(self):
        """Test swarm creation."""
        factory = AgentFactory()

        mock_agent1 = MagicMock()
        mock_agent1.name = "agent1"
        mock_agent2 = MagicMock()
        mock_agent2.name = "agent2"

        with patch("core_agents.factory.Swarm") as MockSwarm:  # noqa: N806
            mock_swarm = MagicMock()
            MockSwarm.return_value = mock_swarm

            config = SwarmConfig(
                agents=[mock_agent1, mock_agent2],
                entry_point=mock_agent1,
                max_handoffs=5,
            )

            factory.create_swarm(config)

            MockSwarm.assert_called_once()
            call_args = MockSwarm.call_args
            assert call_args.args[0] == [mock_agent1, mock_agent2]
            assert call_args.kwargs["entry_point"] == mock_agent1
            assert call_args.kwargs["max_handoffs"] == 5


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_agent_factory_singleton(self):
        """Test that get_agent_factory returns singleton."""
        factory1 = get_agent_factory()
        factory2 = get_agent_factory()
        assert factory1 is factory2

    def test_create_model_function(self):
        """Test create_model convenience function."""
        with patch("core_agents.factory.get_agent_factory") as mock_get:
            mock_factory = MagicMock()
            mock_get.return_value = mock_factory

            config = ModelConfig()
            create_model(config)

            mock_factory.create_model.assert_called_once_with(config)

    def test_create_agent_function(self):
        """Test create_agent convenience function."""
        with patch("core_agents.factory.get_agent_factory") as mock_get:
            mock_factory = MagicMock()
            mock_get.return_value = mock_factory

            config = AgentConfig(
                name="test",
                description="test",
                system_prompt="test",
            )
            create_agent(config)

            mock_factory.create_agent.assert_called_once_with(config)

    def test_create_swarm_function(self):
        """Test create_swarm convenience function."""
        with patch("core_agents.factory.get_agent_factory") as mock_get:
            mock_factory = MagicMock()
            mock_get.return_value = mock_factory

            mock_agent = MagicMock()
            config = SwarmConfig(agents=[mock_agent], entry_point=mock_agent)
            create_swarm(config)

            mock_factory.create_swarm.assert_called_once_with(config)

    def test_quick_agent_function(self):
        """Test quick_agent convenience function."""
        with patch("core_agents.factory.get_agent_factory") as mock_get:
            mock_factory = MagicMock()
            mock_get.return_value = mock_factory

            quick_agent(
                name="quick",
                description="Quick agent",
                system_prompt="Be quick.",
                tools=[],
            )

            mock_factory.create_agent.assert_called_once()
            config = mock_factory.create_agent.call_args.args[0]
            assert config.name == "quick"
            assert config.description == "Quick agent"
