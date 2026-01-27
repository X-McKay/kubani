"""Tests for LLM wrapper and protocols."""

import pytest

from kubani.framework.llm import FrameworkLLM, get_llm
from kubani.framework.protocols import LLMProtocol
from kubani.framework.testing.mocks import MockLLM


def test_framework_llm_implements_protocol():
    """Verify FrameworkLLM implements LLMProtocol."""
    llm = FrameworkLLM()
    assert isinstance(llm, LLMProtocol)


def test_mock_llm_implements_protocol():
    """Verify MockLLM implements LLMProtocol."""
    mock = MockLLM()
    assert isinstance(mock, LLMProtocol)


@pytest.mark.asyncio
async def test_mock_llm_returns_responses():
    """Test MockLLM returns configured responses."""
    mock = MockLLM(responses=["Hello!", "World!"])

    r1 = await mock.chat([{"role": "user", "content": "Hi"}])
    r2 = await mock.chat([{"role": "user", "content": "Hey"}])

    assert r1 == "Hello!"
    assert r2 == "World!"
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_mock_llm_cycles_responses():
    """Test MockLLM cycles through responses when exhausted."""
    mock = MockLLM(responses=["A", "B"])

    results = [await mock.chat([{"role": "user", "content": "test"}]) for _ in range(4)]

    assert results == ["A", "B", "A", "B"]


@pytest.mark.asyncio
async def test_mock_llm_records_calls():
    """Test MockLLM records call arguments."""
    mock = MockLLM()
    messages = [{"role": "user", "content": "Test"}]

    await mock.chat(messages, temperature=0.5)

    assert len(mock.calls) == 1
    assert mock.calls[0]["messages"] == messages
    assert mock.calls[0]["temperature"] == 0.5


def test_get_llm_returns_singleton():
    """Test get_llm returns the same instance."""
    from kubani.framework.llm import reset_llm

    reset_llm()  # Ensure clean state
    llm1 = get_llm()
    llm2 = get_llm()
    assert llm1 is llm2
    reset_llm()  # Clean up


def test_framework_llm_uses_config_defaults():
    """Test FrameworkLLM uses framework config when no params provided."""
    llm = FrameworkLLM()
    # Should have values from config (not None)
    assert llm.model is not None
    assert llm.api_url is not None
    assert llm.temperature is not None


def test_framework_llm_accepts_overrides():
    """Test FrameworkLLM accepts parameter overrides."""
    llm = FrameworkLLM(
        model="custom-model",
        api_url="http://custom:8000/v1",
        temperature=0.5,
        max_tokens=1000,
    )

    assert llm.model == "custom-model"
    assert llm.api_url == "http://custom:8000/v1"
    assert llm.temperature == 0.5
    assert llm.max_tokens == 1000


# =============================================================================
# Tests for helper methods
# =============================================================================


def test_strip_thinking_tags():
    """Test stripping thinking tags from LLM responses."""
    llm = FrameworkLLM()

    # Test <think> tags
    content = "<think>Let me think about this...</think>The answer is 42."
    assert llm._strip_thinking_tags(content) == "The answer is 42."

    # Test <reasoning> tags
    content = "<reasoning>Step 1: ...</reasoning>Result: success"
    assert llm._strip_thinking_tags(content) == "Result: success"

    # Test <thought> tags
    content = "<thought>hmm...</thought>Done!"
    assert llm._strip_thinking_tags(content) == "Done!"

    # Test multiline thinking
    content = "<think>\nLine 1\nLine 2\n</think>Final answer"
    assert llm._strip_thinking_tags(content) == "Final answer"

    # Test no tags - should return stripped content
    content = "  Just regular content  "
    assert llm._strip_thinking_tags(content) == "Just regular content"


def test_extract_json_raw():
    """Test extracting raw JSON."""
    llm = FrameworkLLM()

    content = '{"key": "value", "number": 42}'
    result = llm._extract_json(content)
    assert result == {"key": "value", "number": 42}


def test_extract_json_from_code_block():
    """Test extracting JSON from markdown code blocks."""
    llm = FrameworkLLM()

    # Test ```json block
    content = 'Some text\n```json\n{"result": true}\n```\nMore text'
    result = llm._extract_json(content)
    assert result == {"result": True}

    # Test plain ``` block
    content = '```\n{"status": "ok"}\n```'
    result = llm._extract_json(content)
    assert result == {"status": "ok"}


def test_extract_json_with_thinking_tags():
    """Test extracting JSON that follows thinking tags."""
    llm = FrameworkLLM()

    content = '<think>Let me analyze...</think>{"answer": 42}'
    result = llm._extract_json(content)
    assert result == {"answer": 42}


def test_extract_json_invalid():
    """Test that invalid JSON raises JSONDecodeError."""
    import json

    llm = FrameworkLLM()

    with pytest.raises(json.JSONDecodeError):
        llm._extract_json("not valid json")
