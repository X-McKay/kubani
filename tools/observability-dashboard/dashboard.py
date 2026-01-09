"""
Kubani Observability Dashboard

A real-time dashboard for monitoring Kubani agent system health,
providing visibility into:
- Agent execution traces and performance
- Memory system state
- Event bus activity
- Evaluation results

This dashboard connects to the Kubani infrastructure (Redis, Prometheus)
and provides a unified view of system health.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects metrics from various sources."""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._redis = None

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Connected to Redis for metrics")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")

    async def get_event_bus_stats(self) -> dict[str, Any]:
        """Get event bus statistics."""
        if not self._redis:
            return {"error": "Not connected"}

        try:
            # Get stream info
            streams = ["kubani:events", "kubani:issues", "kubani:remediations"]
            stats = {}

            for stream in streams:
                try:
                    info = await self._redis.xinfo_stream(stream)
                    stats[stream] = {
                        "length": info.get("length", 0),
                        "first_entry": info.get("first-entry"),
                        "last_entry": info.get("last-entry"),
                    }
                except Exception:
                    stats[stream] = {"length": 0}

            return stats
        except Exception as e:
            return {"error": str(e)}

    async def get_sentinel_stats(self) -> dict[str, Any]:
        """Get Sentinel agent statistics."""
        if not self._redis:
            return {"error": "Not connected"}

        try:
            # Count dedup keys
            keys = await self._redis.keys("sentinel:seen:*")
            return {
                "dedup_entries": len(keys),
                "status": "active" if keys else "idle",
            }
        except Exception as e:
            return {"error": str(e)}

    async def get_memory_stats(self) -> dict[str, Any]:
        """Get memory system statistics."""
        # This would connect to the memory system
        return {
            "working_memory_items": 0,
            "episodic_memories": 0,
            "semantic_memories": 0,
        }


