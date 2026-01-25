"""Tests for llm_service.py - LLM interactions with mock responses.

These tests mock the LLM protocol to return canned responses,
testing the prompt construction and response parsing logic.
"""

import pytest

from kubani.workflows.skill_auto.llm_service import (
    OverlapAnalysis,
    SkillSpec,
    clean_markdown_output,
    clean_yaml_output,
    detect_overlap,
    generate_harder_tests,
    generate_improvement,
    generate_test_cases,
    infer_skill_structure,
)


class MockLLM:
    """Mock LLM service for testing.

    Implements the same interface as LLMService to work with the wrapper functions.
    """

    def __init__(self, responses: list[str] | str):
        """
        Initialize with canned responses.

        Args:
            responses: Single response string or list of responses to cycle through
        """
        if isinstance(responses, str):
            responses = [responses]
        self._responses = list(responses)
        self._response_iter = iter(self._responses)
        self.calls: list[dict] = []

    def _get_next_response(self) -> str:
        """Get the next response, cycling back to start if needed."""
        try:
            return next(self._response_iter)
        except StopIteration:
            self._response_iter = iter(self._responses)
            return next(self._response_iter)

    async def infer_skill(self, description: str, context: str | None = None) -> SkillSpec:
        """Mock infer_skill that returns parsed response."""
        import json

        response = self._get_next_response()
        self.calls.append(
            {
                "method": "infer_skill",
                "description": description,
                "context": context,
            }
        )

        # Parse the response as JSON
        if "```json" in response:
            json_start = response.find("```json") + 7
            json_end = response.find("```", json_start)
            response = response[json_start:json_end].strip()
        elif "```" in response:
            json_start = response.find("```") + 3
            json_end = response.find("```", json_start)
            response = response[json_start:json_end].strip()

        data = json.loads(response)
        # Fill in required fields with defaults if missing
        data.setdefault("inputs", {})
        data.setdefault("outputs", {})
        data.setdefault("steps", [])
        data.setdefault("error_handling", [])
        data.setdefault("examples", [])
        return SkillSpec.model_validate(data)

    async def detect_overlap(self, description: str, existing_skills: list) -> OverlapAnalysis:
        """Mock detect_overlap that returns parsed response."""
        import json

        if not existing_skills:
            self.calls.append(
                {
                    "method": "detect_overlap",
                    "description": description,
                    "existing": existing_skills,
                    "skipped": True,
                }
            )
            return OverlapAnalysis(
                has_overlap=False,
                confidence=1.0,
                overlapping_skills=[],
                reasoning="No existing skills to compare against",
                recommendation="proceed",
            )

        response = self._get_next_response()
        self.calls.append(
            {
                "method": "detect_overlap",
                "description": description,
                "existing": existing_skills,
            }
        )

        data = json.loads(response)
        return OverlapAnalysis.model_validate(data)

    async def generate_test_cases(self, spec: dict, seed_tests: str | None = None) -> str:
        """Mock generate_test_cases that cleans the response."""
        response = self._get_next_response()
        self.calls.append(
            {
                "method": "generate_test_cases",
                "spec": spec,
                "seed_tests": seed_tests,
            }
        )
        # Apply the same cleaning as the real implementation
        return clean_yaml_output(response)

    async def generate_harder_tests(
        self,
        skill_name: str,
        current_test_cases: str,
        accuracy: float,
        tests_passed: int,
        tests_total: int,
        failing_tests: list,
        count: int = 2,
    ) -> str:
        """Mock generate_harder_tests."""
        response = self._get_next_response()
        self.calls.append(
            {
                "method": "generate_harder_tests",
                "skill_name": skill_name,
                "current_test_cases": current_test_cases,
                "accuracy": accuracy,
                "tests_passed": tests_passed,
                "tests_total": tests_total,
                "failing_tests": failing_tests,
                "count": count,
            }
        )
        return response

    async def generate_improvement(self, skill_content: str, feedback: str) -> str:
        """Mock generate_improvement that cleans the response."""
        response = self._get_next_response()
        self.calls.append(
            {
                "method": "generate_improvement",
                "skill_content": skill_content,
                "feedback": feedback,
            }
        )
        # Apply the same cleaning as the real implementation
        return clean_markdown_output(response)

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
            "inputs": {"pod_name": {"type": "string", "description": "Name of the pod", "required": true}},
            "outputs": {"diagnosis": {"type": "string", "description": "Diagnosis result"}},
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
    async def test_includes_context_in_call(self):
        """Include additional context in the call."""
        llm = MockLLM('{"name": "test", "description": "test"}')

        await infer_skill_structure(
            llm,
            "Test skill",
            context="This is for Kubernetes environments",
        )

        # Check that context was passed to the method
        assert len(llm.calls) == 1
        assert llm.calls[0]["method"] == "infer_skill"
        assert llm.calls[0]["context"] == "This is for Kubernetes environments"

    @pytest.mark.asyncio
    async def test_passes_description(self):
        """Verify description is passed to infer_skill."""
        llm = MockLLM('{"name": "test", "description": "test"}')

        await infer_skill_structure(llm, "Diagnose memory issues")

        assert llm.calls[0]["description"] == "Diagnose memory issues"


