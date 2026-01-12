"""
Local Development Harness for Kubani Agents.

Provides seamless local development with cluster service connectivity:
- Network tunneling to cluster services (telepresence, kubectl port-forward)
- Configurable Temporal (local or cluster)
- Output routing (console, Discord, or both)
- Hot-reload support for rapid iteration

Usage:
    kubani-dev local-run <agent_name> --temporal=[local|cluster] --output=[console|discord|both]
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

import click

logger = logging.getLogger(__name__)


class TunnelMethod(Enum):
    """Methods for connecting to cluster services."""

    NONE = "none"
    TELEPRESENCE = "telepresence"
    KUBECTL_FORWARD = "kubectl-forward"


class OutputMode(Enum):
    """Where to route agent output."""

    CONSOLE = "console"
    DISCORD = "discord"
    BOTH = "both"


@dataclass
class PortForward:
    """A kubectl port-forward configuration."""

    local_port: int
    remote_port: int
    service: str
    namespace: str
    process: subprocess.Popen | None = None


@dataclass
class LocalDevContext:
    """Context for local development session."""

    agent_name: str
    agent_path: Path
    temporal_mode: str  # "local" or "cluster"
    output_mode: OutputMode
    tunnel_method: TunnelMethod
    port_forwards: list[PortForward] = field(default_factory=list)
    processes: list[subprocess.Popen] = field(default_factory=list)
    cleanup_handlers: list[Callable] = field(default_factory=list)

    def add_cleanup(self, handler: Callable) -> None:
        """Add a cleanup handler to run on shutdown."""
        self.cleanup_handlers.append(handler)

    async def cleanup(self) -> None:
        """Clean up all resources."""
        logger.info("Cleaning up local development resources...")

        # Run cleanup handlers
        for handler in self.cleanup_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            except Exception as e:
                logger.warning(f"Cleanup handler failed: {e}")

        # Stop port forwards
        for pf in self.port_forwards:
            if pf.process:
                pf.process.terminate()
                try:
                    pf.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pf.process.kill()

        # Stop other processes
        for proc in self.processes:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


class ClusterTunnel:
    """Manages connectivity to cluster services."""

    # Default services to forward for local development
    DEFAULT_FORWARDS = [
        PortForward(6333, 6333, "qdrant", "ai-agents"),
        PortForward(7687, 7687, "neo4j", "ai-agents"),
        PortForward(6379, 6379, "redis", "ai-agents"),
        PortForward(8000, 8000, "metadata-registry", "ai-agents"),
        PortForward(8080, 8080, "discord-mcp-server", "ai-agents"),
        PortForward(8001, 8001, "embeddings-api", "ai-agents"),
    ]

    TEMPORAL_FORWARD = PortForward(7233, 7233, "temporal-frontend", "temporal")

    def __init__(self, method: TunnelMethod, include_temporal: bool = False):
        self.method = method
        self.include_temporal = include_temporal
        self.forwards: list[PortForward] = []

    async def start(self, ctx: LocalDevContext) -> None:
        """Start the tunnel to cluster services."""
        if self.method == TunnelMethod.NONE:
            logger.info("No tunnel configured - using local services only")
            return

        if self.method == TunnelMethod.TELEPRESENCE:
            await self._start_telepresence(ctx)
        elif self.method == TunnelMethod.KUBECTL_FORWARD:
            await self._start_port_forwards(ctx)

    async def _start_telepresence(self, ctx: LocalDevContext) -> None:
        """Start telepresence for full cluster network access."""
        logger.info("Starting telepresence connection...")

        try:
            # Check if telepresence is installed
            result = subprocess.run(
                ["telepresence", "version"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError("Telepresence not installed")

            # Connect to cluster
            proc = subprocess.Popen(
                ["telepresence", "connect"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            ctx.processes.append(proc)

            # Wait for connection
            await asyncio.sleep(5)

            logger.info("Telepresence connected - cluster services accessible via DNS")

            # Add cleanup handler
            async def cleanup_telepresence():
                subprocess.run(["telepresence", "quit"], capture_output=True)

            ctx.add_cleanup(cleanup_telepresence)

        except Exception as e:
            logger.error(f"Failed to start telepresence: {e}")
            logger.info("Falling back to kubectl port-forward")
            await self._start_port_forwards(ctx)

    async def _start_port_forwards(self, ctx: LocalDevContext) -> None:
        """Start kubectl port-forwards for each required service."""
        forwards = list(self.DEFAULT_FORWARDS)
        if self.include_temporal:
            forwards.append(self.TEMPORAL_FORWARD)

        logger.info(f"Starting {len(forwards)} port-forwards...")

        for pf in forwards:
            try:
                proc = subprocess.Popen(
                    [
                        "kubectl",
                        "port-forward",
                        f"svc/{pf.service}",
                        f"{pf.local_port}:{pf.remote_port}",
                        "-n",
                        pf.namespace,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                pf.process = proc
                ctx.port_forwards.append(pf)
                logger.info(f"  ✓ {pf.service}:{pf.remote_port} -> localhost:{pf.local_port}")
            except Exception as e:
                logger.warning(f"  ✗ Failed to forward {pf.service}: {e}")

        # Give port-forwards time to establish
        await asyncio.sleep(2)


class LocalTemporalManager:
    """Manages local Temporal instance for development."""

    def __init__(self):
        self.process: subprocess.Popen | None = None

    async def start(self, ctx: LocalDevContext) -> None:
        """Start local Temporalite instance."""
        logger.info("Starting local Temporalite instance...")

        try:
            # Check if temporalite is installed
            result = subprocess.run(
                ["temporalite", "--version"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError("Temporalite not installed")

            # Start temporalite
            self.process = subprocess.Popen(
                [
                    "temporalite",
                    "start",
                    "--namespace",
                    "default",
                    "--log-level",
                    "warn",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            ctx.processes.append(self.process)

            # Wait for startup
            await asyncio.sleep(3)
            logger.info("Temporalite started on localhost:7233")

        except FileNotFoundError:
            logger.warning(
                "Temporalite not found. Install with: "
                "go install github.com/temporalio/temporalite/cmd/temporalite@latest"
            )
            logger.info("Continuing without local Temporal - workflows will be disabled")


class OutputRouter:
    """Routes agent output to configured destinations."""

    def __init__(self, mode: OutputMode, discord_mcp_url: str | None = None):
        self.mode = mode
        self.discord_mcp_url = discord_mcp_url

    async def route(self, message: str, channel: str = "default") -> None:
        """Route a message to configured outputs."""
        if self.mode in (OutputMode.CONSOLE, OutputMode.BOTH):
            self._print_console(message)

        if self.mode in (OutputMode.DISCORD, OutputMode.BOTH):
            await self._send_discord(message, channel)

    def _print_console(self, message: str) -> None:
        """Print message to console with formatting."""
        print(f"\n{'=' * 60}")
        print(message)
        print(f"{'=' * 60}\n")

    async def _send_discord(self, message: str, channel: str) -> None:
        """Send message to Discord via MCP server."""
        if not self.discord_mcp_url:
            logger.warning("Discord MCP URL not configured")
            return

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                # Initialize MCP session if needed
                response = await client.post(
                    f"{self.discord_mcp_url}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "send_message",
                            "arguments": {
                                "channel_id": channel,
                                "content": message,
                            },
                        },
                    },
                    timeout=30.0,
                )
                if response.status_code != 200:
                    logger.warning(f"Failed to send to Discord: {response.status_code}")
        except Exception as e:
            logger.warning(f"Failed to send to Discord: {e}")


async def run_agent_locally(ctx: LocalDevContext) -> None:
    """Run an agent in local development mode."""
    # Set up environment for the agent
    env = os.environ.copy()
    env["KUBANI_ENVIRONMENT"] = "development"
    env["KUBANI_CONFIG_DIR"] = str(ctx.agent_path.parent.parent.parent)

    if ctx.temporal_mode == "local":
        env["TEMPORAL_HOST"] = "localhost:7233"
    else:
        env["TEMPORAL_HOST"] = "temporal-frontend.temporal.svc.cluster.local:7233"

    # Set output mode
    env["LOCAL_OUTPUT_MODE"] = ctx.output_mode.value

    # Find the agent's main entry point
    worker_path = ctx.agent_path / "src" / ctx.agent_name.replace("-", "_") / "worker.py"
    if not worker_path.exists():
        # Try alternative paths
        for pattern in ["worker.py", "main.py", "__main__.py"]:
            matches = list(ctx.agent_path.rglob(pattern))
            if matches:
                worker_path = matches[0]
                break

    if not worker_path.exists():
        logger.error(f"Could not find entry point for agent {ctx.agent_name}")
        return

    logger.info(f"Starting agent from {worker_path}")

    # Run the agent using uv to ensure we use the agent's venv
    # This handles dependency resolution automatically
    proc = subprocess.Popen(
        ["uv", "run", "python", str(worker_path)],
        env=env,
        cwd=str(ctx.agent_path),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    ctx.processes.append(proc)

    # Wait for the agent process
    try:
        proc.wait()
    except KeyboardInterrupt:
        logger.info("Received interrupt, shutting down...")


@click.command("local-run")
@click.argument("agent_name")
@click.option(
    "--temporal",
    type=click.Choice(["local", "cluster"]),
    default="local",
    help="Use local Temporalite or cluster Temporal",
)
@click.option(
    "--output",
    type=click.Choice(["console", "discord", "both"]),
    default="console",
    help="Where to route agent output",
)
@click.option(
    "--tunnel/--no-tunnel",
    default=False,
    help="Enable tunnel to cluster services",
)
@click.option(
    "--tunnel-method",
    type=click.Choice(["telepresence", "kubectl-forward"]),
    default="kubectl-forward",
    help="Method for cluster connectivity",
)
@click.option(
    "--watch/--no-watch",
    default=False,
    help="Watch for file changes and restart (not yet implemented)",
)
def local_run(
    agent_name: str,
    temporal: str,
    output: str,
    tunnel: bool,
    tunnel_method: str,
    watch: bool,
) -> None:
    """
    Run an agent locally with cluster service connectivity.

    This command sets up the local development environment:
    - Optionally tunnels to cluster services (Qdrant, Redis, Neo4j, etc.)
    - Starts local Temporal or connects to cluster Temporal
    - Routes output to console and/or Discord

    Examples:

        # Run locally with local Temporal, console output
        kubani-dev local-run k8s-monitor

        # Run with cluster services and Discord output
        kubani-dev local-run k8s-monitor --tunnel --temporal=cluster --output=both

        # Quick iteration with console-only output
        kubani-dev local-run news-monitor --output=console
    """
    # Find agent path
    # __file__ is at tools/kubani-dev/src/kubani_dev/local_run.py (5 levels from repo root)
    repo_root = Path(__file__).parent.parent.parent.parent.parent
    agent_path = repo_root / "agents" / agent_name

    if not agent_path.exists():
        click.echo(f"Error: Agent '{agent_name}' not found at {agent_path}", err=True)
        sys.exit(1)

    # Create context
    ctx = LocalDevContext(
        agent_name=agent_name,
        agent_path=agent_path,
        temporal_mode=temporal,
        output_mode=OutputMode(output),
        tunnel_method=TunnelMethod(tunnel_method) if tunnel else TunnelMethod.NONE,
    )

    # Set up signal handlers
    def signal_handler(signum, frame):
        asyncio.get_event_loop().run_until_complete(ctx.cleanup())
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    async def main():
        try:
            click.echo(f"\n🚀 Starting local development for {agent_name}")
            click.echo(f"   Temporal: {temporal}")
            click.echo(f"   Output: {output}")
            click.echo(f"   Tunnel: {tunnel_method if tunnel else 'disabled'}")
            click.echo()

            # Start tunnel if enabled
            if tunnel:
                tunnel_manager = ClusterTunnel(
                    method=ctx.tunnel_method,
                    include_temporal=(temporal == "cluster"),
                )
                await tunnel_manager.start(ctx)

            # Start local Temporal if needed
            if temporal == "local":
                temporal_manager = LocalTemporalManager()
                await temporal_manager.start(ctx)

            # Run the agent
            await run_agent_locally(ctx)

        finally:
            await ctx.cleanup()

    asyncio.run(main())


if __name__ == "__main__":
    local_run()
