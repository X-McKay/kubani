"""LLM-powered skill executor."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from agent_framework.llm.client import LLMClientWrapper
from agent_framework.trace import ExecutionTrace, SpanKind, TraceSpan

logger = logging.getLogger(__name__)


class LLMSkillExecutor:
    """
    Execute skills using LLM.

    Takes a skill definition (markdown) and context, executes via LLM,
    and returns structured output with full trace.
    """

    SYSTEM_PROMPT = """You are an AI agent executing a skill. Follow the skill instructions precisely.

Given:
1. A skill definition (SKILL.md) with steps and expected behavior
2. Input context with relevant data

Your task:
1. Follow the skill steps exactly
2. Use the provided context
3. Return a JSON response with your findings/actions

IMPORTANT: Your response MUST be valid JSON. Use this format:
{
    "status": "success" | "failure" | "needs_approval",
    "summary": "Brief summary of what was done",
    "findings": ["Finding 1", "Finding 2"],
    "actions_taken": ["Action 1", "Action 2"],
    "recommendations": ["Recommendation 1"],
    "confidence": 0.0-1.0,
    "details": { ... any additional structured data ... }
}
"""

    def __init__(self, llm_client: LLMClientWrapper):
        """
        Initialize executor.

        Args:
            llm_client: LLM client for making calls
        """
        self.llm = llm_client

    async def execute(
        self,
        skill_content: str,
        skill_name: str,
        context: dict[str, Any],
        trace: ExecutionTrace,
    ) -> dict[str, Any]:
        """
        Execute a skill with LLM.

        Args:
            skill_content: Full skill markdown content
            skill_name: Name of the skill
            context: Input context for the skill
            trace: Execution trace to record to

        Returns:
            Structured output from skill execution
        """
        # Build the prompt
        user_message = self._build_prompt(skill_content, context)

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        # Create LLM call span
        llm_span = TraceSpan(
            name=f"llm.execute_skill.{skill_name}",
            kind=SpanKind.LLM_CALL,
            attributes={
                "llm.model": self.llm.model,
                "llm.temperature": self.llm.temperature,
                "skill.name": skill_name,
            },
        )
        trace.add_span(llm_span)

        try:
            # Make LLM call
            response = await self.llm.chat(messages)

            # Update span with token counts
            llm_span.input_tokens = response.input_tokens
            llm_span.output_tokens = response.output_tokens
            llm_span.attributes["llm.latency_ms"] = response.latency_ms

            # Parse response
            output = self._parse_response(response.content)

            llm_span.end()

            return output

        except Exception as e:
            llm_span.end(status="error", error=str(e))
            raise

    def _build_prompt(
        self,
        skill_content: str,
        context: dict[str, Any],
    ) -> str:
        """Build the user prompt for skill execution."""
        context_str = json.dumps(context, indent=2, default=str)

        return f"""# Skill Definition

{skill_content}

---

# Input Context

```json
{context_str}
```

---

Execute this skill with the given context. Return your response as JSON."""

    def _parse_response(self, content: str) -> dict[str, Any]:
        """Parse LLM response to extract JSON output."""
        # Try to find JSON in the response
        # First, try direct JSON parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code block
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object in the text
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: return raw content
        logger.warning("Could not parse JSON from LLM response, returning raw")
        return {
            "status": "unknown",
            "summary": "Could not parse structured response",
            "raw_response": content,
        }
