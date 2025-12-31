"""
Shared test fixtures for k8s-monitor tests.

Provides mocks and fixtures for testing swarm behavior, error scenarios,
and Discord notification validation without requiring actual LLM calls.
"""

import os
import sys
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Ensure the src directory is on the path for local development
_src_path = Path(__file__).parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from k8s_monitor.models import ClusterHealthReport, HealthStatus, Issue  # noqa: E402

# =============================================================================
# Mock Model for Deterministic Agent Responses
# =============================================================================


class MockModel:
    """
    Mock Strands model that returns predefined responses.

    Used for testing agent behavior without actual LLM calls.
    Matches responses based on patterns in the prompt.
    """

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls: list[str] = []
        self.default_response = "Mock response"

    def set_response(self, pattern: str, response: str) -> None:
        """Set a response for prompts matching the pattern."""
        self.responses[pattern] = response

    def set_default(self, response: str) -> None:
        """Set the default response when no patterns match."""
        self.default_response = response

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list | None = None,
        **kwargs: Any,
    ) -> Generator[dict[str, Any], None, None]:
        """Mock streaming response."""
        # Extract the last message content
        prompt = ""
        if messages:
            last_message = messages[-1]
            if isinstance(last_message.get("content"), str):
                prompt = last_message["content"]
            elif isinstance(last_message.get("content"), list):
                for block in last_message["content"]:
                    if isinstance(block, dict) and "text" in block:
                        prompt += block["text"]

        self.calls.append(prompt)

        # Find matching response
        for pattern, response in self.responses.items():
            if pattern.lower() in prompt.lower():
                yield {"type": "text", "text": response}
                return

        yield {"type": "text", "text": self.default_response}


@pytest.fixture
def mock_model() -> MockModel:
    """Provide a mock model for testing agent responses."""
    return MockModel()


# =============================================================================
# Swarm Flow Recorder
# =============================================================================


@dataclass
class ToolCallRecord:
    """Record of a tool call."""

    tool_name: str
    args: dict[str, Any]
    result: Any = None
    error: Exception | None = None


@dataclass
class SwarmFlowRecorder:
    """
    Records agent handoffs and tool calls during swarm execution.

    Use this to verify:
    - discord_notify is called exactly once
    - Agent handoff sequence is correct
    - No duplicate notifications
    """

    handoffs: list[tuple[str, str]] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    discord_notify_calls: int = 0
    handoff_to_agent_calls: int = 0

    def record_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: Any = None,
        error: Exception | None = None,
    ) -> None:
        """Record a tool call."""
        self.tool_calls.append(ToolCallRecord(tool_name, args, result, error))

        if tool_name == "discord_notify":
            self.discord_notify_calls += 1
        elif tool_name == "handoff_to_agent":
            self.handoff_to_agent_calls += 1
            # Record handoff if we can extract target agent
            if "agent" in args:
                self.handoffs.append(("unknown", args["agent"]))

    def assert_single_discord_notification(self) -> None:
        """Assert that discord_notify was called exactly once."""
        assert (
            self.discord_notify_calls == 1
        ), f"Expected exactly 1 discord_notify call, got {self.discord_notify_calls}"

    def assert_no_discord_handoff(self) -> None:
        """Assert that discord agent didn't hand off to another agent."""
        discord_tools = [
            tc
            for tc in self.tool_calls
            if tc.tool_name == "discord_notify" or tc.tool_name == "handoff_to_agent"
        ]

        # After discord_notify, there should be no more handoff_to_agent calls
        found_discord = False
        for tc in discord_tools:
            if tc.tool_name == "discord_notify":
                found_discord = True
            elif found_discord and tc.tool_name == "handoff_to_agent":
                pytest.fail("discord agent called handoff_to_agent after discord_notify")

    def get_tool_call_count(self, tool_name: str) -> int:
        """Get the number of times a tool was called."""
        return sum(1 for tc in self.tool_calls if tc.tool_name == tool_name)


@pytest.fixture
def flow_recorder() -> SwarmFlowRecorder:
    """Provide a swarm flow recorder for testing."""
    return SwarmFlowRecorder()


# =============================================================================
# Error Injection
# =============================================================================


