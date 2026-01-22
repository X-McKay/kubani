"""AgentRunner - Run agents in local or cluster mode."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import TYPE_CHECKING, Any

from agent_framework.config import AgentConfig, RunMode
from agent_framework.trace import ExecutionTrace, SpanKind, TraceSpan

if TYPE_CHECKING:
    from agent_framework.base import AgentBase

logger = logging.getLogger(__name__)


class AgentRunner:
    """
    Run agents in local or cluster mode.

    Provides a unified entry point for agent execution, handling:
    - Lifecycle management (initialize, run, shutdown)
    - Signal handling for graceful shutdown
    - Mode-specific behavior (local vs cluster)

    Example:
        # Local mode
        runner = AgentRunner(MyAgent, AgentConfig(name="my-agent"))
        await runner.run_local()

        # Single event
        result = await runner.handle_event({"type": "pod_crash", ...})

        # Cluster mode (Temporal worker)
        await runner.run_cluster()
    """

    def __init__(
        self,
        agent_class: type[AgentBase],
        config: AgentConfig,
    ):
        """
        Initialize AgentRunner.

        Args:
            agent_class: The agent class to instantiate
            config: Agent configuration
        """
        self.agent_class = agent_class
        self.config = config
        self._agent: AgentBase | None = None
        self._shutdown_event: asyncio.Event | None = None

    @property
    def agent(self) -> AgentBase:
        """Get the agent instance (creates if needed)."""
        if self._agent is None:
            self._agent = self.agent_class(self.config)
        return self._agent

    async def run_local(self) -> None:
        """
        Run agent in local mode (single process).

        Sets up signal handlers for graceful shutdown.
        """
        self._shutdown_event = asyncio.Event()

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self._handle_shutdown()),
            )

        try:
            logger.info(f"Starting agent {self.config.name} in local mode")

            # Initialize
            await self.agent.initialize()
            self.agent._running = True

            # Run until shutdown
            run_task = asyncio.create_task(self.agent.run())
            shutdown_task = asyncio.create_task(self._shutdown_event.wait())

            done, pending = await asyncio.wait(
                [run_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        finally:
            await self.agent.shutdown()
            logger.info(f"Agent {self.config.name} stopped")

    async def _handle_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        if self._shutdown_event:
            self._shutdown_event.set()

    async def handle_event(
        self,
        event: dict[str, Any],
        trace: bool = True,
    ) -> ExecutionTrace:
        """
        Handle a single event and return trace.

        Useful for testing and one-off executions.

        Args:
            event: Event data to handle
            trace: Whether to record trace

        Returns:
            Execution trace with results
        """
        # Create trace
        exec_trace = ExecutionTrace(
            execution_type="agent",
            name=self.config.name,
            version=self.config.version,
            input=event,
        )

        # Create span
        span = TraceSpan(
            name=f"agent.{self.config.name}.handle_event",
            kind=SpanKind.AGENT,
            attributes={
                "event.type": event.get("type", "unknown"),
            },
        )
        exec_trace.add_span(span)

        try:
            # Ensure initialized
            if not self.agent._initialized:
                await self.agent.initialize()

            # Handle event
            result = await self.agent.handle_event(event)

            span.end()
            exec_trace.end(output=result)

        except Exception as e:
            logger.exception(f"Event handling failed: {e}")
            span.end(status="error", error=str(e))
            exec_trace.end(output={"error": str(e)})

        return exec_trace

    async def run_cluster(self) -> None:
        """
        Run agent in cluster mode (Temporal worker).

        Requires temporalio to be installed.
        """
        try:
            from temporalio.client import Client
            from temporalio.worker import Worker
        except ImportError:
            raise ImportError(
                "Temporal support requires 'temporalio' package. "
                "Install with: pip install agent-framework[temporal]"
            )

        # Get Temporal configuration
        from core_agents.config_unified import get_config

        kubani_config = get_config()

        # Connect to Temporal
        client = await Client.connect(
            kubani_config.temporal.host,
            namespace=kubani_config.temporal.namespace,
        )

        logger.info(
            f"Starting agent {self.config.name} in cluster mode "
            f"(Temporal: {kubani_config.temporal.host})"
        )

        # Initialize agent
        await self.agent.initialize()

        # Create worker
        # Note: Actual workflows/activities would be registered by the agent
        worker = Worker(
            client,
            task_queue=self.config.name,
            workflows=[],  # Agent provides these
            activities=[],  # Agent provides these
        )

        try:
            await worker.run()
        finally:
            await self.agent.shutdown()


def run_agent(
    agent_class: type[AgentBase],
    config: AgentConfig | None = None,
    **config_kwargs: Any,
) -> None:
    """
    Convenience function to run an agent.

    Parses command-line arguments and runs in appropriate mode.

    Example:
        if __name__ == "__main__":
            run_agent(MyAgent, name="my-agent")
    """
    import argparse

    parser = argparse.ArgumentParser(description="Run agent")
    parser.add_argument(
        "--mode",
        choices=["local", "local-cluster", "cluster"],
        default="local",
        help="Execution mode",
    )
    parser.add_argument(
        "--event",
        type=str,
        help="JSON event to handle (single execution)",
    )

    args = parser.parse_args()

    # Build config
    mode_map = {
        "local": RunMode.LOCAL,
        "local-cluster": RunMode.LOCAL_CLUSTER,
        "cluster": RunMode.CLUSTER,
    }

    if config is None:
        config = AgentConfig(mode=mode_map[args.mode], **config_kwargs)
    else:
        config.mode = mode_map[args.mode]

    runner = AgentRunner(agent_class, config)

    async def main() -> None:
        if args.event:
            import json

            event = json.loads(args.event)
            trace = await runner.handle_event(event)
            print(trace.model_dump_json(indent=2))
        elif config.mode == RunMode.CLUSTER:
            await runner.run_cluster()
        else:
            await runner.run_local()

    asyncio.run(main())
