"""Tests for NewsDigestSyndicate."""

import pytest

from kubani.syndicates.news_digest import NewsDigestSyndicate


class TestNewsDigestSyndicate:
    """Test NewsDigestSyndicate basic functionality."""

    def test_import(self):
        """Test that syndicate can be imported."""
        from kubani.syndicates import NewsDigestSyndicate

        assert NewsDigestSyndicate is not None

    def test_instantiation(self):
        """Test that syndicate can be instantiated."""
        syndicate = NewsDigestSyndicate()
        assert syndicate is not None

    def test_name(self):
        """Test syndicate has correct name."""
        syndicate = NewsDigestSyndicate()
        assert syndicate.name == "news-digest"

    def test_agents_defined(self):
        """Test that agents are defined."""
        syndicate = NewsDigestSyndicate()
        assert len(syndicate.agents) == 3

    def test_agent_names(self):
        """Test that correct agents are included."""
        syndicate = NewsDigestSyndicate()
        agent_names = [a.__name__ for a in syndicate.agents]
        assert "FeedCollectorAgent" in agent_names
        assert "ContentAnalystAgent" in agent_names
        assert "DigestPublisherAgent" in agent_names

    def test_get_agent(self):
        """Test getting agent instances."""
        from kubani.agents.feed_collector import FeedCollectorAgent

        syndicate = NewsDigestSyndicate()
        agent = syndicate.get_agent(FeedCollectorAgent)
        assert agent is not None
        assert isinstance(agent, FeedCollectorAgent)

    def test_get_agent_singleton(self):
        """Test that get_agent returns same instance."""
        from kubani.agents.feed_collector import FeedCollectorAgent

        syndicate = NewsDigestSyndicate()
        agent1 = syndicate.get_agent(FeedCollectorAgent)
        agent2 = syndicate.get_agent(FeedCollectorAgent)
        assert agent1 is agent2

    def test_get_invalid_agent_raises(self):
        """Test that getting non-member agent raises."""
        from kubani.agents.event_classifier import EventClassifierAgent

        syndicate = NewsDigestSyndicate()
        with pytest.raises(ValueError):
            syndicate.get_agent(EventClassifierAgent)

    def test_config_loaded(self):
        """Test that config is loaded from config.yaml."""
        syndicate = NewsDigestSyndicate()
        assert syndicate.config is not None
        assert "schedule" in syndicate.config

    def test_task_queue(self):
        """Test task queue configuration."""
        syndicate = NewsDigestSyndicate()
        assert syndicate.get_task_queue() == "news-digest"
