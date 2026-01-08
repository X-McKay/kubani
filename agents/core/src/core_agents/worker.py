"""
Generic Temporal worker for AI agents.

Provides a standardized AgentWorker class that consolidates common patterns:
- Temporal client connection with standard env vars
- Worker creation with task queue, workflows, activities
- Standard logging setup
- Optional federated agents support
- Command-line argument handling

Usage:
    from core_agents.worker import AgentWorker, AgentWorkerConfig

    config = AgentWorkerConfig(
        task_queue="my-agent",
        workflows=[MyWorkflow],
        activities=[my_activity],
    )
    worker = AgentWorker(config)
    worker.run()  # Parses args: worker, schedule, check, etc.
"""

import asyncio
import logging
import os
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from temporalio.client import Client
from temporalio.worker import Worker

logger = logging.getLogger(__name__)


def setup_logging(
    level: int = logging.INFO,
    format_string: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
) -> None:
    """
    Configure standard logging format for agents.

    Args:
        level: Logging level (default: INFO)
        format_string: Log message format
    """
    logging.basicConfig(level=level, format=format_string)


@dataclass
class ScheduledWorkflowConfig:
    """Configuration for a scheduled workflow."""

    workflow_class: type
    """Workflow class to run."""

    workflow_id: str
    """Unique ID for the workflow."""

    default_args: list[Any] = field(default_factory=list)
    """Default arguments for the workflow."""

    interval_env_var: str | None = None
    """Environment variable for interval (in hours)."""

    default_interval_hours: int = 1
    """Default interval if env var not set."""


@dataclass
class CommandConfig:
    """Configuration for a CLI command."""

    name: str
    """Command name (e.g., 'schedule', 'check')."""

    description: str
    """Description for help text."""

    handler: Callable[["AgentWorker"], Awaitable[Any]]
    """Async handler function."""

    args: list[str] = field(default_factory=list)
    """Additional args for help text (e.g., ['hours'])."""


@dataclass
class AgentWorkerConfig:
    """Configuration for an AgentWorker."""

    task_queue: str
    """Task queue name for this agent."""

    workflows: list[type]
    """List of workflow classes to register."""

    activities: list[Callable]
    """List of activity functions to register."""

    name: str = ""
    """Agent name (defaults to task_queue)."""

    description: str = ""
    """Agent description for logging."""

    temporal_host_default: str = "temporal-frontend.temporal.svc.cluster.local:7233"
    """Default Temporal host if TEMPORAL_HOST not set."""

    temporal_namespace_default: str = "default"
    """Default Temporal namespace if TEMPORAL_NAMESPACE not set."""

    scheduled_workflows: list[ScheduledWorkflowConfig] = field(default_factory=list)
    """Scheduled workflows that can be started via CLI."""

    federated_agents_factory: Callable[[], Awaitable[None]] | None = None
    """Optional factory to start federated agents alongside worker."""

    federated_agents_enabled_env: str = "ENABLE_FEDERATED_AGENTS"
    """Environment variable to enable/disable federated agents."""

    startup_hooks: list[Callable[[Client], Awaitable[None]]] = field(default_factory=list)
    """Functions to run after Temporal connection but before worker starts."""

    custom_commands: list[CommandConfig] = field(default_factory=list)
    """Additional CLI commands beyond the standard ones."""


