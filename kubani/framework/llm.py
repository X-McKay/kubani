"""LLM utilities using Strands Agent SDK.

This module provides a simple interface for LLM interactions that:
1. Uses Strands SDK internally (agentic by nature)
2. Implements LLMProtocol for testability
3. Gets configuration from kubani.framework.config

Usage:
    from kubani.framework.llm import get_llm, FrameworkLLM

    # Simple usage
    llm = get_llm()
    response = await llm.chat([{"role": "user", "content": "Hello"}])

    # With dependency injection
    async def my_function(llm: LLMProtocol):
        return await llm.chat(messages)

    # In production
    await my_function(get_llm())

    # In tests
    await my_function(MockLLM(responses=["test"]))

    # Skill execution (for skill evaluation)
    result = await llm.execute_skill(skill_sop, inputs)

    # Critic evaluation (for semantic verification)
    critique = await llm.critic_evaluate(skill_desc, test_desc, inputs, expected, actual, assertions)
"""

import logging
from dataclasses import dataclass

from strands import Agent

from kubani.framework.config import get_llm_config

logger = logging.getLogger(__name__)


@dataclass
class ChatResponse:
    """Response from chat completion with metadata."""

    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class FrameworkLLM:
    """
    LLM wrapper using Strands SDK.

    Implements LLMProtocol for dependency injection and testing.
    Uses Strands Agent for agentic workflows - even simple chat completions
    benefit from the agent abstraction for consistency across Kubani.
    """

    def __init__(
        self,
        model: str | None = None,
        api_url: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """
        Initialize LLM wrapper.

        If parameters not provided, uses kubani.framework.config.
        """
        config = get_llm_config()

        self.model = model or config.model
        self.api_url = api_url or config.api_url
        self.temperature = temperature if temperature is not None else config.temperature
        self.max_tokens = max_tokens or config.max_tokens

        self._agent: Agent | None = None
        self._current_system_prompt: str | None = None

    def _get_agent(self, system_prompt: str | None = None) -> Agent:
        """
        Get or create Strands Agent.

        Creates a new agent if system prompt changes.
        Uses OpenAIModel to connect to vLLM or other OpenAI-compatible endpoints.
        """
        from strands.models.openai import OpenAIModel

        # Create new agent if system prompt changed or first call
        if self._agent is None or system_prompt != self._current_system_prompt:
            self._current_system_prompt = system_prompt

            # Create OpenAI-compatible model pointing to our vLLM endpoint
            model = OpenAIModel(
                client_args={
                    "api_key": "not-needed",  # vLLM doesn't require API key
                    "base_url": self.api_url,
                },
                model_id=self.model,
            )

            self._agent = Agent(
                model=model,
                system_prompt=system_prompt or "",
            )
        return self._agent

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Send chat completion and return content.

        Implements LLMProtocol interface.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (currently not passed to Strands)
            max_tokens: Max tokens (uses instance default if not specified)

        Returns:
            Response content as string
        """
        # Extract system and user messages
        system_messages = [m for m in messages if m["role"] == "system"]
        user_messages = [m for m in messages if m["role"] == "user"]

        if not user_messages:
            raise ValueError("No user message in messages list")

        # Get system prompt if present
        system_prompt = system_messages[-1]["content"] if system_messages else None

        # Get agent with appropriate system prompt
        agent = self._get_agent(system_prompt)

        # Use the last user message as the prompt
        prompt = user_messages[-1]["content"]

        # Run the agent asynchronously
        try:
            result = await agent.invoke_async(prompt)
            # Strands Agent returns AgentResult - extract text content
            # The result.message is typically a dict with 'role' and 'content'
            if hasattr(result, "message"):
                message = result.message
                # Handle dict-style message
                if isinstance(message, dict):
                    content = message.get("content", [])
                    if isinstance(content, list) and content:
                        # Get text from first content block
                        text_block = content[0]
                        if isinstance(text_block, dict):
                            return text_block.get("text", str(message))
                        return str(text_block)
                    return str(content)
                return str(message)
            return str(result)
        except Exception as e:
            logger.error(f"Strands Agent error: {e}")
            raise

    async def chat_with_metadata(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Chat with full response metadata."""
        content = await self.chat(messages, temperature, max_tokens)
        return ChatResponse(
            content=content,
            model=self.model,
            # Token counts would come from Strands internals if available
        )

    def _strip_thinking_tags(self, content: str) -> str:
        """
        Strip out thinking/reasoning tags from LLM responses.

        Many reasoning models (Qwen3, DeepSeek, etc.) output thinking in
        <think>...</think> or similar tags before their actual response.

        Args:
            content: Raw LLM response content

        Returns:
            Content with thinking tags stripped out
        """
        import re

        # Strip <think>...</think> tags (Qwen3, DeepSeek)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)

        # Strip <reasoning>...</reasoning> tags
        content = re.sub(r"<reasoning>.*?</reasoning>", "", content, flags=re.DOTALL)

        # Strip <thought>...</thought> tags
        content = re.sub(r"<thought>.*?</thought>", "", content, flags=re.DOTALL)

        return content.strip()

    def _extract_json(self, content: str) -> dict:
        """
        Extract JSON from LLM response content.

        Handles:
        - Raw JSON
        - JSON wrapped in ```json ... ``` code blocks
        - JSON wrapped in ``` ... ``` code blocks

        Args:
            content: LLM response content

        Returns:
            Parsed JSON as dict

        Raises:
            json.JSONDecodeError: If no valid JSON found
        """
        import json

        # Strip thinking tags first
        content = self._strip_thinking_tags(content)

        # Try to extract from markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return json.loads(content)

    async def execute_skill(
        self,
        skill_sop: str,
        inputs: dict,
        timeout: int | None = None,
        max_retries: int = 1,
    ) -> dict:
        """
        Execute a skill by having the LLM follow the SOP.

        This is the core method for LLM-based skill evaluation. The LLM reads
        the skill's Standard Operating Procedure (SKILL.md) and executes it
        with the given inputs, returning structured JSON output.

        Args:
            skill_sop: The skill's standard operating procedure (SKILL.md content)
            inputs: Input parameters for the skill
            timeout: Optional timeout in seconds (not currently used with Strands)
            max_retries: Number of retries on failure (default: 1)

        Returns:
            Dict with 'output', 'tokens', 'latency_ms'
        """
        import json
        import time

        system_prompt = f"""You are an AI agent executing a skill. Follow the instructions in the skill SOP exactly.

SKILL SOP:
{skill_sop}

CRITICAL INSTRUCTIONS:
1. Read the "Output Format" section carefully
2. Return ONLY a JSON object with the EXACT field names specified
3. Do NOT add wrapper fields like "output", "result", or "response"
4. Do NOT add explanatory text before or after the JSON
5. The JSON must be parseable and match the schema exactly

Example: If the SOP says return {{"sum": number}}, return {{"sum": 8}}, NOT {{"output": {{"sum": 8}}}}"""

        user_prompt = f"""Execute the skill with these inputs:

{json.dumps(inputs, indent=2)}

Follow the SOP instructions and return the output as JSON."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        start_time = time.time()
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                response = await self.chat(messages)
                latency_ms = (time.time() - start_time) * 1000

                # Try to parse JSON from response
                try:
                    output = self._extract_json(response)
                except json.JSONDecodeError:
                    # If not valid JSON, return as-is
                    output = {"result": response}

                return {
                    "output": output,
                    "tokens": {
                        "prompt": 0,
                        "completion": 0,
                        "total": 0,
                    },  # Not available from Strands
                    "latency_ms": latency_ms,
                }

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(
                        f"Skill execution attempt {attempt + 1} failed: {e}, retrying..."
                    )
                    continue
                raise

        raise last_error  # type: ignore

    async def critic_evaluate(
        self,
        skill_description: str,
        test_case_description: str,
        inputs: dict,
        expected_output: dict,
        actual_output: dict,
        assertion_results: list[dict],
    ) -> dict:
        """
        Use LLM as a critic to verify if the skill execution truly achieved its goal.

        This goes beyond assertion checking to provide semantic understanding of success.
        Inspired by Voyager's self-verification mechanism.

        Args:
            skill_description: What the skill is supposed to do
            test_case_description: What this specific test case is testing
            inputs: The inputs provided to the skill
            expected_output: The expected output
            actual_output: The actual output from skill execution
            assertion_results: Results from assertion checks

        Returns:
            Dict with 'success' (bool), 'confidence' (float), 'critique' (str), 'suggestions' (str)
        """
        import json

        # Count passed/failed assertions
        passed_assertions = sum(1 for a in assertion_results if a.get("passed", False))
        total_assertions = len(assertion_results)

        # Build assertion summary
        assertion_summary = []
        for i, assertion in enumerate(assertion_results, 1):
            status = "PASSED" if assertion.get("passed") else "FAILED"
            assertion_summary.append(f"{i}. {assertion.get('type', 'unknown')}: {status}")
            if not assertion.get("passed") and "message" in assertion:
                assertion_summary.append(f"   Reason: {assertion['message']}")

        system_prompt = """You are an expert evaluator for AI agent skills. Your job is to determine if a skill execution truly achieved its intended goal.

You will be given:
1. What the skill is supposed to do
2. What this test case is testing
3. The inputs provided
4. The expected output
5. The actual output
6. Results from automated assertion checks

Your task is to provide a semantic evaluation that goes beyond simple assertion checking. Consider:
- Did the skill achieve its core objective?
- Are there subtle failures the assertions might have missed?
- Are there unintended side effects?
- Is the output semantically correct even if format differs slightly?

Respond with a JSON object:
{
    "success": true/false,  // Did the skill truly succeed?
    "confidence": 0.0-1.0,  // How confident are you? (0.0 = not at all, 1.0 = absolutely certain)
    "critique": "Detailed analysis of what happened",
    "suggestions": "Specific suggestions for improvement (if failed)"
}"""

        user_prompt = f"""Evaluate this skill execution:

**Skill Description:**
{skill_description}

**Test Case:**
{test_case_description}

**Inputs:**
{json.dumps(inputs, indent=2)}

**Expected Output:**
{json.dumps(expected_output, indent=2)}

**Actual Output:**
{json.dumps(actual_output, indent=2)}

**Assertion Results ({passed_assertions}/{total_assertions} passed):**
{chr(10).join(assertion_summary) if assertion_summary else "No assertions defined"}

Provide your evaluation as JSON."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self.chat(messages)

            # Parse the response
            result = self._extract_json(response)

            # Validate required fields
            if not all(k in result for k in ["success", "confidence", "critique"]):
                raise ValueError("Missing required fields in critic response")

            # Add suggestions if missing
            if "suggestions" not in result:
                result["suggestions"] = ""

            return result

        except Exception as e:
            logger.error(f"Critic evaluation failed: {e}")
            # Fallback: base decision on assertion results
            return {
                "success": passed_assertions == total_assertions,
                "confidence": 0.5,
                "critique": f"Critic evaluation failed ({str(e)}). Falling back to assertion results: {passed_assertions}/{total_assertions} passed.",
                "suggestions": "Fix the critic evaluation system.",
            }


# Global instance
_llm: FrameworkLLM | None = None


def get_llm() -> FrameworkLLM:
    """Get global LLM instance configured from framework."""
    global _llm
    if _llm is None:
        _llm = FrameworkLLM()
    return _llm


def reset_llm() -> None:
    """Reset global LLM (useful after config changes)."""
    global _llm
    _llm = None
