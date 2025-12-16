"""
LLM Client wrapper for vLLM OpenAI-compatible API.

Provides a Strands-compatible model provider that connects to the local
vLLM instance running in the cluster.
"""

import os
from typing import Any

from strands.models.openai import OpenAIModel


def create_vllm_model_provider(
    base_url: str | None = None,
    model_name: str | None = None,
    api_key: str = "not-needed",
    **kwargs: Any,
) -> OpenAIModel:
    """
    Create a Strands model provider configured for the local vLLM instance.

    Args:
        base_url: vLLM API URL. Defaults to VLLM_API_URL env var or cluster service.
        model_name: Model name to use. Defaults to VLLM_MODEL env var.
        api_key: API key (vLLM doesn't require one, but OpenAI client needs it).
        **kwargs: Additional arguments passed to OpenAIModel.

    Returns:
        OpenAIModel configured for vLLM.

    Example:
        >>> from agent_platform import create_vllm_model_provider
        >>> model = create_vllm_model_provider()
        >>> agent = Agent(model=model)
    """
    # Default to cluster-internal service URL
    default_url = "http://llm-api.vllm.svc.cluster.local:8000/v1"
    url = base_url or os.environ.get("VLLM_API_URL", default_url)

    # Default model name from environment or the deployed model
    model = model_name or os.environ.get("VLLM_MODEL", "openai/gpt-oss-20b")

    return OpenAIModel(
        client_args={
            "base_url": url,
            "api_key": api_key,
        },
        model_id=model,
        **kwargs,
    )


def create_local_vllm_provider(**kwargs: Any) -> OpenAIModel:
    """
    Create a model provider for local development (outside cluster).

    Uses localhost:8000 or port-forwarded vLLM service.
    """
    return create_vllm_model_provider(
        base_url="http://localhost:8000/v1",
        **kwargs,
    )
