"""Vision tool for the Nexus PI agent.

Sends a screenshot (base64 PNG) to Qwen3-VL-8B via the OpenAI-compatible
vLLM API and returns a structured description of the screen.

Usage:
    from kubani.nexus.tools.vision import analyze_screen
    # Add to workspace_tools list in activities.py
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)

# VLM configuration via environment variables
VLM_API_URL = os.environ.get("VLM_API_URL", "https://vlm.almckay.io/v1")
VLM_API_KEY = os.environ.get("VLM_API_KEY", "dummy")
VLM_MODEL = os.environ.get("VLM_MODEL", "Qwen/Qwen3-VL-8B-Instruct")

_ANALYSIS_PROMPT = """/no_think
Analyze this screenshot and return a JSON object with exactly these fields:

{
  "description": "Brief description of what is visible on screen",
  "elements": [
    {"label": "element text or description", "type": "button|link|input|text|image|icon|other", "x": 123, "y": 456}
  ],
  "suggestion": "What action to take next given the task"
}

List the most important interactive elements with their approximate pixel
coordinates (x, y from top-left). Focus on elements relevant to the task.

Respond ONLY with the JSON object, no other text."""


@tool
def analyze_screen(screenshot_base64: str, task: str = "") -> dict[str, Any]:
    """Analyze a screenshot using the vision model to identify UI elements and their positions.

    Call this after taking a screenshot with the computer use tools.
    Pass the image_base64 from the screenshot result and describe what
    you're looking for in the task parameter.

    Args:
        screenshot_base64: Base64-encoded PNG image from the screenshot tool.
        task: What you're trying to find or do on screen.

    Returns:
        Dictionary with 'description', 'elements' (list with label/type/x/y), and 'suggestion'.
    """
    import httpx

    user_text = _ANALYSIS_PROMPT
    if task:
        user_text += f"\n\nTask: {task}"

    payload = {
        "model": VLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_base64}",
                        },
                    },
                ],
            }
        ],
        "max_tokens": 2048,
        "temperature": 0.1,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{VLM_API_URL}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {VLM_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()

        data = response.json()
        raw_text = data["choices"][0]["message"]["content"]

        # Strip thinking tags if present
        import re

        raw_text = re.sub(r"<think>[\s\S]*?</think>\s*", "", raw_text).strip()

        # Try to parse as JSON
        try:
            result = json.loads(raw_text)
            # Ensure expected keys exist
            return {
                "description": result.get("description", ""),
                "elements": result.get("elements", []),
                "suggestion": result.get("suggestion", ""),
            }
        except json.JSONDecodeError:
            # Fall back to raw text in description field
            logger.warning("VLM response was not valid JSON, returning raw text")
            return {
                "description": raw_text,
                "elements": [],
                "suggestion": "",
            }

    except Exception as e:
        logger.error(f"Vision analysis failed: {e}", exc_info=True)
        return {
            "description": f"Vision analysis failed: {e}",
            "elements": [],
            "suggestion": "Try taking another screenshot or proceeding without vision.",
        }
