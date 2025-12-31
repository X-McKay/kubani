"""
Tests for core_agents.communication.a2a module.

Tests the agent registry, capability definitions, and registration functions.
"""

import pytest


class TestAgentCapability:
    """Tests for AgentCapability dataclass."""

    def test_creation(self, sample_capability):
        """Test that AgentCapability can be created."""
        assert sample_capability.name == "sample-capability"
        assert sample_capability.description == "A sample capability for testing"
        assert "sample" in sample_capability.tags

    def test_to_a2a_skill_conversion(self, sample_capability):
        """Test conversion to A2A AgentSkill format."""
        # This test will skip if a2a types aren't available
        pytest.importorskip("a2a.types")

        skill = sample_capability.to_a2a_skill()

        assert skill.id == sample_capability.name
        assert skill.name == sample_capability.name
        assert skill.description == sample_capability.description
        assert skill.tags == sample_capability.tags

    def test_default_schemas(self):
        """Test that schemas default to empty dicts."""
        from core_agents.communication import AgentCapability

        cap = AgentCapability(name="test", description="Test")

        assert cap.input_schema == {}
        assert cap.output_schema == {}
        assert cap.tags == []


class TestAgentInfo:
    """Tests for AgentInfo dataclass."""

    def test_creation(self, sample_agent_info):
        """Test that AgentInfo can be created."""
        assert sample_agent_info.id == "test-agent"
        assert sample_agent_info.name == "Test Agent"
        assert len(sample_agent_info.capabilities) == 2

    def test_a2a_url_with_service_name(self, sample_agent_info):
        """Test a2a_url property with Kubernetes service name."""
        url = sample_agent_info.a2a_url

        assert url == "http://test-agent.ai-agents.svc.cluster.local:9000/"

    def test_a2a_url_with_full_url(self):
        """Test a2a_url property when endpoint is already a URL."""
        from core_agents.communication import AgentInfo

        agent = AgentInfo(
            id="test",
            name="Test",
            description="Test",
            endpoint="http://example.com:8080",
            capabilities=[],
        )

        assert agent.a2a_url == "http://example.com:8080"

    def test_get_a2a_skills(self, sample_agent_info):
        """Test conversion of capabilities to A2A skills."""
        pytest.importorskip("a2a.types")

        skills = sample_agent_info.get_a2a_skills()

        assert len(skills) == 2
        assert skills[0].name == "test-capability"

    def test_registered_at_auto_set(self, sample_agent_info):
        """Test that registered_at is automatically set."""
        assert sample_agent_info.registered_at is not None
        # Should be ISO format
        assert "T" in sample_agent_info.registered_at


