"""
Observability Dashboard for Kubani Development.

Provides a real-time web-based dashboard for:
- Live trace visualization
- Performance metrics
- Evaluation results
- Memory system state
"""

import asyncio
import json
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DashboardData:
    """Manages data for the dashboard."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._traces: list[dict] = []
        self._metrics: dict[str, list] = {}
        self._evaluations: list[dict] = []

    def add_trace(self, trace: dict) -> None:
        """Add a trace entry."""
        trace["timestamp"] = datetime.now(UTC).isoformat()
        self._traces.append(trace)
        # Keep last 1000 traces
        if len(self._traces) > 1000:
            self._traces = self._traces[-1000:]

    def add_metric(self, name: str, value: float) -> None:
        """Add a metric value."""
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append({
            "value": value,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        # Keep last 100 values per metric
        if len(self._metrics[name]) > 100:
            self._metrics[name] = self._metrics[name][-100:]

    def get_traces(self, limit: int = 50) -> list[dict]:
        """Get recent traces."""
        return self._traces[-limit:]

    def get_metrics(self) -> dict[str, list]:
        """Get all metrics."""
        return self._metrics

    def load_evaluations(self) -> list[dict]:
        """Load evaluation results from disk."""
        eval_dir = self.project_root / "eval-results"
        if not eval_dir.exists():
            return []

        evaluations = []
        for agent_dir in eval_dir.iterdir():
            if agent_dir.is_dir():
                for report_file in agent_dir.glob("report_*.json"):
                    try:
                        data = json.loads(report_file.read_text())
                        evaluations.append(data)
                    except Exception as e:
                        logger.warning(f"Failed to load {report_file}: {e}")

        return sorted(evaluations, key=lambda x: x.get("timestamp", ""), reverse=True)


def generate_dashboard_html(data: DashboardData) -> str:
    """Generate the dashboard HTML."""
    traces = data.get_traces()
    metrics = data.get_metrics()
    evaluations = data.load_evaluations()[:10]

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kubani Development Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .trace-entry {{ transition: all 0.3s ease; }}
        .trace-entry:hover {{ background-color: #f3f4f6; }}
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <nav class="bg-indigo-600 text-white p-4">
        <div class="container mx-auto flex justify-between items-center">
            <h1 class="text-2xl font-bold">Kubani Dev Dashboard</h1>
            <div class="text-sm">
                <span id="status" class="px-2 py-1 bg-green-500 rounded">Connected</span>
            </div>
        </div>
    </nav>

    <main class="container mx-auto p-4">
        <!-- Metrics Section -->
        <section class="mb-8">
            <h2 class="text-xl font-semibold mb-4">Metrics</h2>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div class="bg-white rounded-lg shadow p-4">
                    <h3 class="text-gray-500 text-sm">Total Traces</h3>
                    <p class="text-3xl font-bold">{len(traces)}</p>
                </div>
                <div class="bg-white rounded-lg shadow p-4">
                    <h3 class="text-gray-500 text-sm">Active Metrics</h3>
                    <p class="text-3xl font-bold">{len(metrics)}</p>
                </div>
                <div class="bg-white rounded-lg shadow p-4">
                    <h3 class="text-gray-500 text-sm">Evaluations</h3>
                    <p class="text-3xl font-bold">{len(evaluations)}</p>
                </div>
            </div>
        </section>

        <!-- Traces Section -->
        <section class="mb-8">
            <h2 class="text-xl font-semibold mb-4">Recent Traces</h2>
            <div class="bg-white rounded-lg shadow overflow-hidden">
                <table class="min-w-full">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">Time</th>
                            <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">Agent</th>
                            <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">Action</th>
                            <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">Duration</th>
                            <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">Status</th>
                        </tr>
                    </thead>
                    <tbody id="traces-body">
                        {''.join(_render_trace_row(t) for t in traces[-20:])}
                    </tbody>
                </table>
            </div>
        </section>

        <!-- Evaluations Section -->
        <section class="mb-8">
            <h2 class="text-xl font-semibold mb-4">Recent Evaluations</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                {''.join(_render_evaluation_card(e) for e in evaluations[:6])}
            </div>
        </section>
    </main>

    <script>
        // Auto-refresh every 5 seconds
        setInterval(() => {{
            fetch('/api/traces')
                .then(r => r.json())
                .then(data => {{
                    // Update traces table
                    console.log('Updated traces:', data.length);
                }});
        }}, 5000);
    </script>
</body>
</html>
"""


def _render_trace_row(trace: dict) -> str:
    """Render a trace table row."""
    timestamp = trace.get("timestamp", "")[:19]
    agent = trace.get("agent", "unknown")
    action = trace.get("action", "")[:50]
    duration = trace.get("duration", 0)
    status = trace.get("status", "unknown")

    status_color = "green" if status == "success" else "red" if status == "error" else "yellow"

    return f"""
        <tr class="trace-entry border-t">
            <td class="px-4 py-2 text-sm text-gray-500">{timestamp}</td>
            <td class="px-4 py-2 text-sm">{agent}</td>
            <td class="px-4 py-2 text-sm">{action}</td>
            <td class="px-4 py-2 text-sm">{duration:.2f}s</td>
            <td class="px-4 py-2">
                <span class="px-2 py-1 text-xs rounded bg-{status_color}-100 text-{status_color}-800">
                    {status}
                </span>
            </td>
        </tr>
    """


def _render_evaluation_card(evaluation: dict) -> str:
    """Render an evaluation card."""
    agent = evaluation.get("agent", "unknown")
    timestamp = evaluation.get("timestamp", "")[:10]
    summary = evaluation.get("summary", {})
    status = summary.get("overall_status", "unknown")
    score = summary.get("average_score", 0)

    status_color = "green" if status == "passed" else "red"

    return f"""
        <div class="bg-white rounded-lg shadow p-4">
            <div class="flex justify-between items-start mb-2">
                <h3 class="font-semibold">{agent}</h3>
                <span class="px-2 py-1 text-xs rounded bg-{status_color}-100 text-{status_color}-800">
                    {status}
                </span>
            </div>
            <p class="text-sm text-gray-500 mb-2">{timestamp}</p>
            <div class="flex justify-between text-sm">
                <span>Score: {score:.2f}</span>
                <span>Passed: {summary.get('passed', 0)}/{summary.get('total', 0)}</span>
            </div>
        </div>
    """


def start_dashboard(
    project_root: Path,
    host: str = "localhost",
    port: int = 3000,
) -> None:
    """Start the dashboard server."""
    from aiohttp import web

    data = DashboardData(project_root)

    async def index_handler(request: web.Request) -> web.Response:
        html = generate_dashboard_html(data)
        return web.Response(text=html, content_type="text/html")

    async def traces_handler(request: web.Request) -> web.Response:
        return web.json_response(data.get_traces())

    async def metrics_handler(request: web.Request) -> web.Response:
        return web.json_response(data.get_metrics())

    async def evaluations_handler(request: web.Request) -> web.Response:
        return web.json_response(data.load_evaluations())

    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/api/traces", traces_handler)
    app.router.add_get("/api/metrics", metrics_handler)
    app.router.add_get("/api/evaluations", evaluations_handler)

    logger.info(f"Starting dashboard at http://{host}:{port}")
    web.run_app(app, host=host, port=port)