class TestDetectOverlap:
    """Tests for detect_overlap function."""

    @pytest.mark.asyncio
    async def test_no_existing_skills(self):
        """Return no overlap when no existing skills."""
        llm = MockLLM("")  # Won't be used for response

        result = await detect_overlap(llm, "New skill", [])

        assert result.has_overlap is False
        assert result.confidence == 1.0
        # Method was called but skipped
        assert len(llm.calls) == 1
        assert llm.calls[0].get("skipped") is True

    @pytest.mark.asyncio
    async def test_overlap_detected(self):
        """Detect overlap with existing skills."""
        response = """{
            "has_overlap": true,
            "confidence": 0.85,
            "overlapping_skills": ["existing-skill"],
            "reasoning": "Both handle pod diagnostics",
            "recommendation": "merge"
        }"""
        llm = MockLLM(response)

        result = await detect_overlap(
            llm, "Diagnose pod issues", [{"name": "existing-skill", "description": "Pod helper"}]
        )

        assert result.has_overlap is True
        assert result.confidence == 0.85
        assert "existing-skill" in result.overlapping_skills
        assert result.recommendation == "merge"

    @pytest.mark.asyncio
    async def test_no_overlap_detected(self):
        """No overlap when skills are different."""
        response = """{
            "has_overlap": false,
            "confidence": 0.9,
            "overlapping_skills": [],
            "reasoning": "Skills address different domains",
            "recommendation": "proceed"
        }"""
        llm = MockLLM(response)

        result = await detect_overlap(
            llm, "Generate reports", [{"name": "other-skill", "description": "Something else"}]
        )

        assert result.has_overlap is False
        assert result.recommendation == "proceed"

    @pytest.mark.asyncio
    async def test_passes_existing_skills(self):
        """Verify existing skills are passed to detect_overlap."""
        response = """{
            "has_overlap": false,
            "confidence": 0.9,
            "overlapping_skills": [],
            "reasoning": "No overlap",
            "recommendation": "proceed"
        }"""
        llm = MockLLM(response)
        existing = [
            {"name": "skill-a", "description": "A"},
            {"name": "skill-b", "description": "B"},
        ]

        await detect_overlap(llm, "New skill", existing)

        assert llm.calls[0]["existing"] == existing


class TestGenerateTestCases:
    """Tests for generate_test_cases function."""

    @pytest.mark.asyncio
    async def test_generates_yaml(self):
        """Generate valid YAML test cases."""
        response = """test_cases:
  - name: test_basic
    description: Basic test
    inputs:
      param: value
    expected:
      result: success"""
        llm = MockLLM(response)

        result = await generate_test_cases(llm, {"name": "test-skill"})

        assert "test_cases:" in result
        assert "test_basic" in result

    @pytest.mark.asyncio
    async def test_cleans_yaml_wrapper(self):
        """Strip YAML code block wrapper."""
        response = """```yaml
test_cases:
  - name: test
```"""
        llm = MockLLM(response)

        result = await generate_test_cases(llm, {"name": "test-skill"})

        assert not result.startswith("```")
        assert "test_cases:" in result

    @pytest.mark.asyncio
    async def test_includes_seed_tests(self):
        """Include seed tests in call."""
        llm = MockLLM("test_cases: []")
        seed = "test_cases:\n  - name: seed_test"

        await generate_test_cases(llm, {"name": "test"}, seed_tests=seed)

        assert llm.calls[0]["seed_tests"] == seed