class ErrorInjector:
    """
    Inject errors at specific points in execution.

    Use to test error handling for:
    - MCP connection failures
    - Kubernetes API errors
    - Discord webhook failures
    """

    def __init__(self):
        self.error_points: dict[str, Exception] = {}
        self.call_counts: dict[str, int] = {}
        self.fail_on_nth: dict[str, tuple[int, Exception]] = {}

    def fail_on(self, point: str, error: Exception) -> None:
        """Always fail at this point."""
        self.error_points[point] = error

    def fail_on_nth_call(self, point: str, n: int, error: Exception) -> None:
        """Fail on the nth call to this point."""
        self.fail_on_nth[point] = (n, error)
        self.call_counts[point] = 0

    def clear(self) -> None:
        """Clear all error injections."""
        self.error_points.clear()
        self.call_counts.clear()
        self.fail_on_nth.clear()

    def check_and_raise(self, point: str) -> None:
        """Check if an error should be raised at this point."""
        # Check always-fail points
        if point in self.error_points:
            raise self.error_points[point]

        # Check nth-call failures
        if point in self.fail_on_nth:
            self.call_counts[point] = self.call_counts.get(point, 0) + 1
            n, error = self.fail_on_nth[point]
            if self.call_counts[point] == n:
                raise error


@pytest.fixture
def error_injector() -> ErrorInjector:
    """Provide an error injector for testing."""
    return ErrorInjector()


# =============================================================================
# Sample Cluster States
# =============================================================================


@pytest.fixture
def healthy_cluster_state() -> dict[str, Any]:
    """Sample healthy cluster state."""
    return {
        "nodes": {
            "node-1": {"ready": True, "conditions": ["Ready"]},
            "node-2": {"ready": True, "conditions": ["Ready"]},
        },
        "pods": {
            "healthy_count": 42,
            "unhealthy_count": 0,
            "problem_pods": [],
        },
        "deployments": {
            "healthy_count": 10,
            "unhealthy_count": 0,
            "unhealthy_deployments": [],
        },
        "events": [],
    }


@pytest.fixture
def unhealthy_cluster_state() -> dict[str, Any]:
    """Sample unhealthy cluster state with various issues."""
    return {
        "nodes": {
            "node-1": {"ready": True, "conditions": ["Ready"]},
            "node-2": {"ready": False, "conditions": ["NotReady", "MemoryPressure"]},
        },
        "pods": {
            "healthy_count": 38,
            "unhealthy_count": 4,
            "problem_pods": [
                {
                    "name": "app-pod-1",
                    "namespace": "default",
                    "status": "CrashLoopBackOff",
                    "restarts": 15,
                },
                {
                    "name": "db-pod-1",
                    "namespace": "database",
                    "status": "Pending",
                    "restarts": 0,
                },
            ],
        },
        "deployments": {
            "healthy_count": 8,
            "unhealthy_count": 2,
            "unhealthy_deployments": [
                {"name": "app-deploy", "namespace": "default", "ready": "1/3"},
                {"name": "worker-deploy", "namespace": "jobs", "ready": "0/2"},
            ],
        },
        "events": [
            {
                "type": "Warning",
                "reason": "BackOff",
                "message": "Back-off pulling image",
                "namespace": "default",
                "count": 10,
            },
            {
                "type": "Warning",
                "reason": "FailedScheduling",
                "message": "Insufficient memory",
                "namespace": "database",
                "count": 5,
            },
        ],
    }


# =============================================================================
# Sample Reports and Issues
# =============================================================================


@pytest.fixture
def sample_healthy_report() -> ClusterHealthReport:
    """Create a sample healthy report for testing."""
    return ClusterHealthReport(
        summary="**Status:** Healthy\n\nAll systems operational.",
        status=HealthStatus.HEALTHY,
        timestamp="2024-01-01T00:00:00Z",
        issues=[],
    )


