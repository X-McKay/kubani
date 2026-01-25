"""Tests for llm_service.py - LLM interactions with mock responses.

These tests mock the LLM protocol to return canned responses,
testing the prompt construction and response parsing logic.
"""

import pytest

from kubani.workflows.skill_auto.llm_service import (
    detect_overlap,
    generate_harder_tests,
    generate_improvement,
    generate_test_cases,
    infer_skill_structure,
)


class MockLLM:
    """Mock LLM service for testing."""

    def __init__(self, responses: list[str] | str):
        """
        Initialize with canned responses.

        Args:
            responses: Single response string or list of responses to cycle through
        """
        if isinstance(responses, str):
            responses = [responses]
        self._responses = iter(responses)
        self.calls: list[dict] = []

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Record call and return next canned response."""
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return next(self._responses)

    async def close(self) -> None:
        """No-op for mock."""
        pass


class TestInferSkillStructure:
    """Tests for infer_skill_structure function."""

    @pytest.mark.asyncio
    async def test_parses_json_response(self):
        """Parse valid JSON response from LLM."""
        response = """{
            "name": "diagnose-oom",
            "description": "Diagnose OOMKilled pods",
            "inputs": {"pod_name": {"type": "string", "required": true}},
            "outputs": {"diagnosis": {"type": "string"}},
            "steps": ["Check events", "Analyze limits"],
            "error_handling": ["Handle missing pod"],
            "examples": []
        }"""
        llm = MockLLM(response)

        result = await infer_skill_structure(llm, "A skill to diagnose OOM killed pods")

        assert result["name"] == "diagnose-oom"
        assert result["description"] == "Diagnose OOMKilled pods"
        assert result["inputs"]["pod_name"]["type"] == "string"
        assert len(result["steps"]) == 2

    @pytest.mark.asyncio
    async def test_handles_code_block_response(self):
        """Handle response wrapped in markdown code block."""
        response = """Here's the skill structure:

```json
{
    "name": "test-skill",
    "description": "Test description"
}
```

This should work."""
        llm = MockLLM(response)

        result = await infer_skill_structure(llm, "Test skill")

        assert result["name"] == "test-skill"

    @pytest.mark.asyncio
    async def test_includes_context_in_prompt(self):
        """Include additional context in the prompt."""
        llm = MockLLM('{"name": "test", "description": "test"}')

        await infer_skill_structure(
            llm,
            "Test skill",
            context="This is for Kubernetes environments",
        )

        # Check that context was included in the prompt
        prompt = llm.calls[0]["messages"][0]["content"]
        assert "Kubernetes environments" in prompt

    @pytest.mark.asyncio
    async def test_prompt_structure(self):
        """Verify prompt includes required sections."""
        llm = MockLLM('{"name": "test", "description": "test"}')

        await infer_skill_structure(llm, "Diagnose memory issues")

        prompt = llm.calls[0]["messages"][0]["content"]
        assert "SKILL DESCRIPTION:" in prompt
        assert "Diagnose memory issues" in prompt
        assert "JSON object" in prompt
        assert '"name"' in prompt
        assert '"inputs"' in prompt


class TestDetectOverlap:
    """Tests for detect_overlap function."""

    @pytest.mark.asyncio
    async def test_no_existing_skills(self):
        """Return no overlap when no existing skills."""
        llm = MockLLM("")  # Won't be called

        result = await detect_overlap(llm, "New skill", [])

        assert result.has_overlap is False
        assert result.confidence == 1.0
        assert llm.calls == []  # LLM not called

    @pytest.mark.asyncio
    async def test_overlap_detected(self):
        """Detect overlap with existing skills."""
        response = """{
            "has_overlap": true,
            "confidence": 0.85,
            "overlapping_skills": ["memory-troubleshooting"],
            "reasoning": "Both diagnose memory issues",
            "recommendation": "merge"
        }"""
        llm = MockLLM(response)

        existing = [
            {"name": "memory-troubleshooting", "description": "Debug memory issues"},
        ]
        result = await detect_overlap(llm, "Diagnose OOM pods", existing)

        assert result.has_overlap is True
        assert result.confidence == 0.85
        assert "memory-troubleshooting" in result.overlapping_skills
        assert result.recommendation == "merge"

    @pytest.mark.asyncio
    async def test_no_overlap_detected(self):
        """No overlap with distinct skills."""
        response = """{
            "has_overlap": false,
            "confidence": 0.95,
            "overlapping_skills": [],
            "reasoning": "Completely different domains",
            "recommendation": "proceed"
        }"""
        llm = MockLLM(response)

        existing = [
            {"name": "deploy-app", "description": "Deploy applications"},
        ]
        result = await detect_overlap(llm, "Debug network issues", existing)

        assert result.has_overlap is False
        assert result.recommendation == "proceed"

    @pytest.mark.asyncio
    async def test_uses_low_temperature(self):
        """Use low temperature for consistent analysis."""
        llm = MockLLM(
            '{"has_overlap": false, "confidence": 1.0, "overlapping_skills": [], "reasoning": "", "recommendation": "proceed"}'
        )

        await detect_overlap(llm, "Test", [{"name": "other", "description": ""}])

        assert llm.calls[0]["temperature"] == 0.3


class TestGenerateTestCases:
    """Tests for generate_test_cases function."""

    @pytest.mark.asyncio
    async def test_generates_yaml(self):
        """Generate valid YAML test cases."""
        response = """test_cases:
  - name: basic_test
    description: Test basic functionality
    inputs:
      param: value
    expected:
      result: success
    assertions:
      - type: exists
        field: result