class AgentWorker:
    """
    Generic Temporal worker for AI agents.

    Consolidates common patterns across agent workers:
    - Standard Temporal client connection
    - Worker lifecycle management
    - Federated agents support
    - CLI command handling

    Example:
        config = AgentWorkerConfig(
            task_queue="k8s-monitor",
            workflows=[ClusterHealthCheckWorkflow],
            activities=[collect_and_analyze_cluster],
            scheduled_workflows=[
                ScheduledWorkflowConfig(
                    workflow_class=ScheduledHealthCheckWorkflow,
                    workflow_id="k8s-monitor-scheduled",
                    default_interval_hours=1,
                ),
            ],
        )
        worker = AgentWorker(config)
        worker.run()
    """

    def __init__(self, config: AgentWorkerConfig) -> None:
        """
        Initialize the worker with configuration.

        Args:
            config: Worker configuration
        """
        self.config = config
        self._client: Client | None = None
        self._worker: Worker | None = None

    @property
    def name(self) -> str:
        """Get agent name (defaults to task queue)."""
        return self.config.name or self.config.task_queue

    @property
    def temporal_host(self) -> str:
        """Get Temporal host from environment or default."""
        return os.environ.get("TEMPORAL_HOST", self.config.temporal_host_default)

    @property
    def temporal_namespace(self) -> str:
        """Get Temporal namespace from environment or default."""
        return os.environ.get("TEMPORAL_NAMESPACE", self.config.temporal_namespace_default)

    @property
    def federated_agents_enabled(self) -> bool:
        """Check if federated agents are enabled."""
        env_var = self.config.federated_agents_enabled_env
        return os.environ.get(env_var, "true").lower() == "true"

    async def connect(self) -> Client:
        """
        Connect to Temporal server.

        Returns:
            Connected Temporal client
        """
        if self._client is None:
            logger.info(f"Connecting to Temporal at {self.temporal_host}")
            self._client = await Client.connect(
                self.temporal_host,
                namespace=self.temporal_namespace,
            )
        return self._client

    async def run_startup_hooks(self) -> None:
        """Run startup hooks after Temporal connection."""
        client = await self.connect()
        for hook in self.config.startup_hooks:
            try:
                await hook(client)
            except Exception as e:
                logger.error(f"Startup hook failed: {e}")

    async def run_worker(self) -> None:
        """
        Run the Temporal worker.

        This is the main entry point that:
        1. Connects to Temporal
        2. Runs startup hooks
        3. Creates and runs the worker
        4. Optionally starts federated agents
        """
        client = await self.connect()
        await self.run_startup_hooks()

        logger.info(f"Starting worker on task queue: {self.config.task_queue}")

        self._worker = Worker(
            client,
            task_queue=self.config.task_queue,
            workflows=self.config.workflows,
            activities=self.config.activities,
        )

        logger.info("Worker started, polling for tasks...")

        # Start federated agents if configured and enabled
        federated_factory = self.config.federated_agents_factory
        if federated_factory and self.federated_agents_enabled:
            logger.info("Starting federated agents...")
            federated_task = asyncio.create_task(federated_factory())
            try:
                await self._worker.run()
            finally:
                federated_task.cancel()
                try:
                    await federated_task
                except asyncio.CancelledError:
                    logger.info("Federated agents stopped")
        else:
            if federated_factory and not self.federated_agents_enabled:
                logger.info(
                    f"Federated agents disabled ({self.config.federated_agents_enabled_env}=false)"
                )
            await self._worker.run()

    async def start_scheduled_workflow(
        self,
        scheduled_config: ScheduledWorkflowConfig,
        interval_hours: int | None = None,
        extra_args: list[Any] | None = None,
    ) -> str | None:
        """
        Start a scheduled workflow if not already running.

        Args:
            scheduled_config: Configuration for the scheduled workflow
            interval_hours: Override default interval (hours)
            extra_args: Additional args to pass to workflow

        Returns:
            Workflow ID if started, None if already running
        """
        client = await self.connect()
        workflow_id = scheduled_config.workflow_id

        # Check if already running
        try:
            handle = client.get_workflow_handle(workflow_id)
            desc = await handle.describe()
            if desc.status.name == "RUNNING":
                logger.info(f"Scheduled workflow already running: {workflow_id}")
                return None
        except Exception:
            pass  # Workflow doesn't exist

        # Determine interval
        actual_interval = interval_hours
        if actual_interval is None:
            if scheduled_config.interval_env_var:
                actual_interval = int(
                    os.environ.get(
                        scheduled_config.interval_env_var,
                        str(scheduled_config.default_interval_hours),
                    )
                )
            else:
                actual_interval = scheduled_config.default_interval_hours

        # Build args
        workflow_args = list(scheduled_config.default_args)
        if actual_interval is not None and not workflow_args:
            workflow_args = [actual_interval]
        if extra_args:
            workflow_args.extend(extra_args)

        logger.info(f"Starting scheduled workflow: {workflow_id} (interval: {actual_interval}h)")

        await client.start_workflow(
            scheduled_config.workflow_class.run,
            *workflow_args,
            id=workflow_id,
            task_queue=self.config.task_queue,
        )

        logger.info(f"Scheduled workflow started: {workflow_id}")
        return workflow_id

    async def run_single_workflow(
        self,
        workflow_class: type,
        workflow_id_prefix: str,
        args: list[Any] | None = None,
    ) -> Any:
        """
        Run a single workflow and wait for result.

        Args:
            workflow_class: Workflow class to run
            workflow_id_prefix: Prefix for workflow ID
            args: Arguments for the workflow

        Returns:
            Workflow result
        """
        client = await self.connect()
        workflow_id = f"{workflow_id_prefix}-{asyncio.get_event_loop().time()}"

        logger.info(f"Starting workflow: {workflow_id}")

        handle = await client.start_workflow(
            workflow_class.run,
            *(args or []),
            id=workflow_id,
            task_queue=self.config.task_queue,
        )

        result = await handle.result()
        logger.info(f"Workflow completed: {workflow_id}")
        return result

    async def run_federated_only(self) -> None:
        """Run only federated agents without Temporal worker."""
        if not self.config.federated_agents_factory:
            logger.error("No federated agents factory configured")
            return
        await self.config.federated_agents_factory()

    def _print_help(self) -> None:
        """Print CLI help text."""
        print(f"Usage: {self.name}-worker <command> [args]")
        print()
        print("Commands:")
        print("  worker              Run Temporal worker (default)")

        # Standard commands based on scheduled workflows
        for sw in self.config.scheduled_workflows:
            base_name = sw.workflow_id.replace(f"{self.config.task_queue}-", "")
            print(f"  schedule-{base_name}  Start {base_name} scheduled workflow")

        # Federated agents
        if self.config.federated_agents_factory:
            print("  federated-only      Run only federated agents (no Temporal worker)")

        # Custom commands
        for cmd in self.config.custom_commands:
            args_str = " ".join(f"<{a}>" for a in cmd.args) if cmd.args else ""
            cmd_str = f"  {cmd.name}"
            if args_str:
                cmd_str += f" {args_str}"
            cmd_str = cmd_str.ljust(24)
            print(f"{cmd_str}{cmd.description}")

        print()
        print("Environment variables:")
        print("  TEMPORAL_HOST           Temporal server address")
        print("  TEMPORAL_NAMESPACE      Temporal namespace")
        if self.config.federated_agents_factory:
            print(
                f"  {self.config.federated_agents_enabled_env}  "
                "Enable federated agents (default: true)"
            )

    def run(self, args: list[str] | None = None) -> None:
        """
        Main entry point - parse args and run appropriate command.

        Args:
            args: Command line arguments (defaults to sys.argv[1:])
        """
        setup_logging()

        cmd_args = args if args is not None else sys.argv[1:]
        command = cmd_args[0] if cmd_args else "worker"

        if command in ("--help", "-h", "help"):
            self._print_help()
            return

        if command == "worker":
            asyncio.run(self.run_worker())
            return

        if command == "federated-only" and self.config.federated_agents_factory:
            asyncio.run(self.run_federated_only())
            return

        # Check scheduled workflows
        for sw in self.config.scheduled_workflows:
            base_name = sw.workflow_id.replace(f"{self.config.task_queue}-", "")
            if command == f"schedule-{base_name}":
                interval = int(cmd_args[1]) if len(cmd_args) > 1 else None
                asyncio.run(self.start_scheduled_workflow(sw, interval))
                return

        # Check custom commands
        for cmd in self.config.custom_commands:
            if command == cmd.name:
                asyncio.run(cmd.handler(self))
                return

        print(f"Unknown command: {command}")
        self._print_help()
        sys.exit(1)


__all__ = [
    "AgentWorker",
    "AgentWorkerConfig",
    "CommandConfig",
    "ScheduledWorkflowConfig",
    "setup_logging",
]
