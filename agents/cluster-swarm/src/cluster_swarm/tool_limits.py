"""
Tool result limiting for context management.

Limits tool output size to prevent context overflow during swarm investigations.
Based on the pattern from k8s-monitor's healer.py.
"""

import logging
import os
from typing import Any

from strands.types.tools import AgentTool, ToolSpec, ToolUse

logger = logging.getLogger(__name__)

# Tool result size limits - can be overridden via environment variables
MAX_LOG_LINES = int(os.getenv("SWARM_MAX_LOG_LINES", "50"))
MAX_EVENTS = int(os.getenv("SWARM_MAX_EVENTS", "20"))
MAX_RESULT_CHARS = int(os.getenv("SWARM_MAX_RESULT_CHARS", "4000"))


def truncate_result(result: str, max_chars: int = MAX_RESULT_CHARS) -> str:
    """
    Truncate a tool result to prevent context overflow.

    Keeps first 70% and last 20% of content to preserve both
    the beginning context and recent/relevant information.
    """
    if len(result) <= max_chars:
        return result

    keep_start = int(max_chars * 0.7)
    keep_end = int(max_chars * 0.2)
    truncated_chars = len(result) - max_chars

    return (
        result[:keep_start]
        + f"\n\n... [TRUNCATED {truncated_chars} chars] ...\n\n"
        + result[-keep_end:]
    )


class LimitedMCPAgentTool(AgentTool):
    """
    Wrapper that limits result size for MCP tools to prevent context overflow.

    For pods_log: limits tail to MAX_LOG_LINES
    For events_list: truncates result to MAX_EVENTS items
    All tools: truncates final result to MAX_RESULT_CHARS
    """

    def __init__(self, original_tool: AgentTool, name: str):
        """
        Initialize the limited tool wrapper.

        Args:
            original_tool: The MCP tool to wrap
            name: The tool name (used for applying specific limits)
        """
        super().__init__()
        self._original = original_tool
        self._name = name

    @property
    def tool_name(self) -> str:
        """Get the name of the tool."""
        return self._name

    @property
    def tool_spec(self) -> ToolSpec:
        """Get the specification of the tool."""
        return self._original.tool_spec

    @property
    def tool_type(self) -> str:
        """Get the type of the tool."""
        return self._original.tool_type

    async def stream(self, tool_use: ToolUse, invocation_state: dict[str, Any], **kwargs: Any):
        """
        Stream the tool execution, applying limits to input and truncating output.

        Args:
            tool_use: The tool use request containing tool ID and parameters
            invocation_state: Context for the tool invocation
            **kwargs: Additional keyword arguments

        Yields:
            Tool events with the last being the tool result
        """
        # Apply input limits for specific tools
        tool_input = tool_use.get("input", {})

        if self._name == "pods_log":
            # Limit log lines unless explicitly set to a smaller value
            current_tail = tool_input.get("tail", 100)
            if current_tail > MAX_LOG_LINES:
                tool_input["tail"] = MAX_LOG_LINES
                logger.debug(f"Limited pods_log tail to {MAX_LOG_LINES}")

        # Delegate to original tool and process results
        async for event in self._original.stream(tool_use, invocation_state, **kwargs):
            # Check if this is a result event with content to truncate
            if hasattr(event, "result") and event.result:
                result = event.result
                content = result.get("content", [])

                # Truncate text content if too large
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        text = item["text"]
                        if isinstance(text, str) and len(text) > MAX_RESULT_CHARS:
                            logger.info(
                                f"Truncating {self._name} result from {len(text)} "
                                f"to ~{MAX_RESULT_CHARS} chars"
                            )
                            item["text"] = truncate_result(text, MAX_RESULT_CHARS)

            yield event


def wrap_tools_with_limits(tools: list[AgentTool]) -> list[AgentTool]:
    """
    Wrap a list of MCP tools with result limiting.

    Args:
        tools: List of MCP agent tools to wrap

    Returns:
        List of LimitedMCPAgentTool wrappers
    """
    return [LimitedMCPAgentTool(tool, tool.tool_name) for tool in tools]
