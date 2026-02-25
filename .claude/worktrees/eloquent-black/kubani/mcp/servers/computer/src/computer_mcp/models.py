"""
Models for the Computer Use MCP server.
"""

from pydantic import BaseModel, Field


class ScreenshotResult(BaseModel):
    """Result of a screenshot capture."""

    image_base64: str = Field(description="PNG screenshot encoded as base64")
    width: int = Field(description="Screenshot width in pixels")
    height: int = Field(description="Screenshot height in pixels")
    url: str | None = Field(default=None, description="Current page URL")
    title: str | None = Field(default=None, description="Current page title")


class ActionResult(BaseModel):
    """Result of a browser action."""

    success: bool = Field(description="Whether the action succeeded")
    message: str = Field(default="", description="Human-readable result message")
    url: str | None = Field(default=None, description="Current page URL after action")
    error: str | None = Field(default=None, description="Error message if action failed")
