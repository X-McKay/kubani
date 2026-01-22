"""Tests for AgentBase."""

import pytest
from agent_framework import AgentBase
from agent_framework.config import AgentConfig, RunMode


class TestAgent(AgentBase):
    """Test agent implementation."""

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.events_handled = []

    async def run(self) -> None:
        """Simple run that exits immediately."""
        pass

    async def handle_event(self, event: dict) -> dict:
        """Track handled events."""
        self.events_handled.append(event)
        return {"handled": True}


class TestAgentBase:
    """Tests for AgentBase class."""

    def test_agent_creation(self):
        """Test agent can be created with config."""
        config = AgentConfig(name="test-agent", version="1.0.0")
        agent = TestAgent(config)

        assert agent.name == "test-agent"
        assert agent.version == "1.0.0"
        assert agent.mode == RunMode.LOCAL
        assert not agent.running

    @pytest.mark.asyncio
    async def test_agent_lifecycle(self):
        """Test agent initialize/run/shutdown cycle."""
        config = AgentConfig(name="test-agent")
        agent = TestAgent(config)

        # Initialize
        await agent.initialize()
        assert agent._initialized

        # Run
        await agent.run()

        # Shutdown
        await agent.shutdown()
        assert not agent.running

    @pytest.mark.asyncio
    async def test_handle_event(self):
        """Test event handling."""
        config = AgentConfig(name="test-agent")
        agent = TestAgent(config)
        await agent.initialize()

        event = {"type": "test", "data": "hello"}
        result = await agent.handle_event(event)

        assert result == {"handled": True}
        assert event in agent.events_handled
