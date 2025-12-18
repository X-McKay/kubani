"""
Strands agent hooks for k8s-monitor.

Provides lifecycle hooks for safety, observability, and Discord streaming.
"""

import logging
import os
import time
from typing import Any

from strands.hooks.events import (
    AfterModelCallEvent,
    AfterToolCallEvent,
    BeforeToolCallEvent,
)
from strands.hooks.registry import HookProvider, HookRegistry

logger = logging.getLogger(__name__)


class SafetyHook(HookProvider):
    """
    Safety hook to block dangerous operations.

    Prevents the agent from executing destructive operations like
    deleting pods, deployments, or other resources.
    """

    # Tools that should be blocked entirely
    BLOCKED_TOOLS = {
        "pods_delete",
        "resources_delete",
        "helm_uninstall",
        "deployments_delete",
        "delete_namespace",
        "kubectl_delete",
        "shell",  # Block shell access for safety
    }

    # Tools that require additional validation
    RESTRICTED_TOOLS = {
        "scale_deployment": lambda args: args.get("replicas", 0) <= 10,
        "restart_pod": lambda args: True,  # Allow restarts
    }

    def register_hooks(self, registry: HookRegistry) -> None:
        """Register safety check callbacks."""
        registry.add_callback(BeforeToolCallEvent, self.check_safety)

    def check_safety(self, event: BeforeToolCallEvent) -> None:
        """Check if a tool call is safe before execution."""
        # Get tool name from selected_tool attribute
        tool = event.selected_tool
        tool_name = tool.tool_name if tool and hasattr(tool, "tool_name") else "unknown"

        # Block dangerous tools
        if tool_name in self.BLOCKED_TOOLS:
            logger.warning(f"Blocked dangerous tool: {tool_name}")
            raise ToolBlockedError(f"Operation blocked for safety: {tool_name}")

        # Validate restricted tools
        if tool_name in self.RESTRICTED_TOOLS:
            validator = self.RESTRICTED_TOOLS[tool_name]
            args = event.tool_use.input if hasattr(event.tool_use, "input") else {}
            if not validator(args):
                logger.warning(f"Restricted tool validation failed: {tool_name}")
                raise ToolBlockedError(f"Tool {tool_name} arguments failed validation")


class ToolBlockedError(Exception):
    """Raised when a tool is blocked by safety checks."""

    pass


class ObservabilityHook(HookProvider):
    """
    Observability hook for logging and metrics.

    Logs tool calls and tracks timing/metrics for monitoring.
    """

    def __init__(self):
        self.tool_timings: dict[str, list[float]] = {}
        self.tool_call_start: dict[str, float] = {}

    def register_hooks(self, registry: HookRegistry) -> None:
        """Register observability callbacks."""
        registry.add_callback(BeforeToolCallEvent, self.on_tool_start)
        registry.add_callback(AfterToolCallEvent, self.on_tool_end)
        registry.add_callback(AfterModelCallEvent, self.on_model_response)

    def on_tool_start(self, event: BeforeToolCallEvent) -> None:
        """Log tool call start and record timing."""
        tool = event.selected_tool
        tool_name = tool.tool_name if tool and hasattr(tool, "tool_name") else "unknown"
        tool_use_id = event.tool_use.tool_use_id if hasattr(event.tool_use, "tool_use_id") else "unknown"

        logger.info(f"Tool call started: {tool_name} (id: {tool_use_id})")
        self.tool_call_start[tool_use_id] = time.time()

    def on_tool_end(self, event: AfterToolCallEvent) -> None:
        """Log tool call completion and record timing."""
        tool = event.selected_tool
        tool_name = tool.tool_name if tool and hasattr(tool, "tool_name") else "unknown"
        tool_use_id = event.tool_use.tool_use_id if hasattr(event.tool_use, "tool_use_id") else "unknown"

        # Calculate duration
        start_time = self.tool_call_start.pop(tool_use_id, None)
        duration = time.time() - start_time if start_time else 0

        # Track timing
        if tool_name not in self.tool_timings:
            self.tool_timings[tool_name] = []
        self.tool_timings[tool_name].append(duration)

        # Determine success status
        status = "completed" if not event.error else "error"

        logger.info(f"Tool call completed: {tool_name} ({status}) in {duration:.2f}s")

    def on_model_response(self, event: AfterModelCallEvent) -> None:
        """Log model response metadata."""
        stop_reason = event.stop_reason if hasattr(event, "stop_reason") else "unknown"
        logger.debug(f"Model response received (stop_reason: {stop_reason})")

    def get_metrics(self) -> dict[str, Any]:
        """Get collected metrics summary."""
        metrics = {}
        for tool_name, timings in self.tool_timings.items():
            metrics[tool_name] = {
                "call_count": len(timings),
                "avg_duration": sum(timings) / len(timings) if timings else 0,
                "max_duration": max(timings) if timings else 0,
            }
        return metrics


