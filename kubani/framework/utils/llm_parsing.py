"""LLM output parsing utilities.

Functions for extracting structured data from LLM responses, handling
common issues like markdown code blocks, thinking tags, and malformed JSON.
"""

import json
import re
from typing import Any


def extract_json(text: str) -> dict[str, Any]:
    """
    Extract the first complete JSON object from text.

    Handles:
    - Markdown code blocks (```json ... ```)
    - Surrounding text before/after JSON
    - Nested braces
    - Multiple JSON objects (takes first)
    - Python dict syntax with single quotes

    Args:
        text: Text potentially containing JSON

    Returns:
        Parsed JSON as dict

    Raises:
        ValueError: If no valid JSON object found

    Example:
        >>> extract_json('Here is the result: {"key": "value"}')
        {'key': 'value'}
        >>> extract_json('```json\\n{"key": "value"}\\n```')
        {'key': 'value'}
    """
    # First, try to extract from markdown code block
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if code_block_match:
        text = code_block_match.group(1).strip()

    # Find the first '{' character
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in text: {text[:200]}")

    # Use brace counting to find the matching '}'
    depth = 0
    in_string = False
    escape_next = False
    end = -1

    for i, char in enumerate(text[start:], start=start):
        if escape_next:
            escape_next = False
            continue

        if char == "\\":
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        raise ValueError(f"Unbalanced braces in JSON: {text[:200]}")

    json_str = text[start:end]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Try to fix common LLM issues: single quotes instead of double quotes
        # Convert Python dict syntax to JSON
        try:
            import ast

            # ast.literal_eval can parse Python dict syntax with single quotes
            result = ast.literal_eval(json_str)
            if isinstance(result, dict):
                return result
        except (ValueError, SyntaxError):
            pass

        # Try replacing single quotes with double quotes (simple cases)
        try:
            fixed = json_str.replace("'", '"')
            return json.loads(fixed)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}. Text: {json_str[:200]}") from e


def clean_yaml_output(content: str) -> str:
    """
    Clean YAML output by removing code blocks and thinking tags.

    Args:
        content: Raw LLM output containing YAML

    Returns:
        Cleaned YAML content

    Example:
        >>> clean_yaml_output('<think>Planning...</think>```yaml\\nkey: value\\n```')
        'key: value'
    """
    # Remove thinking tags
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content = content.strip()

    # Remove code blocks
    if content.startswith("```yaml"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]

    if content.endswith("```"):
        content = content[:-3]

    return content.strip()


def clean_markdown_output(content: str) -> str:
    """
    Clean markdown output by removing code blocks and thinking tags.

    Args:
        content: Raw LLM output containing Markdown

    Returns:
        Cleaned Markdown content

    Example:
        >>> clean_markdown_output('```markdown\\n# Title\\n```')
        '# Title'
    """
    # Remove thinking tags
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content = content.strip()

    if content.startswith("```markdown"):
        content = content.split("```markdown", 1)[1]
        if "```" in content:
            content = content.rsplit("```", 1)[0]
    elif content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

    return content.strip()


def clean_llm_output(content: str) -> str:
    """
    Clean LLM output by removing thinking tags and code block markers.

    This is a general-purpose cleaner that removes common LLM artifacts
    without assuming a specific format.

    Args:
        content: Raw LLM output

    Returns:
        Cleaned content

    Example:
        >>> clean_llm_output('<think>Let me think...</think>\\n```\\nresult\\n```')
        'result'
    """
    content = content.strip()

    # Remove LLM thinking tags if present (e.g., <think>...</think>)
    content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)

    # Remove code block markers if present
    if content.startswith("```"):
        lines = content.split("\n")
        # Skip first line (```yaml or ```) and last line if it's closing ```
        if lines[-1].strip().startswith("```"):
            content = "\n".join(lines[1:-1])
        else:
            content = "\n".join(lines[1:])

    return content.strip()


__all__ = [
    "extract_json",
    "clean_yaml_output",
    "clean_markdown_output",
    "clean_llm_output",
]