@pytest.fixture
def sample_critical_report() -> ClusterHealthReport:
    """Create a sample critical report with issues."""
    return ClusterHealthReport(
        summary="**Status:** Critical\n\n2 pods failing, 1 node down.",
        status=HealthStatus.CRITICAL,
        timestamp="2024-01-01T00:00:00Z",
        issues=[
            Issue(
                id="issue-1",
                title="Pod app-pod-1 CrashLoopBackOff",
                description="Pod is repeatedly crashing",
                severity=HealthStatus.CRITICAL,
                resource_type="Pod",
                resource_name="app-pod-1",
                namespace="default",
                detected_at="2024-01-01T00:00:00Z",
            ),
            Issue(
                id="issue-2",
                title="Node node-2 NotReady",
                description="Node is not responding",
                severity=HealthStatus.CRITICAL,
                resource_type="Node",
                resource_name="node-2",
                namespace="",
                detected_at="2024-01-01T00:00:00Z",
            ),
        ],
    )


# =============================================================================
# Mock Discord Webhook
# =============================================================================


@dataclass
class DiscordWebhookCapture:
    """Captures Discord webhook calls for testing."""

    calls: list[dict[str, Any]] = field(default_factory=list)
    should_fail: bool = False
    fail_with: Exception | None = None

    def capture(self, payload: dict[str, Any]) -> None:
        """Record a webhook call."""
        self.calls.append(payload)

    def set_failure(self, error: Exception) -> None:
        """Configure the webhook to fail with an error."""
        self.should_fail = True
        self.fail_with = error

    def clear(self) -> None:
        """Clear captured calls and reset failure state."""
        self.calls.clear()
        self.should_fail = False
        self.fail_with = None

    @property
    def call_count(self) -> int:
        """Number of webhook calls made."""
        return len(self.calls)


@pytest.fixture
def mock_discord_webhook() -> Generator[DiscordWebhookCapture, None, None]:
    """
    Mock Discord webhook that captures calls.

    Use to verify:
    - Number of notifications sent
    - Notification content
    - Error handling
    """
    capture = DiscordWebhookCapture()

    async def mock_post(url: str, json: dict[str, Any], **kwargs: Any) -> MagicMock:
        capture.capture(json)
        if capture.should_fail and capture.fail_with:
            raise capture.fail_with

        response = MagicMock()
        response.raise_for_status = MagicMock()
        return response

    with (
        patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.test/webhook"}),
        patch("httpx.AsyncClient") as mock_client_class,
    ):
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        yield capture


# =============================================================================
# MCP Client Mock
# =============================================================================


@pytest.fixture
def mock_mcp_client() -> Generator[MagicMock, None, None]:
    """
    Mock kubernetes-mcp-server MCP client.

    Use to simulate:
    - Successful K8s operations
    - Connection timeouts
    - API errors
    """
    mock_client = MagicMock()
    mock_client.start = MagicMock()
    mock_client.stop = MagicMock()
    mock_client.load_tools = AsyncMock(return_value=[])

    with patch("strands.tools.mcp.mcp_client.MCPClient", return_value=mock_client):
        yield mock_client


# =============================================================================
# Common Error Types
# =============================================================================


@pytest.fixture
def mcp_timeout_error() -> httpx.ConnectTimeout:
    """MCP connection timeout error."""
    return httpx.ConnectTimeout("Connection to kubernetes-mcp-server timed out")


@pytest.fixture
def discord_rate_limit_error() -> httpx.HTTPStatusError:
    """Discord rate limit error (429)."""
    request = httpx.Request("POST", "https://discord.test/webhook")
    response = httpx.Response(429, request=request)
    return httpx.HTTPStatusError("Rate limited", request=request, response=response)


@pytest.fixture
def k8s_api_error() -> Exception:
    """Kubernetes API error."""
    return Exception("Kubernetes API error: connection refused")


# =============================================================================
# Utility Functions
# =============================================================================


def simulate_tool_call(
    tool_name: str,
    args: dict[str, Any],
    hooks: list | None = None,
) -> None:
    """
    Simulate a tool call through the hook system.

    Raises ToolBlockedError if the tool is blocked by safety hooks.
    """
    from k8s_monitor.hooks import SafetyHook

    if hooks is None:
        hooks = [SafetyHook()]

    # Create a mock event
    mock_event = MagicMock()
    mock_tool = MagicMock()
    mock_tool.tool_name = tool_name
    mock_event.selected_tool = mock_tool
    mock_event.tool_use = MagicMock()
    mock_event.tool_use.input = args

    # Check each hook
    for hook in hooks:
        if isinstance(hook, SafetyHook):
            hook.check_safety(mock_event)
