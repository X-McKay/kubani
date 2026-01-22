"""Tests for LLM skill executor."""

from unittest.mock import MagicMock

from agent_framework.llm import LLMClientWrapper, LLMSkillExecutor


class TestLLMClientWrapper:
    """Tests for LLMClientWrapper."""

    def test_client_creation(self):
        """Test client can be created with defaults."""
        client = LLMClientWrapper()
        assert client.base_url == "https://llm.almckay.io/v1"
        assert client.model == "nvidia/Qwen3-14B-FP4"

    def test_client_custom_config(self):
        """Test client with custom config."""
        client = LLMClientWrapper(
            base_url="http://localhost:11434/v1",
            model="llama2",
            temperature=0.5,
        )
        assert client.base_url == "http://localhost:11434/v1"
        assert client.model == "llama2"
        assert client.temperature == 0.5

    def test_client_strips_trailing_slash(self):
        """Test that base_url trailing slash is stripped."""
        client = LLMClientWrapper(base_url="http://localhost:8000/v1/")
        assert client.base_url == "http://localhost:8000/v1"


class TestLLMSkillExecutor:
    """Tests for LLMSkillExecutor."""

    def test_parse_json_response(self):
        """Test JSON parsing from LLM response."""
        client = MagicMock()
        executor = LLMSkillExecutor(client)

        # Direct JSON
        result = executor._parse_response('{"status": "success"}')
        assert result["status"] == "success"

        # JSON in code block
        result = executor._parse_response('```json\n{"status": "success"}\n```')
        assert result["status"] == "success"

        # JSON embedded in text
        result = executor._parse_response('Here is the result: {"status": "success"}')
        assert result["status"] == "success"

    def test_parse_invalid_response(self):
        """Test fallback for unparseable response."""
        client = MagicMock()
        executor = LLMSkillExecutor(client)

        result = executor._parse_response("This is not JSON at all")
        assert result["status"] == "unknown"
        assert "raw_response" in result

    def test_build_prompt(self):
        """Test prompt building."""
        client = MagicMock()
        executor = LLMSkillExecutor(client)

        prompt = executor._build_prompt(
            skill_content="# My Skill\n\nDo something useful.",
            context={"key": "value"},
        )

        assert "# Skill Definition" in prompt
        assert "# My Skill" in prompt
        assert "# Input Context" in prompt
        assert '"key": "value"' in prompt