class TestGenerateHarderTests:
    """Tests for generate_harder_tests function."""

    @pytest.mark.asyncio
    async def test_generates_harder_tests(self):
        """Generate harder test cases."""
        response = """test_cases:
  - name: harder_test
    description: Edge case"""
        llm = MockLLM(response)

        result = await generate_harder_tests(
            llm,
            "test-skill",
            "existing tests",
            0.6,
            3,
            5,
            [{"name": "failing", "reason": "timeout"}],
        )

        assert "harder_test" in result

    @pytest.mark.asyncio
    async def test_includes_failure_info(self):
        """Include failing test information in call."""
        llm = MockLLM("test_cases: []")
        failing = [
            {"name": "test_a", "reason": "timeout"},
            {"name": "test_b", "reason": "wrong output"},
        ]

        await generate_harder_tests(llm, "skill", "tests", 0.5, 2, 4, failing, count=3)

        call = llm.calls[0]
        assert call["failing_tests"] == failing
        assert call["accuracy"] == 0.5
        assert call["count"] == 3


class TestGenerateImprovement:
    """Tests for generate_improvement function."""

    @pytest.mark.asyncio
    async def test_generates_improved_content(self):
        """Generate improved skill content."""
        response = """---
name: improved-skill
---

# Improved Skill

Better content here."""
        llm = MockLLM(response)

        result = await generate_improvement(llm, "old content", "improve accuracy")

        assert "improved-skill" in result
        assert "Better content" in result

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
        assert "---" in result

    @pytest.mark.asyncio
    async def test_strips_think_tags(self):
        """Strip <think> tags from response."""
        response = """<think>
Let me think about this...
</think>

---
name: test
---
# Test Skill"""
        llm = MockLLM(response)

        result = await generate_improvement(llm, "old content", "feedback")

        assert "<think>" not in result
        assert "</think>" not in result
        assert "---" in result

    @pytest.mark.asyncio
    async def test_passes_content_and_feedback(self):
        """Verify content and feedback are passed to method."""
        llm = MockLLM("---\nname: test\n---\n# Test")

        await generate_improvement(llm, "my content", "my feedback")

        call = llm.calls[0]
        assert call["skill_content"] == "my content"
        assert call["feedback"] == "my feedback"


class TestCleanYamlOutput:
    """Tests for clean_yaml_output helper."""

    def test_strips_yaml_code_block(self):
        """Strip ```yaml wrapper."""
        content = "```yaml\ntest: value\n```"
        result = clean_yaml_output(content)
        assert result == "test: value"

    def test_strips_generic_code_block(self):
        """Strip ``` wrapper."""
        content = "```\ntest: value\n```"
        result = clean_yaml_output(content)
        assert result == "test: value"

    def test_strips_think_tags(self):
        """Strip <think> tags."""
        content = "<think>reasoning</think>\ntest: value"
        result = clean_yaml_output(content)
        assert "<think>" not in result
        assert result == "test: value"

    def test_preserves_clean_yaml(self):
        """Preserve YAML without wrappers."""
        content = "test: value\nother: data"
        result = clean_yaml_output(content)
        assert result == content


class TestCleanMarkdownOutput:
    """Tests for clean_markdown_output helper."""

    def test_strips_markdown_code_block(self):
        """Strip ```markdown wrapper."""
        content = "```markdown\n# Title\n```"
        result = clean_markdown_output(content)
        assert result == "# Title"

    def test_strips_think_tags(self):
        """Strip <think> tags."""
        content = "<think>reasoning</think>\n# Title"
        result = clean_markdown_output(content)
        assert "<think>" not in result
        assert result == "# Title"

    def test_handles_empty_think_tags(self):
        """Handle empty <think> tags."""
        content = "<think>\n\n</think>\n\n---\nname: test"
        result = clean_markdown_output(content)
        assert result.startswith("---")
