"""Nexus agentic tool models.

Models for the Pi-style agentic loop: tool calls, tool results,
and the structured output from each agentic step.

The agentic loop works as follows:
    1. LLM sees context + tool results → produces AgenticStepResult
    2. If action is TOOL_CALL: execute the tool, append result, loop
    3. If action is TOOL_CALLS: execute tools in parallel, loop
    4. If action is RESPOND: publish response, stop
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgenticAction(str, Enum):
    """What the LLM wants to do next."""

    RESPOND = "respond"
    TOOL_CALL = "tool_call"
    TOOL_CALLS = "tool_calls"


class ToolCall(BaseModel):
    """A single tool invocation requested by the LLM.

    Attributes:
        tool_name: Name of the tool (e.g., "read_file", "bash", "web/fetch-url").
        arguments: Arguments to pass to the tool.
    """

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """The result of executing a tool.

    Attributes:
        tool_name: Name of the tool that was executed.
        success: Whether the tool executed successfully.
        output: The tool's output (stdout or return value).
        error: Error message if the tool failed.
        duration_ms: How long the tool took to execute.
    """

    tool_name: str
    success: bool = True
    output: str = ""
    error: str | None = None
    duration_ms: int = 0


class AgenticStepResult(BaseModel):
    """The structured output from one agentic step (one LLM call).

    The LLM returns this structure to indicate what it wants to do next.

    Attributes:
        action: The action type (respond, tool_call, tool_calls).
        response_text: Final response text (when action is RESPOND).
        tool_call: Single tool call (when action is TOOL_CALL).
        tool_calls: Multiple parallel tool calls (when action is TOOL_CALLS).
        reasoning: Internal chain-of-thought (logged but not shown to user).
    """

    action: AgenticAction
    response_text: str | None = None
    tool_call: ToolCall | None = None
    tool_calls: list[ToolCall] | None = None
    reasoning: str = ""
