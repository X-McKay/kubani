"""
Passive Observers for the Learning Agent.

These observers monitor various data sources without requiring
explicit callbacks from other agents:

- TemporalObserver: Polls completed workflows from Temporal
- EventCollector: Subscribes to Redis event bus
- DiscordMonitor: Watches Discord channels for agent outputs
"""

from learning_agent.observers.discord import AgentMessage, DiscordMonitor, ReactionSummary
from learning_agent.observers.events import AgentEvent, EventCollector, ExecutionChain
from learning_agent.observers.temporal import WorkflowObserver, WorkflowResult

__all__ = [
    # Temporal
    "WorkflowObserver",
    "WorkflowResult",
    # Events
    "EventCollector",
    "AgentEvent",
    "ExecutionChain",
    # Discord
    "DiscordMonitor",
    "AgentMessage",
    "ReactionSummary",
]