class TraceCollector:
    """Collects execution traces."""

    def __init__(self):
        self._traces: list[dict] = []
        self._max_traces = 1000

    def add_trace(self, trace: dict) -> None:
        """Add a trace."""
        trace["timestamp"] = datetime.now(UTC).isoformat()
        self._traces.append(trace)
        if len(self._traces) > self._max_traces:
            self._traces = self._traces[-self._max_traces:]

    def get_traces(
        self,
        limit: int = 50,
        agent: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> list[dict]:
        """Get traces with optional filtering."""
        traces = self._traces

        if agent:
            traces = [t for t in traces if t.get("agent") == agent]

        if since:
            since_iso = since.isoformat()
            traces = [t for t in traces if t.get("timestamp", "") >= since_iso]

        return traces[-limit:]


class Dashboard:
    """Main dashboard application."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 3000,
        redis_url: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.metrics = MetricsCollector(redis_url)
        self.traces = TraceCollector()

    def _generate_html(self, data: dict[str, Any]) -> str:
        """Generate dashboard HTML."""
        event_stats = data.get("event_bus", {})
        sentinel_stats = data.get("sentinel", {})
        memory_stats = data.get("memory", {})
        traces = data.get("traces", [])

        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kubani Observability Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        .card {{ transition: transform 0.2s, box-shadow 0.2s; }}
        .card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
        .status-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
        .status-active {{ background-color: #10b981; animation: pulse 2s infinite; }}
        .status-idle {{ background-color: #f59e0b; }}
        .status-error {{ background-color: #ef4444; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
    </style>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    <!-- Header -->
    <header class="bg-gray-800 border-b border-gray-700 px-6 py-4">
        <div class="flex justify-between items-center">
            <div class="flex items-center space-x-4">
                <h1 class="text-2xl font-bold text-indigo-400">
                    <i class="fas fa-robot mr-2"></i>Kubani Dashboard
                </h1>
                <span class="text-sm text-gray-400">Real-time Agent Monitoring</span>
            </div>
            <div class="flex items-center space-x-4">
                <span class="text-sm text-gray-400">
                    Last updated: <span id="last-update">{datetime.now(UTC).strftime('%H:%M:%S')}</span>
                </span>
                <button onclick="location.reload()" class="px-3 py-1 bg-indigo-600 rounded hover:bg-indigo-700">
                    <i class="fas fa-sync-alt mr-1"></i>Refresh
                </button>
            </div>
        </div>
    </header>

    <main class="p-6">
        <!-- Status Cards -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div class="card bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div class="flex justify-between items-start">
                    <div>
                        <p class="text-gray-400 text-sm">Sentinel Status</p>
                        <p class="text-2xl font-bold mt-1">{sentinel_stats.get('status', 'Unknown').title()}</p>
                    </div>
                    <div class="status-dot status-{'active' if sentinel_stats.get('status') == 'active' else 'idle'}"></div>
                </div>
                <p class="text-sm text-gray-500 mt-2">
                    {sentinel_stats.get('dedup_entries', 0)} dedup entries
                </p>
            </div>

            <div class="card bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div class="flex justify-between items-start">
                    <div>
                        <p class="text-gray-400 text-sm">Event Bus</p>
                        <p class="text-2xl font-bold mt-1">{sum(s.get('length', 0) for s in event_stats.values() if isinstance(s, dict))}</p>
                    </div>
                    <i class="fas fa-stream text-indigo-400 text-xl"></i>
                </div>
                <p class="text-sm text-gray-500 mt-2">Total events in streams</p>
            </div>

            <div class="card bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div class="flex justify-between items-start">
                    <div>
                        <p class="text-gray-400 text-sm">Memory System</p>
                        <p class="text-2xl font-bold mt-1">{memory_stats.get('semantic_memories', 0)}</p>
                    </div>
                    <i class="fas fa-brain text-purple-400 text-xl"></i>
                </div>
                <p class="text-sm text-gray-500 mt-2">Semantic memories stored</p>
            </div>

            <div class="card bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div class="flex justify-between items-start">
                    <div>
                        <p class="text-gray-400 text-sm">Recent Traces</p>
                        <p class="text-2xl font-bold mt-1">{len(traces)}</p>
                    </div>
                    <i class="fas fa-chart-line text-green-400 text-xl"></i>
                </div>
                <p class="text-sm text-gray-500 mt-2">In last hour</p>
            </div>
        </div>

        <!-- Main Content Grid -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Event Streams -->
            <div class="bg-gray-800 rounded-lg border border-gray-700 p-6">
                <h2 class="text-lg font-semibold mb-4 flex items-center">
                    <i class="fas fa-stream mr-2 text-indigo-400"></i>Event Streams
                </h2>
                <div class="space-y-4">
                    {self._render_stream_stats(event_stats)}
                </div>
            </div>

            <!-- Recent Traces -->
            <div class="bg-gray-800 rounded-lg border border-gray-700 p-6">
                <h2 class="text-lg font-semibold mb-4 flex items-center">
                    <i class="fas fa-history mr-2 text-green-400"></i>Recent Activity
                </h2>
                <div class="space-y-2 max-h-64 overflow-y-auto">
                    {self._render_traces(traces)}
                </div>
            </div>
        </div>

        <!-- Architecture Diagram -->
        <div class="mt-8 bg-gray-800 rounded-lg border border-gray-700 p-6">
            <h2 class="text-lg font-semibold mb-4 flex items-center">
                <i class="fas fa-project-diagram mr-2 text-purple-400"></i>System Architecture
            </h2>
            <div class="flex justify-center">
                <pre class="text-sm text-gray-400">
┌─────────────────────────────────────────────────────────────────┐
│                        Kubani Agent System                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ Sentinel │───▶│  Event   │───▶│  Healer  │───▶│ Explorer │  │
│  │  Agent   │    │   Bus    │    │  Agent   │    │  Agent   │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│       │              │                │               │         │
│       ▼              ▼                ▼               ▼         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Memory System                         │   │
│  │  ┌─────────┐  ┌──────────┐  ┌──────────┐               │   │
│  │  │ Working │  │ Episodic │  │ Semantic │               │   │
│  │  └─────────┘  └──────────┘  └──────────┘               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                </pre>
            </div>
        </div>
    </main>

    <script>
        // Auto-refresh every 30 seconds
        setTimeout(() => location.reload(), 30000);
    </script>
</body>
</html>
"""

    def _render_stream_stats(self, stats: dict) -> str:
        """Render event stream statistics."""
        if not stats or "error" in stats:
            return '<p class="text-gray-500">No stream data available</p>'

        html = []
        for stream, info in stats.items():
            if isinstance(info, dict) and "length" in info:
                html.append(f"""
                    <div class="flex justify-between items-center p-3 bg-gray-700 rounded">
                        <span class="text-sm">{stream}</span>
                        <span class="text-indigo-400 font-mono">{info['length']}</span>
                    </div>
                """)

        return "\n".join(html) if html else '<p class="text-gray-500">No streams found</p>'

    def _render_traces(self, traces: list) -> str:
        """Render recent traces."""
        if not traces:
            return '<p class="text-gray-500">No recent activity</p>'

        html = []
        for trace in traces[-10:]:
            timestamp = trace.get("timestamp", "")[:19]
            agent = trace.get("agent", "unknown")
            action = trace.get("action", "")[:40]
            status = trace.get("status", "unknown")

            status_class = {
                "success": "text-green-400",
                "error": "text-red-400",
                "running": "text-yellow-400",
            }.get(status, "text-gray-400")

            html.append(f"""
                <div class="flex justify-between items-center p-2 bg-gray-700 rounded text-sm">
                    <div>
                        <span class="text-gray-400">{timestamp}</span>
                        <span class="ml-2 text-indigo-300">{agent}</span>
                        <span class="ml-2">{action}</span>
                    </div>
                    <span class="{status_class}">{status}</span>
                </div>
            """)

        return "\n".join(html)

    async def run(self) -> None:
        """Run the dashboard server."""
        from aiohttp import web

        await self.metrics.connect()

        async def index_handler(request: web.Request) -> web.Response:
            data = {
                "event_bus": await self.metrics.get_event_bus_stats(),
                "sentinel": await self.metrics.get_sentinel_stats(),
                "memory": await self.metrics.get_memory_stats(),
                "traces": self.traces.get_traces(),
            }
            html = self._generate_html(data)
            return web.Response(text=html, content_type="text/html")

        async def api_stats_handler(request: web.Request) -> web.Response:
            data = {
                "event_bus": await self.metrics.get_event_bus_stats(),
                "sentinel": await self.metrics.get_sentinel_stats(),
                "memory": await self.metrics.get_memory_stats(),
            }
            return web.json_response(data)

        async def api_traces_handler(request: web.Request) -> web.Response:
            limit = int(request.query.get("limit", 50))
            agent = request.query.get("agent")
            return web.json_response(self.traces.get_traces(limit=limit, agent=agent))

        app = web.Application()
        app.router.add_get("/", index_handler)
        app.router.add_get("/api/stats", api_stats_handler)
        app.router.add_get("/api/traces", api_traces_handler)

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        logger.info(f"Dashboard running at http://{self.host}:{self.port}")

        # Keep running
        while True:
            await asyncio.sleep(3600)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Kubani Observability Dashboard")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=3000, help="Port to bind to")
    parser.add_argument("--redis-url", help="Redis URL")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    dashboard = Dashboard(
        host=args.host,
        port=args.port,
        redis_url=args.redis_url,
    )

    asyncio.run(dashboard.run())


if __name__ == "__main__":
    main()