"""
        llm = MockLLM(response)

        spec = {
            "name": "test-skill",
            "description": "Test skill",
            "inputs": {"param": {"type": "string"}},
            "outputs": {"result": {"type": "string"}},
            "examples": [],
        }
        result = await generate_test_cases(llm, spec)

        assert "test_cases:" in result
        assert "basic_test" in result

    @pytest.mark.asyncio
    async def test_wraps_bare_list(self):
        """Wrap bare YAML list in test_cases key."""
        response = """- name: test1
  description: First test
- name: test2
  description: Second test
"""
        llm = MockLLM(response)

        spec = {"name": "test", "description": "test", "inputs": {}, "outputs": {}}
        result = await generate_test_cases(llm, spec)

        assert "test_cases:" in result

    @pytest.mark.asyncio
    async def test_includes_seed_tests(self):
        """Include seed tests in the prompt."""
        llm = MockLLM("test_cases: []")

        seed = "- name: seed_test\n  description: Seed"
        await generate_test_cases(
            llm,
            {"name": "test", "description": "test", "inputs": {}, "outputs": {}},
            seed_tests=seed,
        )

        prompt = llm.calls[0]["messages"][0]["content"]
        assert "SEED TEST CASES" in prompt
        assert "seed_test" in prompt


class TestGenerateHarderTests:
    """Tests for generate_harder_tests function."""

    @pytest.mark.asyncio
    async def test_generates_harder_tests(self):
        """Generate harder test cases targeting weaknesses."""
        response = """- name: edge_case_empty_input
  description: Test with empty input
  inputs: {}
  expected:
    error: true
"""
        llm = MockLLM(response)

        result = await generate_harder_tests(
            llm,
            skill_name="test-skill",
            current_test_cases="test_cases:\n  - name: basic",
            accuracy=0.7,
            tests_passed=3,
            tests_total=5,
            failing_tests=[{"name": "test_x", "reason": "missing field"}],
            count=2,
        )

        assert "edge_case_empty_input" in result

    @pytest.mark.asyncio
    async def test_includes_failure_info(self):
        """Include failure information in the prompt."""
        llm = MockLLM("test_cases: []")

        await generate_harder_tests(
            llm,
            skill_name="my-skill",
            current_test_cases="test_cases: []",
            accuracy=0.6,
            tests_passed=3,
            tests_total=5,
            failing_tests=[
                {"name": "test_edge", "reason": "timeout"},
                {"name": "test_boundary", "reason": "wrong output"},
            ],
            count=2,
        )

        prompt = llm.calls[0]["messages"][0]["content"]
        assert "60.0%" in prompt  # Accuracy
        assert "3/5" in prompt  # Tests passed
        assert "test_edge" in prompt
        assert "timeout" in prompt


class TestGenerateImprovement:
    """Tests for generate_improvement function."""

    @pytest.mark.asyncio
    async def test_generates_improved_content(self):
        """Generate improved SKILL.md content."""
        response = """---
name: improved-skill
version: 0.2.0
---

# Improved Skill

Better instructions here.

## Steps

1. Do this first
2. Then do this
"""
        llm = MockLLM(response)

        result = await generate_improvement(
            llm,
            skill_content="---\nname: old-skill\n---\n# Old Skill\n\nOld instructions.",
            feedback="Instructions are unclear. Add more detail.",
        )

        assert "improved-skill" in result
        assert "Better instructions" in result

    @pytest.mark.asyncio
    async def test_strips_markdown_wrapper(self):
        """Strip markdown code block wrapper from response."""
        response = """```markdown
---
name: test
---
# Test
```"""
        llm = MockLLM(response)

        result = await generate_improvement(llm, "old content", "feedback")

        assert not result.startswith("```")
        assert "name: test" in result

    @pytest.mark.asyncio
    async def test_uses_moderate_temperature(self):
        """Use moderate temperature for improvements."""
        llm = MockLLM("---\nname: test\n---\n# Test")

        await generate_improvement(llm, "content", "feedback")

        assert llm.calls[0]["temperature"] == 0.5