class TestAgentRegistry:
    """Tests for AgentRegistry class."""

    def test_starts_empty(self):
        """Test that registry starts with no agents."""
        from core_agents.communication import AgentRegistry

        registry = AgentRegistry()

        assert len(registry.list_agents()) == 0

    def test_register_agent(self, sample_agent_info):
        """Test registering an agent."""
        from core_agents.communication import AgentRegistry

        registry = AgentRegistry()
        registered = registry.register_agent(sample_agent_info)

        assert registered.id == sample_agent_info.id
        assert len(registry.list_agents()) == 1

    def test_get_agent_by_id(self, sample_agent_info):
        """Test getting an agent by ID."""
        from core_agents.communication import AgentRegistry

        registry = AgentRegistry()
        registry.register_agent(sample_agent_info)

        agent = registry.get_agent("test-agent")

        assert agent is not None
        assert agent.id == "test-agent"

    def test_get_nonexistent_agent(self):
        """Test getting an agent that doesn't exist."""
        from core_agents.communication import AgentRegistry

        registry = AgentRegistry()

        assert registry.get_agent("nonexistent") is None

    def test_unregister_agent(self, sample_agent_info):
        """Test unregistering an agent."""
        from core_agents.communication import AgentRegistry

        registry = AgentRegistry()
        registry.register_agent(sample_agent_info)

        result = registry.unregister_agent("test-agent")

        assert result is True
        assert len(registry.list_agents()) == 0

    def test_unregister_nonexistent_agent(self):
        """Test unregistering an agent that doesn't exist."""
        from core_agents.communication import AgentRegistry

        registry = AgentRegistry()

        result = registry.unregister_agent("nonexistent")

        assert result is False

    def test_find_agents_for_capability(self, sample_agent_info):
        """Test finding agents by capability."""
        from core_agents.communication import AgentRegistry

        registry = AgentRegistry()
        registry.register_agent(sample_agent_info)

        agents = registry.find_agents_for("test-capability")

        assert len(agents) == 1
        assert agents[0].id == "test-agent"

    def test_find_agent_for_capability(self, sample_agent_info):
        """Test finding first agent for capability."""
        from core_agents.communication import AgentRegistry

        registry = AgentRegistry()
        registry.register_agent(sample_agent_info)

        agent = registry.find_agent_for("test-capability")

        assert agent is not None
        assert agent.id == "test-agent"

    def test_find_agent_for_nonexistent_capability(self, sample_agent_info):
        """Test finding agent for capability that doesn't exist."""
        from core_agents.communication import AgentRegistry

        registry = AgentRegistry()
        registry.register_agent(sample_agent_info)

        agent = registry.find_agent_for("nonexistent-capability")

        assert agent is None

    def test_capability_index_rebuilt_on_register(self, sample_agent_info):
        """Test that capability index is rebuilt when agents register."""
        from core_agents.communication import AgentCapability, AgentInfo, AgentRegistry

        registry = AgentRegistry()
        registry.register_agent(sample_agent_info)

        # Register another agent with overlapping capability
        agent2 = AgentInfo(
            id="agent2",
            name="Agent 2",
            description="Another agent",
            endpoint="agent2.svc",
            capabilities=[
                AgentCapability(
                    name="test-capability",  # Same as sample_agent_info
                    description="Same capability",
                ),
            ],
        )
        registry.register_agent(agent2)

        agents = registry.find_agents_for("test-capability")

        assert len(agents) == 2

    def test_get_capability(self, sample_agent_info):
        """Test getting a specific capability from an agent."""
        from core_agents.communication import AgentRegistry

        registry = AgentRegistry()
        registry.register_agent(sample_agent_info)

        cap = registry.get_capability("test-agent", "test-capability")

        assert cap is not None
        assert cap.name == "test-capability"

    def test_get_capability_nonexistent(self, sample_agent_info):
        """Test getting capability that doesn't exist."""
        from core_agents.communication import AgentRegistry

        registry = AgentRegistry()
        registry.register_agent(sample_agent_info)

        cap = registry.get_capability("test-agent", "nonexistent")

        assert cap is None


class TestGetAgentRegistry:
    """Tests for get_agent_registry() singleton function."""

    def test_returns_registry(self):
        """Test that get_agent_registry returns a registry."""
        from core_agents.communication import get_agent_registry

        registry = get_agent_registry()

        assert registry is not None

    def test_returns_same_instance(self):
        """Test that get_agent_registry returns the same instance."""
        from core_agents.communication import get_agent_registry

        registry1 = get_agent_registry()
        registry2 = get_agent_registry()

        assert registry1 is registry2


class TestRegisterAgentOnStartup:
    """Tests for register_agent_on_startup() function."""

    @pytest.mark.asyncio
    async def test_registers_with_global_registry(self, sample_agent_info):
        """Test that agent is registered with global registry."""
        from core_agents.communication import (
            get_agent_registry,
            register_agent_on_startup,
        )

        # Clear registry first
        registry = get_agent_registry()
        registry._agents.clear()
        registry._capability_index.clear()

        await register_agent_on_startup(sample_agent_info)

        agent = registry.get_agent("test-agent")
        assert agent is not None
        assert agent.id == "test-agent"

    @pytest.mark.asyncio
    async def test_returns_registered_info(self, sample_agent_info):
        """Test that registration returns the agent info."""
        from core_agents.communication import (
            get_agent_registry,
            register_agent_on_startup,
        )

        # Clear registry
        registry = get_agent_registry()
        registry._agents.clear()

        result = await register_agent_on_startup(sample_agent_info)

        assert result.id == sample_agent_info.id

    def test_sync_version_works(self, sample_agent_info):
        """Test synchronous registration version."""
        from core_agents.communication import (
            get_agent_registry,
            register_agent_on_startup_sync,
        )

        # Clear registry
        registry = get_agent_registry()
        registry._agents.clear()

        result = register_agent_on_startup_sync(sample_agent_info)

        assert result.id == sample_agent_info.id
        assert registry.get_agent("test-agent") is not None


class TestNoHardcodedAgents:
    """Tests verifying no hardcoded agents in registry."""

    def test_registry_starts_empty(self):
        """Test that new registry has no pre-registered agents."""
        from core_agents.communication import AgentRegistry

        registry = AgentRegistry()

        assert len(registry.list_agents()) == 0
        assert len(registry._capability_index) == 0

    def test_no_known_agents_class_var(self):
        """Test that KNOWN_AGENTS is not in AgentRegistry."""
        from core_agents.communication import AgentRegistry

        assert not hasattr(AgentRegistry, "KNOWN_AGENTS") or AgentRegistry.KNOWN_AGENTS == {}
