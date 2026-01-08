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
import contextlib
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
class AgentCapabilityConfig:
    """Configuration for an agent capability."""

    name: str
    """Capability name (e.g., 'analyze', 'remediate')."""

    description: str = ""
    """Description of what this capability does."""

    input_schema: dict[str, Any] | None = None
    """JSON schema for capability inputs."""

    output_schema: dict[str, Any] | None = None
    """JSON schema for capability outputs."""

    tags: list[str] = field(default_factory=list)
    """Tags for capability categorization."""


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

    # --- Agent Metadata for Registry ---
    agent_id: str | None = None
    """Unique agent ID for registry (defaults to task_queue)."""

    agent_version: str | None = None
    """Agent version (defaults to AGENT_VERSION env var)."""

    agent_endpoint: str | None = None
    """Agent's service endpoint URL (defaults to AGENT_ENDPOINT env var)."""

    capabilities: list[AgentCapabilityConfig] = field(default_factory=list)
    """List of agent capabilities for registry."""

    enable_registry: bool = True
    """Enable automatic registration with registry service."""

    # --- Temporal Configuration ---
    temporal_host_default: str = "temporal-frontend.temporal.svc.cluster.local:7233"
    """Default Temporal host if TEMPORAL_HOST not set."""

    temporal_namespace_default: str = "default"
    """Default Temporal namespace if TEMPORAL_NAMESPACE not set."""

    scheduled_workflows: list[ScheduledWorkflowConfig] = field(default_factory=list)
    """Scheduled workflows that can be started via CLI."""

    # --- Federated Agents ---
    federated_agents_factory: Callable[[], Awaitable[None]] | None = None
    """Optional factory to start federated agents alongside worker."""

    federated_agents_enabled_env: str = "ENABLE_FEDERATED_AGENTS"
    """Environment variable to enable/disable federated agents."""

    # --- Lifecycle Hooks ---
    startup_hooks: list[Callable[[Client], Awaitable[None]]] = field(default_factory=list)
    """Functions to run after Temporal connection but before worker starts."""

    shutdown_hooks: list[Callable[[Client], Awaitable[None]]] = field(default_factory=list)
    """Functions to run on worker shutdown (cleanup, deregistration)."""

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
    - Automatic registry registration with retry/backoff

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
            capabilities=[
                AgentCapabilityConfig(
                    name="health-check",
                    description="Analyze cluster health",
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
        self._registry_client: Any = None  # Lazy import to avoid circular deps
        self._registration_task: asyncio.Task | None = None
        self._shutdown_event: asyncio.Event | None = None

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

    @property
    def agent_id(self) -> str:
        """Get agent ID for registry (defaults to task queue)."""
        return self.config.agent_id or self.config.task_queue

    @property
    def agent_version(self) -> str | None:
        """Get agent version from config or environment."""
        return self.config.agent_version or os.environ.get("AGENT_VERSION")

    @property
    def agent_endpoint(self) -> str | None:
        """Get agent endpoint from config or environment."""
        return self.config.agent_endpoint or os.environ.get("AGENT_ENDPOINT")

    @property
    def registry_enabled(self) -> bool:
        """Check if registry integration is enabled."""
        # Check both config flag and environment override
        env_override = os.environ.get("KUBANI_REGISTRY_ENABLED")
        if env_override is not None:
            return env_override.lower() == "true"
        return self.config.enable_registry

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

    async def run_shutdown_hooks(self) -> None:
        """Run shutdown hooks for cleanup."""
        client = self._client
        if client is None:
            return

        for hook in self.config.shutdown_hooks:
            try:
                await hook(client)
            except Exception as e:
                logger.error(f"Shutdown hook failed: {e}")

    def _get_registry_config(self) -> tuple[str, float, int, float, float]:
        """Get registry configuration from environment or defaults.

        Returns:
            Tuple of (url, heartbeat_interval, max_attempts, base_delay, timeout)
        """
        from core_agents.config import get_config

        config = get_config()
        return (
            config.registry_url,
            config.registry_heartbeat_interval,
            config.registry_retry_max_attempts,
            config.registry_retry_base_delay,
            config.registry_timeout,
        )

    async def _get_registry_client(self) -> Any:
        """Get or create the registry client (lazy initialization)."""
        if self._registry_client is None:
            # Lazy import to avoid circular dependencies
            from core_agents.registry import RegistryClient

            url, heartbeat_interval, _, _, timeout = self._get_registry_config()
            self._registry_client = RegistryClient(
                base_url=url,
                timeout=timeout,
                heartbeat_interval=heartbeat_interval,
            )
        return self._registry_client

    async def _register_with_retry(self) -> None:
        """Register with registry using exponential backoff.

        This runs as a background task and keeps retrying registration
        until successful or max attempts reached. The worker continues
        operating regardless of registration status.
        """
        url, heartbeat_interval, max_attempts, base_delay, _ = self._get_registry_config()

        delay = base_delay
        for attempt in range(max_attempts):
            try:
                client = await self._get_registry_client()
                await client.connect()

                # Convert capabilities to registry format
                from core_agents.registry.models import AgentCapability

                capabilities = [
                    AgentCapability(
                        name=cap.name,
                        description=cap.description,
                        input_schema=cap.input_schema or {},
                        output_schema=cap.output_schema or {},
                        tags=cap.tags,
                    )
                    for cap in self.config.capabilities
                ]

                await client.register_agent(
                    agent_id=self.agent_id,
                    name=self.name,
                    description=self.config.description,
                    version=self.agent_version,
                    endpoint=self.agent_endpoint,
                    task_queue=self.config.task_queue,
                    capabilities=capabilities,
                )

                # Start heartbeat after successful registration
                await client.start_heartbeat(self.agent_id)

                logger.info(
                    f"Successfully registered with registry at {url} "
                    f"(heartbeat interval: {heartbeat_interval}s)"
                )

                # Record deployment (fire-and-forget, don't fail on errors)
                await self._record_deployment(client)

                return

            except Exception as e:
                logger.warning(
                    f"Registry registration attempt {attempt + 1}/{max_attempts} failed: {e}"
                )
                if attempt < max_attempts - 1:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60.0)  # Cap at 60 seconds

        logger.error(
            f"Failed to register with registry after {max_attempts} attempts. "
            "Worker will continue operating without registry integration."
        )

    async def _record_deployment(self, client: Any) -> None:
        """
        Record a deployment to the registry.

        This is called after successful agent registration to track
        deployment history. Uses environment variables for deployment
        metadata (set by GitOps manifests).
        """
        if not self.agent_version:
            logger.debug("No agent version set, skipping deployment recording")
            return

        try:
            # Get deployment metadata from environment
            image_tag = os.environ.get("AGENT_IMAGE_TAG", "")
            git_sha = os.environ.get("AGENT_GIT_SHA", "")
            deployed_by = os.environ.get("AGENT_DEPLOYED_BY", "gitops")

            # Use the underlying httpx client for the deployment API
            http_client = client._ensure_client()
            response = await http_client.post(
                "/api/v1/deployments",
                json={
                    "agent_id": self.agent_id,
                    "version": self.agent_version,
                    "image_tag": image_tag,
                    "git_sha": git_sha,
                    "deployed_by": deployed_by,
                    "config_snapshot": {
                        "task_queue": self.config.task_queue,
                        "temporal_host": self.temporal_host,
                        "temporal_namespace": self.temporal_namespace,
                    },
                },
            )
            if response.status_code in (200, 201):
                logger.info(f"Recorded deployment: {self.agent_id} v{self.agent_version}")
            else:
                logger.debug(f"Deployment recording returned {response.status_code}")
        except Exception as e:
            # Don't fail registration if deployment recording fails
            logger.warning(f"Failed to record deployment: {e}")

    async def _cleanup_registry(self) -> None:
        """Clean up registry connection on shutdown."""
        if self._registry_client is not None:
            try:
                # Stop heartbeat and unregister (best effort)
                await self._registry_client.stop_heartbeat()
                try:
                    await self._registry_client.unregister_agent(self.agent_id)
                except Exception as e:
                    logger.debug(f"Unregister failed (may already be removed): {e}")
                await self._registry_client.close()
            except Exception as e:
                logger.warning(f"Registry cleanup error: {e}")
            finally:
                self._registry_client = None

    async def run_worker(self) -> None:
        """
        Run the Temporal worker.

        This is the main entry point that:
        1. Connects to Temporal
        2. Runs startup hooks
        3. Starts registry registration (background, with retry)
        4. Creates and runs the worker
        5. Optionally starts federated agents
        6. Cleans up on shutdown
        """
        client = await self.connect()
        await self.run_startup_hooks()

        # Start registry registration as background task (non-blocking)
        if self.registry_enabled:
            logger.info("Starting registry registration (background task)...")
            self._registration_task = asyncio.create_task(
                self._register_with_retry(), name=f"registry-{self.agent_id}"
            )
        else:
            logger.info("Registry integration disabled")

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
        federated_task: asyncio.Task | None = None

        try:
            if federated_factory and self.federated_agents_enabled:
                logger.info("Starting federated agents...")
                federated_task = asyncio.create_task(federated_factory())

            await self._worker.run()

        finally:
            # Cleanup on shutdown
            logger.info("Worker shutting down, running cleanup...")

            # Cancel federated agents
            if federated_task is not None:
                federated_task.cancel()
                try:
                    await federated_task
                except asyncio.CancelledError:
                    logger.info("Federated agents stopped")

            # Cancel registration task if still running
            if self._registration_task is not None:
                self._registration_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._registration_task

            # Clean up registry connection
            await self._cleanup_registry()

            # Run user-defined shutdown hooks
            await self.run_shutdown_hooks()

            logger.info("Cleanup complete")

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
    "AgentCapabilityConfig",
    "AgentWorker",
    "AgentWorkerConfig",
    "CommandConfig",
    "ScheduledWorkflowConfig",
    "setup_logging",
]
