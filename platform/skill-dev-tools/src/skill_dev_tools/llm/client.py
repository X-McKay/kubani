"""LLM client wrapper for skill execution."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from LLM call."""

    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    model: str
    raw_response: dict[str, Any] | None = None


class LLMClientWrapper:
    """
    Wrapper for LLM API calls with tracing support.

    Supports OpenAI-compatible endpoints (vLLM, Ollama, etc.)
    """

    def __init__(
        self,
        base_url: str = "https://llm.almckay.io/v1",
        model: str = "Qwen3.5-9B-NVFP4",
        api_key: str = "not-needed",
        timeout: float = 120.0,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        enable_thinking: bool = True,
    ):
        """
        Initialize LLM client.

        Args:
            base_url: OpenAI-compatible API base URL
            model: Model name/ID
            api_key: API key (often not needed for local deployments)
            timeout: Request timeout in seconds
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            enable_thinking: Enable thinking mode for reasoning models
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enable_thinking = enable_thinking

        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Send chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override temperature
            max_tokens: Override max tokens

        Returns:
            LLMResponse with content and metrics
        """
        client = await self._get_client()

        # Build request
        request_body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "stream": False,
        }

        if max_tokens or self.max_tokens:
            request_body["max_tokens"] = max_tokens or self.max_tokens

        # Add thinking control for Qwen models
        if not self.enable_thinking and "qwen" in self.model.lower():
            # Add instruction to skip thinking
            if messages and messages[-1]["role"] == "user":
                messages[-1]["content"] += "\n\nRespond directly without <think> tags."

        start_time = time.time()

        try:
            response = await client.post("/chat/completions", json=request_body)
            response.raise_for_status()
            data = response.json()

            latency_ms = (time.time() - start_time) * 1000

            # Extract response
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

            return LLMResponse(
                content=content,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                latency_ms=latency_ms,
                model=self.model,
                raw_response=data,
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"LLM request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"LLM request error: {e}")
            raise

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
