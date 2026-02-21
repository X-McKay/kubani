"""Extra tools for the Nexus PI agent.

Custom @tool functions for capabilities without MCP servers:
- web_search: DuckDuckGo internet search (no API key needed)

Usage:
    from kubani.nexus.tools.extra_tools import create_extra_tools
    extras = create_extra_tools()
"""

from __future__ import annotations

import json
import logging
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)


def _format_result(data: Any) -> str:
    if data is None:
        return "No data returned."
    if isinstance(data, (dict, list)):
        return json.dumps(data, indent=2, default=str)
    return str(data)


def create_extra_tools() -> list:
    """Create custom @tool instances for the PI agent.

    Returns:
        List of Strands tool instances.
    """

    @tool
    def web_search(query: str, max_results: int = 5) -> str:
        """Search the web using DuckDuckGo. Returns titles, URLs, and snippets.

        Use this tool when the user asks to look something up, find information,
        or when you need current data that isn't in your training set.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return. Default 5, max 20.
        """
        try:
            from duckduckgo_search import DDGS

            max_results = min(max_results, 20)
            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))

            if not raw_results:
                return f"No web results found for query: {query}"

            results = []
            for r in raw_results:
                results.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", r.get("link", "")),
                        "snippet": r.get("body", r.get("snippet", "")),
                    }
                )
            return _format_result(results)
        except ImportError:
            return "Error: duckduckgo-search package not installed."
        except Exception as e:
            return f"Error searching the web: {e}"

    return [web_search]
