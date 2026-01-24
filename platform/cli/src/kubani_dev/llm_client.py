"""LLM client for skill development workflow."""

import copy
import json
import logging
import time
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for interacting with LLMs (Ollama or OpenAI-compatible endpoints)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:3b",
        timeout: int = 120,
        enable_thinking: bool = True,
    ):
        """
        Initialize LLM client.

        Args:
            base_url: Base URL for the LLM API (Ollama or OpenAI-compatible)
            model: Model name to use
            timeout: Request timeout in seconds
            enable_thinking: Whether to enable thinking mode for reasoning models (Qwen3, etc.)
                            When False, disables <think> tags for faster responses with fewer tokens.
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.enable_thinking = enable_thinking
        self.is_ollama = "11434" in base_url  # Simple heuristic

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        timeout: Optional[int] = None,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request with retry logic.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            timeout: Request timeout in seconds (overrides default)
            max_retries: Number of retries on timeout (default: 2)

        Returns:
            Response dict with 'content', 'tokens', 'latency_ms'
        """
        # Apply /nothink soft switch for Qwen3 models when thinking is disabled
        # This is a workaround until vLLM deployments are updated with --reasoning-parser qwen3
        # See: https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html#thinking-budget
        if not self.enable_thinking and "qwen" in self.model.lower():
            messages = self._apply_nothink_workaround(messages)

        # Use custom timeout if provided
        original_timeout = self.timeout
        if timeout:
            self.timeout = timeout

        last_error = None
        try:
            for attempt in range(max_retries + 1):
                try:
                    if self.is_ollama:
                        return self._chat_ollama(messages, temperature, stream)
                    else:
                        return self._chat_openai(messages, temperature, max_tokens, stream)
                except Exception as e:
                    last_error = e
                    is_timeout = "timeout" in str(e).lower() or "timed out" in str(e).lower()

                    if is_timeout and attempt < max_retries:
                        # Increase timeout for retry (1.5x each time)
                        self.timeout = int(self.timeout * 1.5)
                        logger.warning(
                            f"Timeout on attempt {attempt + 1}/{max_retries + 1}, "
                            f"retrying with {self.timeout}s timeout..."
                        )
                        continue
                    else:
                        raise

            # Should not reach here, but just in case
            raise last_error
        finally:
            # Restore original timeout
            self.timeout = original_timeout

    def _apply_nothink_workaround(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Apply /nothink soft switch workaround for Qwen3 models.

        This is a temporary workaround until vLLM deployments are updated with
        --reasoning-parser qwen3 flag. The /nothink prefix tells Qwen3 to skip
        internal reasoning, reducing token usage by ~65%.

        Reference: https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html#thinking-budget

        Args:
            messages: Original message list

        Returns:
            Modified message list with /nothink prepended to first user message
        """
        # Make a deep copy to avoid modifying original messages

        messages_copy = copy.deepcopy(messages)

        # Find first user message and prepend /nothink
        for msg in messages_copy:
            if msg["role"] == "user":
                msg["content"] = "/nothink\n\n" + msg["content"]
                break

        return messages_copy

    def _chat_ollama(
        self, messages: List[Dict[str, str]], temperature: float, stream: bool
    ) -> Dict[str, Any]:
        """Chat using Ollama API."""
        url = f"{self.base_url}/api/chat"

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": temperature},
        }

        start_time = time.time()

        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()

            result = response.json()
            latency_ms = (time.time() - start_time) * 1000

            return {
                "content": result.get("message", {}).get("content", ""),
                "tokens": {
                    "prompt": result.get("prompt_eval_count", 0),
                    "completion": result.get("eval_count", 0),
                    "total": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
                },
                "latency_ms": latency_ms,
                "model": self.model,
            }

        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            raise

    def _chat_openai(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool,
    ) -> Dict[str, Any]:
        """Chat using OpenAI-compatible API."""
        url = f"{self.base_url}/v1/chat/completions"

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        # For vLLM with Qwen3/reasoning models, control thinking mode via extra_body
        # NOTE: This requires vLLM 0.9.0+ with --reasoning-parser qwen3 flag in deployment
        # Without it, this parameter is ignored and /nothink workaround is used instead
        # TODO: Remove this after vLLM deployments are updated (see docs/planning/vllm-reasoning-parser.md)
        if not self.enable_thinking:
            payload["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

        start_time = time.time()

        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()

            result = response.json()
            latency_ms = (time.time() - start_time) * 1000

            choice = result["choices"][0]
            usage = result.get("usage", {})

            return {
                "content": choice["message"]["content"],
                "tokens": {
                    "prompt": usage.get("prompt_tokens", 0),
                    "completion": usage.get("completion_tokens", 0),
                    "total": usage.get("total_tokens", 0),
                },
                "latency_ms": latency_ms,
                "model": self.model,
            }

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

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

    def generate_skill(self, description: str, context: Optional[str] = None) -> str:
        """
        Generate a skill SOP from a description.

        Args:
            description: Natural language description of the skill
            context: Additional context about the skill

        Returns:
            Generated SKILL.md content
        """
        system_prompt = """You are an expert at creating AI agent skills. Generate a complete SKILL.md file in markdown format.

The skill should include:
1. A clear title and description
2. Input parameters with types and descriptions
3. Output format specification
4. Step-by-step instructions for execution
5. Error handling guidelines
6. Example usage

Format the skill as a professional markdown document."""

        user_prompt = f"""Create a skill with the following description:

{description}"""

        if context:
            user_prompt += f"\n\nAdditional context:\n{context}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = self.chat(messages, temperature=0.7)
        return response["content"]

    def execute_skill(
        self,
        skill_sop: str,
        inputs: Dict[str, Any],
        timeout: Optional[int] = None,
        max_retries: int = 1,
    ) -> Dict[str, Any]:
        """
        Execute a skill by having the LLM follow the SOP.

        Args:
            skill_sop: The skill's standard operating procedure (SKILL.md content)
            inputs: Input parameters for the skill
            timeout: Optional timeout in seconds (overrides default)
            max_retries: Number of retries on timeout (default: 1)

        Returns:
            Dict with 'output', 'tokens', 'latency_ms'
        """
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

        # Save original timeout and set custom if provided
        original_timeout = self.timeout
        if timeout:
            self.timeout = timeout

        # Retry logic for timeouts
        response = None
        try:
            for attempt in range(max_retries + 1):
                try:
                    response = self.chat(messages, temperature=0.3)
                    break
                except Exception as e:
                    if "timeout" in str(e).lower() and attempt < max_retries:
                        logger.warning(
                            f"Timeout on attempt {attempt + 1}/{max_retries + 1}, retrying..."
                        )
                        # Increase timeout for retry
                        self.timeout = int(self.timeout * 1.5)
                        continue
                    else:
                        raise
        finally:
            # Restore original timeout
            self.timeout = original_timeout

        # Try to parse JSON from response
        content = response["content"]
        try:
            # Strip out thinking tags (Qwen3 and other reasoning models)
            content = self._strip_thinking_tags(content)

            # Extract JSON if it's wrapped in markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            output = json.loads(content)
        except json.JSONDecodeError:
            # If not valid JSON, return as-is
            output = {"result": content}

        return {
            "output": output,
            "tokens": response["tokens"],
            "latency_ms": response["latency_ms"],
        }

    def critic_evaluate(
        self,
        skill_description: str,
        test_case_description: str,
        inputs: Dict[str, Any],
        expected_output: Dict[str, Any],
        actual_output: Dict[str, Any],
        assertion_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
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
        # Count passed/failed assertions
        passed_assertions = sum(1 for a in assertion_results if a.get("passed", False))
        total_assertions = len(assertion_results)

        # Build assertion summary
        assertion_summary = []
        for i, assertion in enumerate(assertion_results, 1):
            status = "✓ PASSED" if assertion.get("passed") else "✗ FAILED"
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
{chr(10).join(assertion_summary)}

Provide your evaluation as JSON."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self.chat(
                messages, temperature=0.2
            )  # Low temperature for consistent evaluation
            content = response["content"]

            # Strip out thinking tags (Qwen3 and other reasoning models)
            content = self._strip_thinking_tags(content)

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)

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
