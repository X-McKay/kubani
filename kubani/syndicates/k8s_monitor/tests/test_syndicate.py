"""Tests for K8sMonitorSyndicate."""

import pytest

from syndicates.k8s_monitor import K8sMonitorSyndicate


class TestK8sMonitorSyndicate:
    """Test K8sMonitorSyndicate basic functionality."""

    def test_import(self):
        """Test that syndicate can be imported."""
        from syndicates import K8sMonitorSyndicate

        assert K8sMonitorSyndicate is not None

    def test_instantiation(self):
        """Test that syndicate can be instantiated."""
        syndicate = K8sMonitorSyndicate()
        assert syndicate is not None

    def test_name(self):
        """Test syndicate has correct name."""
        syndicate = K8sMonitorSyndicate()
        assert syndicate.name == "k8s-monitor"

    def test_agents_defined(self):
        """Test that agents are defined."""
        syndicate = K8sMonitorSyndicate()
        assert len(syndicate.agents) == 3

    def test_agent_names(self):
        """Test that correct agents are included."""
        syndicate = K8sMonitorSyndicate()
        agent_names = [a.__name__ for a in syndicate.agents]
        assert "EventClassifierAgent" in agent_names
        assert "RemediatorAgent" in agent_names
        assert "SkillLearnerAgent" in agent_names

    def test_get_agent(self):
        """Test getting agent instances."""
        from agents.event_classifier import EventClassifierAgent

        syndicate = K8sMonitorSyndicate()
        agent = syndicate.get_agent(EventClassifierAgent)
        assert agent is not None
        assert isinstance(agent, EventClassifierAgent)

    def test_get_agent_singleton(self):
        """Test that get_agent returns same instance."""
        from agents.event_classifier import EventClassifierAgent

        syndicate = K8sMonitorSyndicate()
        agent1 = syndicate.get_agent(EventClassifierAgent)
        agent2 = syndicate.get_agent(EventClassifierAgent)
        assert agent1 is agent2

    def test_get_invalid_agent_raises(self):
        """Test that getting non-member agent raises."""
        from agents.feed_collector import FeedCollectorAgent

        syndicate = K8sMonitorSyndicate()
        with pytest.raises(ValueError):
            syndicate.get_agent(FeedCollectorAgent)

    def test_config_loaded(self):
        """Test that config is loaded from config.yaml."""
        syndicate = K8sMonitorSyndicate()
        assert syndicate.config is not None
        assert "schedule" in syndicate.config

    def test_task_queue(self):
        """Test task queue configuration."""
        syndicate = K8sMonitorSyndicate()
        assert syndicate.get_task_queue() == "k8s-monitor"
