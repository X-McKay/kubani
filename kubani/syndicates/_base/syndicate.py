"""
Base class for Kubani Syndicates.

Syndicates are missions that orchestrate multiple agents to accomplish objectives.
They coordinate agent interactions, manage workflows, and handle handoffs.

    kubani/syndicates/k8s-monitor/
    ├── syndicate.py       # Syndicate class (extends Syndicate)
    ├── config.yaml        # Agent bindings, schedules
    ├── workflows/         # Temporal workflows
    └── tests/             # Syndicate tests

Usage:
    from syndicates._base import Syndicate
    from agents.sentinel import SentinelAgent
    from agents.healer import HealerAgent

    class K8sMonitorSyndicate(Syndicate):
        '''Keep the Kubernetes cluster healthy.'''

        agents = [SentinelAgent, HealerAgent]

        async def run(self):
            sentinel = self.get_agent(SentinelAgent)
            healer = self.get_agent(HealerAgent)

            async for event in sentinel.watch():
                classification = await sentinel.run(f"Classify: {event}")
                if classification.needs_remediation:
                    await healer.run(f"Remediate: {classification.summary}")

    syndicate = K8sMonitorSyndicate()
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypeVar

import yaml

from kubani.agents._base.agent import KubaniAgent
from kubani.framework.config import get_config
from kubani.framework.events import EventType, get_event_bus

logger = logging.getLogger(__name__)

# Type variable for agent classes
T = TypeVar("T", bound=KubaniAgent)


class Syndicate(ABC):
    """
    Base class for Kubani syndicates.

    Syndicates orchestrate multiple agents to accomplish missions.
    They define:
    - Which agents are part of the syndicate
    - How agents hand off work to each other
    - Workflows for complex multi-agent tasks

    Subclasses must:
    - Define `agents` class variable with agent classes
    - Implement `run()` method for the main orchestration logic
    """

    # List of agent classes that belong to this syndicate
    agents: list[type[KubaniAgent]] = []

    # Override in subclass to specify syndicate directory
    SYNDICATE_DIR: Path | None = None

    def __init__(self, syndicate_dir: Path | None = None):
        """
        Initialize the syndicate.

        Args:
            syndicate_dir: Override the syndicate directory. If not provided,
                          uses SYNDICATE_DIR or auto-detects from subclass location.
        """
        self._syndicate_dir = self._resolve_syndicate_dir(syndicate_dir)
        self._config: dict[str, Any] | None = None
        self._agent_instances: dict[type[KubaniAgent], KubaniAgent] = {}
        self._running = False

    def _resolve_syndicate_dir(self, syndicate_dir: Path | None) -> Path:
        """Resolve the syndicate directory."""
        if syndicate_dir:
            return syndicate_dir
        if self.SYNDICATE_DIR:
            return self.SYNDICATE_DIR

        # Auto-detect from subclass location
        import inspect

        subclass_file = inspect.getfile(self.__class__)
        return Path(subclass_file).parent

    @property
    def config(self) -> dict[str, Any]:
        """Get syndicate configuration from config.yaml."""
        if self._config is None:
            self._config = self._load_config()
        return self._config

    @property
    def name(self) -> str:
        """Get syndicate name from config."""
        return self.config.get("name", self.__class__.__name__)

    @property
    def description(self) -> str:
        """Get syndicate description from config."""
        return self.config.get("description", "")

    @property
    def version(self) -> str:
        """Get syndicate version from config."""
        return self.config.get("version", "1.0.0")

    @property
    def schedule(self) -> dict[str, Any] | None:
        """Get Temporal schedule configuration."""
        return self.config.get("schedule")

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from config.yaml."""
        config_path = self._syndicate_dir / "config.yaml"

        if not config_path.exists():
            logger.warning(f"No config.yaml found at {config_path}")
            return {}

        try:
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load config.yaml: {e}")
            return {}

    def get_agent(self, agent_class: type[T]) -> T:
        """
        Get an instance of an agent.

        Creates the agent on first access. Agents are singletons within a syndicate.

        Args:
            agent_class: The agent class to get an instance of

        Returns:
            Agent instance

        Raises:
            ValueError: If the agent class is not part of this syndicate
        """
        if agent_class not in self.agents:
            raise ValueError(f"Agent {agent_class.__name__} is not part of {self.name}")

        if agent_class not in self._agent_instances:
            self._agent_instances[agent_class] = agent_class()

        return self._agent_instances[agent_class]  # type: ignore

    @abstractmethod
    async def run(self) -> None:
        """
        Main orchestration logic for the syndicate.

        This method should:
        - Get agent instances using get_agent()
        - Coordinate agent work
        - Handle handoffs between agents
        - Manage the overall mission

        Override in subclass.
        """
        ...

    async def start(self) -> None:
        """
        Start the syndicate.

        Publishes a SYNDICATE_STARTED event and calls run().
        """
        self._running = True

        try:
            bus = await get_event_bus()
            await bus.publish(
                EventType.SYNDICATE_STARTED,
                {
                    "syndicate": self.name,
                    "version": self.version,
                    "agents": [a.__name__ for a in self.agents],
                },
                source=self.name,
            )

            logger.info(f"Starting syndicate: {self.name}")
            await self.run()

        except Exception as e:
            logger.error(f"Syndicate {self.name} failed: {e}", exc_info=e)
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """
        Stop the syndicate.

        Publishes a SYNDICATE_STOPPED event.
        """
        if not self._running:
            return

        self._running = False

        try:
            bus = await get_event_bus()
            await bus.publish(
                EventType.SYNDICATE_STOPPED,
                {"syndicate": self.name},
                source=self.name,
            )
        except Exception as e:
            logger.warning(f"Failed to publish stop event: {e}")

        logger.info(f"Stopped syndicate: {self.name}")

    async def handoff(
        self,
        from_agent: KubaniAgent,
        to_agent: KubaniAgent,
        context: dict[str, Any],
        reason: str,
    ) -> None:
        """
        Hand off work from one agent to another.

        Publishes a SYNDICATE_AGENT_HANDOFF event.

        Args:
            from_agent: Agent handing off
            to_agent: Agent receiving the handoff
            context: Context for the handoff
            reason: Reason for the handoff
        """
        try:
            bus = await get_event_bus()
            await bus.publish(
                EventType.SYNDICATE_AGENT_HANDOFF,
                {
                    "syndicate": self.name,
                    "from_agent": from_agent.name,
                    "to_agent": to_agent.name,
                    "context": context,
                    "reason": reason,
                },
                source=self.name,
            )
        except Exception as e:
            logger.warning(f"Failed to publish handoff event: {e}")

        logger.debug(f"Handoff: {from_agent.name} -> {to_agent.name}: {reason}")

    def get_task_queue(self) -> str:
        """Get the Temporal task queue name for this syndicate."""
        return self.config.get("task_queue", self.name)

    def get_temporal_config(self) -> dict[str, Any]:
        """Get Temporal workflow configuration."""
        config = get_config()
        return {
            "namespace": config.temporal.namespace,
            "task_queue": self.get_task_queue(),
            "host": config.temporal.host,
        }
