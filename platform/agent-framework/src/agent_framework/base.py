"""AgentBase - Base class for all agents."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from agent_framework.config import AgentConfig, RunMode

if TYPE_CHECKING:
    from agent_framework.trace import ExecutionTrace

logger = logging.getLogger(__name__)


class AgentBase(ABC):
    """
    Base class for all Kubani agents.

    Provides standard lifecycle management and configuration.
    Agents inherit from this and implement the abstract methods.

    Lifecycle:
        1. __init__(config) - Set up configuration
        2. initialize() - Async setup (connections, resources)
        3. run() - Main execution loop
        4. shutdown() - Cleanup resources

    Example:
        class MyAgent(AgentBase):
            async def initialize(self) -> None:
                self.client = await setup_client()

            async def run(self) -> None:
                while self.running:
                    await self.process_next()

            async def shutdown(self) -> None:
                await self.client.close()
    """

    def __init__(self, config: AgentConfig) -> None:
        """Initialize agent with configuration."""
        self.config = config
        self.name = config.name
        self.version = config.version
        self._running = False
        self._initialized = False

        # Will be set by mixins
        self._mcp_client: Any = None
        self._skill_loader: Any = None
        self._memory: Any = None
        self._tracer: Any = None

    @property
    def running(self) -> bool:
        """Whether the agent is currently running."""
        return self._running

    @property
    def mode(self) -> RunMode:
        """Current execution mode."""
        return self.config.mode

    async def initialize(self) -> None:
        """
        Initialize the agent (async setup).

        Override this to set up connections, load resources, etc.
        Called once before run().
        """
        self._initialized = True
        logger.info(f"Agent {self.name} initialized in {self.mode.value} mode")

    @abstractmethod
    async def run(self) -> None:
        """
        Main agent execution.

        Override this to implement the agent's main logic.
        For long-running agents, check self.running in the loop.
        """
        pass

    async def shutdown(self) -> None:
        """
        Shutdown the agent (cleanup).

        Override this to close connections, flush buffers, etc.
        Called after run() completes or on interrupt.
        """
        self._running = False
        logger.info(f"Agent {self.name} shutdown")

    async def handle_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Handle a single event/trigger.

        Override this for event-driven agents.
        Default implementation raises NotImplementedError.

        Args:
            event: Event data

        Returns:
            Result of handling the event
        """
        raise NotImplementedError(
            f"Agent {self.name} does not implement handle_event(). "
            "Override this method for event-driven behavior."
        )

    async def execute_skill(
        self,
        skill_name: str,
        context: dict[str, Any] | None = None,
    ) -> ExecutionTrace:
        """
        Execute a skill by name.

        Requires SkillLoaderMixin to be applied.

        Args:
            skill_name: Name of the skill to execute
            context: Context to pass to the skill

        Returns:
            Execution trace with results
        """
        if self._skill_loader is None:
            raise RuntimeError(
                "SkillLoaderMixin not applied. Add SkillLoaderMixin to your agent class."
            )
        return await self._skill_loader.execute(skill_name, context or {})

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} mode={self.mode.value}>"
