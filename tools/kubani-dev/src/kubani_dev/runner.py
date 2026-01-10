"""
Agent Runner - Local development server with hot-reloading.

Provides a development environment for running agents locally with:
- Hot-reloading on code changes
- Mock MCP servers for testing
- Mock Redis for event bus
- Real-time logging and tracing
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING
from watchfiles import awatch

if TYPE_CHECKING:
    from aiohttp import web

logger = logging.getLogger(__name__)


class MockRedis:
    """Mock Redis client for local development."""

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._streams: dict[str, list] = {}
        self._expiry: dict[str, float] = {}

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> Any:
        return self._data.get(key)

    async def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        if nx and key in self._data:
            return None
        self._data[key] = value
        if ex:
            self._expiry[key] = asyncio.get_event_loop().time() + ex
        return True

    async def delete(self, key: str) -> int:
        if key in self._data:
            del self._data[key]
            return 1
        return 0

    async def xadd(self, stream: str, fields: dict, id: str = "*") -> str:
        if stream not in self._streams:
            self._streams[stream] = []
        entry_id = f"{len(self._streams[stream])}-0"
        self._streams[stream].append({"id": entry_id, "fields": fields})
        return entry_id

    async def xread(
        self,
        streams: dict,
        count: int | None = None,
        block: int | None = None,
    ) -> list:
        results = []
        for stream, last_id in streams.items():
            if stream in self._streams:
                entries = self._streams[stream]
                results.append((stream, entries[-count:] if count else entries))
        return results


class MockMCPClient:
    """Mock MCP client for local development."""

    def __init__(self, server_name: str):
        self.server_name = server_name
        self._tools: dict[str, Callable] = {}

    def register_mock_tool(self, name: str, handler: Callable) -> None:
        """Register a mock tool handler."""
        self._tools[name] = handler

    async def call_tool(self, tool_name: str, params: dict) -> dict:
        """Call a mock tool."""
        if tool_name in self._tools:
            try:
                result = await self._tools[tool_name](params)
                return {"success": True, "result": result}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {
            "success": False,
            "error": f"Mock tool {tool_name} not registered",
        }


class AgentRunner:
    """
    Runs an agent locally for development.

    Features:
    - Hot-reloading on code changes
    - Mock infrastructure (Redis, MCP)
    - Real-time logging
    - Graceful shutdown
    """

    def __init__(
        self,
        agent_name: str,
        project_root: Path,
        hot_reload: bool = True,
        port: int = 8080,
        mock_mcp: bool = False,
        mock_redis: bool = False,
    ):
        self.agent_name = agent_name
        self.project_root = project_root
        self.hot_reload = hot_reload
        self.port = port
        self.mock_mcp = mock_mcp
        self.mock_redis = mock_redis

        self._agent_module = None
        self._agent_instance = None
        self._running = False
        self._reload_event = asyncio.Event()

        # Determine agent path
        self.agent_path = project_root / "agents" / agent_name

    def _setup_environment(self) -> None:
        """Set up the development environment."""
        # Add agent source to path
        src_path = self.agent_path / "src"
        if src_path.exists() and str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        # Add core library to path
        core_path = self.project_root / "agents" / "core" / "src"
        if core_path.exists() and str(core_path) not in sys.path:
            sys.path.insert(0, str(core_path))

        # Set development environment variables
        os.environ.setdefault("KUBANI_ENV", "development")
        os.environ.setdefault("LOG_LEVEL", "DEBUG")

        if self.mock_redis:
            os.environ["REDIS_URL"] = "mock://localhost"

        logger.info(f"Environment configured for {self.agent_name}")

    def _load_agent_module(self) -> Any:
        """Load or reload the agent module."""
        module_name = self.agent_name.replace("-", "_")

        if self._agent_module:
            # Reload existing module
            importlib.reload(self._agent_module)
            logger.info(f"Reloaded {module_name}")
        else:
            # Initial import
            self._agent_module = importlib.import_module(module_name)
            logger.info(f"Loaded {module_name}")

        return self._agent_module

    async def _watch_for_changes(self) -> None:
        """Watch for file changes and trigger reload."""
        watch_paths = [
            self.agent_path / "src",
            self.project_root / "agents" / "core" / "src",
            self.project_root / "skills",
        ]

        existing_paths = [p for p in watch_paths if p.exists()]

        logger.info(f"Watching for changes in: {[str(p) for p in existing_paths]}")

        async for changes in awatch(*existing_paths):
            if not self._running:
                break

            changed_files = [str(c[1]) for c in changes]
            logger.info(f"Detected changes: {changed_files}")

            # Signal reload
            self._reload_event.set()

    async def _run_agent(self) -> None:
        """Run the agent."""
        try:
            module = self._load_agent_module()

            # Look for standard entry points
            if hasattr(module, "run"):
                await module.run()
            elif hasattr(module, "main"):
                result = module.main()
                if asyncio.iscoroutine(result):
                    await result
            elif hasattr(module, "start"):
                await module.start()
            else:
                logger.warning(f"No entry point found in {self.agent_name}")
                # Keep running for hot-reload
                while self._running and not self._reload_event.is_set():
                    await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            # Wait for reload on error
            await asyncio.sleep(2)

    async def run(self) -> None:
        """Main run loop with hot-reloading."""
        self._setup_environment()
        self._running = True

        logger.info(f"Starting {self.agent_name} (hot-reload={self.hot_reload})")

        if self.hot_reload:
            # Start file watcher
            watch_task = asyncio.create_task(self._watch_for_changes())

        try:
            while self._running:
                self._reload_event.clear()

                # Run agent
                agent_task = asyncio.create_task(self._run_agent())

                # Wait for either agent completion or reload signal
                done, pending = await asyncio.wait(
                    [agent_task, self._reload_event.wait()],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                if self._reload_event.is_set():
                    logger.info("Reloading agent...")
                    continue
                else:
                    # Agent completed normally
                    break

        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            self._running = False
            if self.hot_reload:
                watch_task.cancel()

        logger.info("Agent runner stopped")


class AgentDevServer:
    """
    Development server that exposes agent functionality via HTTP.

    Useful for testing agent interactions via API calls.
    """

    def __init__(
        self,
        agent_runner: AgentRunner,
        host: str = "localhost",
        port: int = 8080,
    ):
        self.runner = agent_runner
        self.host = host
        self.port = port

    async def start(self) -> None:
        """Start the development server."""
        from aiohttp import web

        app = web.Application()
        app.router.add_get("/health", self._health_handler)
        app.router.add_post("/invoke", self._invoke_handler)
        app.router.add_get("/status", self._status_handler)

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        logger.info(f"Dev server running at http://{self.host}:{self.port}")

    async def _health_handler(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "healthy"})

    async def _invoke_handler(self, request: web.Request) -> web.Response:
        """Invoke agent endpoint."""
        try:
            data = await request.json()
            message = data.get("message", "")

            # TODO: Invoke agent with message
            result = {"response": f"Received: {message}"}

            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _status_handler(self, request: web.Request) -> web.Response:
        """Agent status endpoint."""
        return web.json_response(
            {
                "agent": self.runner.agent_name,
                "running": self.runner._running,
                "hot_reload": self.runner.hot_reload,
            }
        )
