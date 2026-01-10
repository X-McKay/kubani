"""
Context compression and summarization for AI agents.

Implements context compression techniques to manage long conversation
histories and reduce token usage. This is essential for long-running
agents and has been shown to yield significant performance improvements.

The Claude Agent SDK achieved a 39% performance improvement using
similar summarization techniques.

Usage:
    from core_agents.context.compression import ContextCompressor

    compressor = ContextCompressor()

    # Compress conversation history
    compressed = compressor.compress_messages(messages)

    # Summarize long content
    summary = compressor.summarize(long_text, max_tokens=500)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CompressionConfig:
    """Configuration for context compression."""

    # Message compression
    max_messages_before_compression: int = 20
    messages_to_keep_recent: int = 5
    messages_to_keep_oldest: int = 2

    # Content compression
    max_content_length: int = 10000
    summary_target_length: int = 500

    # Tool output compression
    max_tool_output_length: int = 2000
    truncate_tool_outputs: bool = True

    # Compression strategies
    remove_redundant_whitespace: bool = True
    remove_code_comments: bool = False
    abbreviate_repeated_content: bool = True


@dataclass
class CompressedContext:
    """Result of context compression."""

    content: str | list[dict[str, Any]]
    original_tokens_estimate: int
    compressed_tokens_estimate: int
    compression_ratio: float
    summary_included: bool = False
    messages_removed: int = 0


class ContextCompressor:
    """
    Compresses and optimizes context for LLM consumption.

    Strategies:
    1. Message history compression with summarization
    2. Tool output truncation
    3. Redundant content removal
    4. Intelligent summarization of older context
    """

    def __init__(self, config: CompressionConfig | None = None):
        """
        Initialize the compressor.

        Args:
            config: Optional configuration
        """
        self.config = config or CompressionConfig()
        logger.debug("ContextCompressor initialized")

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Uses a simple heuristic: ~4 characters per token.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return len(text) // 4

    def compress_messages(
        self,
        messages: list[dict[str, Any]],
        summarize_fn: Any | None = None,
    ) -> CompressedContext:
        """
        Compress a list of messages.

        Keeps recent messages intact and summarizes older ones.

        Args:
            messages: List of message dicts with 'role' and 'content'
            summarize_fn: Optional async function to generate summaries

        Returns:
            CompressedContext with compressed messages
        """
        if len(messages) <= self.config.max_messages_before_compression:
            # No compression needed
            return CompressedContext(
                content=messages,
                original_tokens_estimate=self._estimate_messages_tokens(messages),
                compressed_tokens_estimate=self._estimate_messages_tokens(messages),
                compression_ratio=1.0,
            )

        original_tokens = self._estimate_messages_tokens(messages)

        # Split messages into sections
        oldest = messages[: self.config.messages_to_keep_oldest]
        middle = messages[
            self.config.messages_to_keep_oldest : -self.config.messages_to_keep_recent
        ]
        recent = messages[-self.config.messages_to_keep_recent :]

        # Create summary of middle section
        summary_content = self._create_summary(middle, summarize_fn)

        # Build compressed message list
        compressed = list(oldest)

        if summary_content:
            compressed.append(
                {
                    "role": "system",
                    "content": f"[Summary of {len(middle)} previous messages]\n{summary_content}",
                }
            )

        compressed.extend(recent)

        compressed_tokens = self._estimate_messages_tokens(compressed)

        return CompressedContext(
            content=compressed,
            original_tokens_estimate=original_tokens,
            compressed_tokens_estimate=compressed_tokens,
            compression_ratio=compressed_tokens / original_tokens if original_tokens > 0 else 1.0,
            summary_included=bool(summary_content),
            messages_removed=len(middle),
        )

    def _estimate_messages_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate total tokens in messages."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        total += self.estimate_tokens(item["text"])
        return total

    def _create_summary(
        self,
        messages: list[dict[str, Any]],
        summarize_fn: Any | None = None,
    ) -> str:
        """Create a summary of messages."""
        if not messages:
            return ""

        # Extract key information
        key_points = []
        tool_calls = []
        decisions = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if not isinstance(content, str):
                continue

            # Track tool usage
            if role == "assistant" and "tool" in content.lower():
                tool_calls.append(content[:100])

            # Track decisions/conclusions
            if any(
                word in content.lower()
                for word in ["decided", "concluded", "found", "determined", "result"]
            ):
                decisions.append(content[:150])

            # Track important information
            if any(
                word in content.lower()
                for word in ["error", "warning", "important", "critical", "success"]
            ):
                key_points.append(content[:150])

        # Build summary
        summary_parts = []

        if decisions:
            summary_parts.append("Key decisions/findings:")
            for d in decisions[:3]:
                summary_parts.append(f"  - {d}")

        if key_points:
            summary_parts.append("Important observations:")
            for p in key_points[:3]:
                summary_parts.append(f"  - {p}")

        if tool_calls:
            summary_parts.append(f"Tools used: {len(tool_calls)} calls")

        return (
            "\n".join(summary_parts) if summary_parts else f"[{len(messages)} messages summarized]"
        )

    def compress_text(self, text: str) -> str:
        """
        Compress text content.

        Args:
            text: Text to compress

        Returns:
            Compressed text
        """
        if not text:
            return text

        result = text

        # Remove redundant whitespace
        if self.config.remove_redundant_whitespace:
            result = re.sub(r"\n{3,}", "\n\n", result)
            result = re.sub(r" {2,}", " ", result)
            result = re.sub(r"\t+", " ", result)

        # Remove code comments if configured
        if self.config.remove_code_comments:
            # Remove single-line comments
            result = re.sub(r"#.*$", "", result, flags=re.MULTILINE)
            result = re.sub(r"//.*$", "", result, flags=re.MULTILINE)

        return result.strip()

    def truncate_tool_output(self, output: str, tool_name: str = "") -> str:
        """
        Truncate tool output to configured maximum.

        Args:
            output: Tool output to truncate
            tool_name: Name of the tool (for context)

        Returns:
            Truncated output
        """
        if not self.config.truncate_tool_outputs:
            return output

        if len(output) <= self.config.max_tool_output_length:
            return output

        # Keep beginning and end
        half_length = self.config.max_tool_output_length // 2
        truncated = (
            output[:half_length]
            + f"\n\n[... {len(output) - self.config.max_tool_output_length} characters truncated ...]\n\n"
            + output[-half_length:]
        )

        logger.debug(f"Truncated {tool_name} output from {len(output)} to {len(truncated)} chars")
        return truncated

    def summarize_for_context(
        self,
        content: str,
        context_type: str = "general",
        max_length: int | None = None,
    ) -> str:
        """
        Create a summary suitable for LLM context.

        Args:
            content: Content to summarize
            context_type: Type of content (general, error, tool_output)
            max_length: Maximum summary length

        Returns:
            Summarized content
        """
        max_length = max_length or self.config.summary_target_length

        if len(content) <= max_length:
            return content

        # Simple extractive summarization
        lines = content.split("\n")

        # Score lines by importance
        scored_lines = []
        for line in lines:
            score = 0
            line_lower = line.lower()

            # Important keywords
            if any(w in line_lower for w in ["error", "warning", "critical", "failed"]):
                score += 3
            if any(w in line_lower for w in ["success", "completed", "result"]):
                score += 2
            if any(w in line_lower for w in ["important", "note", "todo"]):
                score += 2

            # Headers
            if line.startswith("#") or line.startswith("##"):
                score += 2

            # Code blocks (keep some)
            if line.startswith("```"):
                score += 1

            scored_lines.append((score, line))

        # Sort by score and take top lines
        scored_lines.sort(key=lambda x: x[0], reverse=True)

        summary_lines = []
        current_length = 0

        for score, line in scored_lines:
            if current_length + len(line) > max_length:
                break
            summary_lines.append(line)
            current_length += len(line) + 1

        # Restore original order for readability
        original_order = {line: i for i, line in enumerate(lines)}
        summary_lines.sort(key=lambda x: original_order.get(x, 0))

        return "\n".join(summary_lines)

    def optimize_for_kv_cache(self, system_prompt: str) -> str:
        """
        Optimize system prompt for KV-cache efficiency.

        Moves static content to the beginning and dynamic content to the end.
        This maximizes cache hits across requests.

        Args:
            system_prompt: System prompt to optimize

        Returns:
            Optimized system prompt
        """
        # Split into sections
        sections = re.split(r"(##\s+[^\n]+)", system_prompt)

        static_sections = []
        dynamic_sections = []

        # Classify sections
        dynamic_keywords = ["current", "today", "now", "recent", "latest", "context"]

        i = 0
        while i < len(sections):
            section = sections[i]

            # Check if this is a header
            if section.startswith("##"):
                header = section.lower()
                content = sections[i + 1] if i + 1 < len(sections) else ""

                if any(kw in header for kw in dynamic_keywords):
                    dynamic_sections.append(section + content)
                else:
                    static_sections.append(section + content)
                i += 2
            else:
                # Non-header content at start is usually static
                if not static_sections:
                    static_sections.append(section)
                else:
                    dynamic_sections.append(section)
                i += 1

        # Rebuild with static first, dynamic last
        optimized = "\n".join(static_sections) + "\n" + "\n".join(dynamic_sections)
        return optimized.strip()