class DiscordStreamHook(HookProvider):
    """
    Discord streaming hook for real-time updates.

    Streams agent thinking and actions to Discord in real-time.
    """

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
        self.buffer: list[str] = []
        self.last_flush_time = time.time()
        self.flush_interval = 5.0  # seconds

    def register_hooks(self, registry: HookRegistry) -> None:
        """Register Discord streaming callbacks."""
        registry.add_callback(AfterToolCallEvent, self.on_tool_complete)
        registry.add_callback(AfterModelCallEvent, self.on_model_thinking)

    def on_tool_complete(self, event: AfterToolCallEvent) -> None:
        """Stream tool completion to Discord."""
        tool = event.selected_tool
        tool_name = tool.tool_name if tool and hasattr(tool, "tool_name") else "unknown"

        # Add to buffer
        self.buffer.append(f"✅ Called `{tool_name}`")

        # Flush if interval passed
        self._maybe_flush()

    def on_model_thinking(self, event: AfterModelCallEvent) -> None:
        """Stream model thinking to Discord (summarized)."""
        # Only stream significant thinking, not every response
        stop_reason = event.stop_reason if hasattr(event, "stop_reason") else None

        if stop_reason == "tool_use":
            self.buffer.append("🤔 Analyzing and preparing tool call...")
        elif stop_reason == "end_turn":
            self.buffer.append("💡 Completed analysis")

        self._maybe_flush()

    def _maybe_flush(self) -> None:
        """Flush buffer if enough time has passed."""
        if time.time() - self.last_flush_time >= self.flush_interval and self.buffer:
            self._flush()

    def _flush(self) -> None:
        """Send buffered messages to Discord."""
        if not self.webhook_url or not self.buffer:
            return

        try:
            from core_agents import DiscordEmbed, send_discord_message_sync

            message = "\n".join(self.buffer[-10:])  # Last 10 items
            embed = DiscordEmbed(
                title="Agent Activity",
                description=message,
                color=0x3498DB,
            )
            send_discord_message_sync(embeds=[embed], webhook_url=self.webhook_url)
            self.buffer.clear()
            self.last_flush_time = time.time()

        except Exception as e:
            logger.error(f"Failed to flush to Discord: {e}")

    def force_flush(self) -> None:
        """Force immediate flush of buffer."""
        self._flush()


# Default hook instances
def create_default_hooks(
    enable_safety: bool = True,
    enable_observability: bool = True,
    enable_discord: bool = False,
) -> list[HookProvider]:
    """
    Create default hook configuration.

    Args:
        enable_safety: Enable safety hook to block dangerous operations
        enable_observability: Enable observability hook for logging/metrics
        enable_discord: Enable Discord streaming hook

    Returns:
        List of configured hook providers
    """
    hooks = []

    if enable_safety:
        hooks.append(SafetyHook())

    if enable_observability:
        hooks.append(ObservabilityHook())

    if enable_discord:
        hooks.append(DiscordStreamHook())

    return hooks
