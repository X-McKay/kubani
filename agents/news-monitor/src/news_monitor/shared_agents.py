"""
Shared Agent Instances for News Monitor.

Implements the singleton/cached agent pattern recommended for Temporal activities.
Instead of creating new agent instances for every activity invocation, we maintain
shared instances that can be reused across multiple executions.

This improves efficiency by:
1. Avoiding repeated agent initialization overhead
2. Maintaining warm MCP connections
3. Enabling better memory utilization across invocations

Usage:
    from news_monitor.shared_agents import get_shared_agents, SharedAgents

    # In activity
    agents = get_shared_agents()
    result = await agents.collector.collect()
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Global singleton instance
_shared_agents: Optional["SharedAgents"] = None


@dataclass
class SharedAgents:
    """
    Container for shared agent instances.

    Provides lazy initialization of agents to avoid import-time side effects.
    """

    _collector: Optional["NewsCollectorAgent"] = None
    _analyst: Optional["NewsAnalystAgent"] = None
    _publisher: Optional["NewsPublisherAgent"] = None

    # Configuration
    collector_max_age_hours: int = 24
    analyst_parallel_workers: int = 4

    @property
    def collector(self) -> "NewsCollectorAgent":
        """Get or create the shared collector agent."""
        if self._collector is None:
            from news_monitor.federated import NewsCollectorAgent

            self._collector = NewsCollectorAgent(max_age_hours=self.collector_max_age_hours)
            logger.info("Created shared NewsCollectorAgent")
        return self._collector

    @property
    def analyst(self) -> "NewsAnalystAgent":
        """Get or create the shared analyst agent."""
        if self._analyst is None:
            from news_monitor.federated import NewsAnalystAgent

            self._analyst = NewsAnalystAgent(parallel_workers=self.analyst_parallel_workers)
            logger.info("Created shared NewsAnalystAgent")
        return self._analyst

    @property
    def publisher(self) -> "NewsPublisherAgent":
        """Get or create the shared publisher agent."""
        if self._publisher is None:
            from news_monitor.federated import NewsPublisherAgent

            self._publisher = NewsPublisherAgent()
            logger.info("Created shared NewsPublisherAgent")
        return self._publisher

    def configure_collector(self, max_age_hours: int) -> None:
        """
        Configure the collector for a specific run.

        This allows activities to customize the collector without
        creating a new instance.
        """
        if self._collector is not None:
            self._collector.max_age_hours = max_age_hours
        self.collector_max_age_hours = max_age_hours

    def reset(self) -> None:
        """Reset all shared agents (useful for testing)."""
        self._collector = None
        self._analyst = None
        self._publisher = None
        logger.info("Reset shared agents")


def get_shared_agents() -> SharedAgents:
    """
    Get the global shared agents instance.

    Creates the instance on first call (lazy initialization).
    """
    global _shared_agents
    if _shared_agents is None:
        _shared_agents = SharedAgents()
        logger.info("Initialized shared agents singleton")
    return _shared_agents


def reset_shared_agents() -> None:
    """Reset the shared agents (useful for testing)."""
    global _shared_agents
    if _shared_agents is not None:
        _shared_agents.reset()
    _shared_agents = None
