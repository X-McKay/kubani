"""Tests for detect_skill_overlap capability."""

import pytest

from kubani.framework.testing.mocks import MockLLM
from kubani.workflows.skill_auto.capabilities.detect_skill_overlap import (
    detect_skill_overlap,
)
from kubani.workflows.skill_auto.models import OverlapResult

# =============================================================================
# Test Data
# =============================================================================

NO_OVERLAP_RESPONSE = """{
    "has_overlap": false,
    "confidence": 0.95,
    "overlapping_skills": [],
    "reasoning": "The new skill addresses a unique problem domain",
    "recommendation": "proceed"
}"""

OVERLAP_DETECTED_RESPONSE = """{
    "has_overlap": true,
    "confidence": 0.85,
    "overlapping_skills": ["existing-skill", "similar-skill"],
    "reasoning": "The new skill overlaps significantly with existing-skill",
    "recommendation": "merge"
}"""

ABORT_RESPONSE = """{
    "has_overlap": true,
    "confidence": 0.95,
    "overlapping_skills": ["duplicate-skill"],
    "reasoning": "This skill is essentially a duplicate of duplicate-skill",
    "recommendation": "abort"
}"""

EXISTING_SKILLS = [
    {"name": "existing-skill", "description": "An existing skill"},
    {"name": "another-skill", "description": "Another existing skill"},
]


# =============================================================================
# Tests
# =============================================================================


class TestDetectSkillOverlap:
    """Tests for detect_skill_overlap function."""

    @pytest.mark.asyncio
    async def test_returns_no_overlap_for_empty_skills(self):
        """Returns no overlap when no existing skills to compare."""
        client = MockLLM(responses=["{}"])  # Won't be called
        result = await detect_skill_overlap(client, "new skill description", [])

        assert isinstance(result, OverlapResult)
        assert result.has_overlap is False
        assert result.confidence == 1.0
        assert result.recommendation == "proceed"
        assert result.overlapping_skills == []
        assert "No existing skills" in result.reasoning

        # LLM should not be called for empty skills
        assert client.call_count == 0

    @pytest.mark.asyncio
    async def test_detects_no_overlap(self):
        """Correctly identifies when no overlap exists."""
        client = MockLLM(responses=[NO_OVERLAP_RESPONSE])
        result = await detect_skill_overlap(
            client, "A completely new unique skill", EXISTING_SKILLS
        )

        assert isinstance(result, OverlapResult)
        assert result.has_overlap is False
        assert result.confidence == 0.95
        assert result.recommendation == "proceed"
        assert result.overlapping_skills == []

    @pytest.mark.asyncio
    async def test_detects_overlap(self):
        """Correctly identifies overlapping skills."""
        client = MockLLM(responses=[OVERLAP_DETECTED_RESPONSE])
        result = await detect_skill_overlap(
            client, "A skill similar to existing ones", EXISTING_SKILLS
        )

        assert result.has_overlap is True
        assert result.confidence == 0.85
        assert result.recommendation == "merge"
        assert "existing-skill" in result.overlapping_skills
        assert "similar-skill" in result.overlapping_skills

    @pytest.mark.asyncio
    async def test_handles_abort_recommendation(self):
        """Handles abort recommendation for duplicates."""
        client = MockLLM(responses=[ABORT_RESPONSE])
        result = await detect_skill_overlap(client, "A duplicate skill", EXISTING_SKILLS)

        assert result.has_overlap is True
        assert result.recommendation == "abort"
        assert "duplicate-skill" in result.overlapping_skills

    @pytest.mark.asyncio
    async def test_includes_skill_details_in_prompt(self):
        """Existing skill details are included in the prompt."""
        client = MockLLM(responses=[NO_OVERLAP_RESPONSE])
        await detect_skill_overlap(client, "new skill", EXISTING_SKILLS)

        assert client.call_count == 1
        user_message = client.calls[0]["messages"][1]["content"]
        assert "existing-skill" in user_message
        assert "An existing skill" in user_message
        assert "another-skill" in user_message

    @pytest.mark.asyncio
    async def test_includes_new_skill_description_in_prompt(self):
        """New skill description is included in the prompt."""
        client = MockLLM(responses=[NO_OVERLAP_RESPONSE])
        await detect_skill_overlap(client, "My special new skill", EXISTING_SKILLS)

        user_message = client.calls[0]["messages"][1]["content"]
        assert "My special new skill" in user_message
        assert "NEW SKILL DESCRIPTION" in user_message

    @pytest.mark.asyncio
    async def test_extracts_json_from_code_block(self):
        """Extracts JSON from markdown code block."""
        response_in_block = f"```json\n{NO_OVERLAP_RESPONSE}\n```"
        client = MockLLM(responses=[response_in_block])
        result = await detect_skill_overlap(client, "new skill", EXISTING_SKILLS)

        assert isinstance(result, OverlapResult)
        assert result.has_overlap is False

    @pytest.mark.asyncio
    async def test_strips_thinking_tags(self):
        """Strips <think> tags from response."""
        response_with_thinking = f"<think>Analyzing...</think>{NO_OVERLAP_RESPONSE}"
        client = MockLLM(responses=[response_with_thinking])
        result = await detect_skill_overlap(client, "new skill", EXISTING_SKILLS)

        assert isinstance(result, OverlapResult)
        assert result.has_overlap is False

    @pytest.mark.asyncio
    async def test_raises_on_invalid_json(self):
        """Raises ValueError when LLM returns invalid JSON."""
        client = MockLLM(responses=["not valid json at all"])
        with pytest.raises(ValueError, match="Invalid JSON"):
            await detect_skill_overlap(client, "new skill", EXISTING_SKILLS)

    @pytest.mark.asyncio
    async def test_handles_missing_fields_with_defaults(self):
        """Handles missing optional fields with sensible defaults."""
        minimal_response = '{"has_overlap": true}'
        client = MockLLM(responses=[minimal_response])
        result = await detect_skill_overlap(client, "new skill", EXISTING_SKILLS)

        assert result.has_overlap is True
        assert result.confidence == 0.0  # Default
        assert result.overlapping_skills == []  # Default
        assert result.reasoning == ""  # Default
        assert result.recommendation == "proceed"  # Default

    @pytest.mark.asyncio
    async def test_normalizes_invalid_recommendation(self):
        """Normalizes invalid recommendation to 'proceed'."""
        invalid_recommendation = """{
            "has_overlap": false,
            "confidence": 0.5,
            "overlapping_skills": [],
            "reasoning": "Test",
            "recommendation": "invalid_value"
        }"""
        client = MockLLM(responses=[invalid_recommendation])
        result = await detect_skill_overlap(client, "new skill", EXISTING_SKILLS)

        assert result.recommendation == "proceed"  # Normalized

    @pytest.mark.asyncio
    async def test_handles_skill_without_description(self):
        """Handles existing skills that lack a description."""
        skills_without_desc = [{"name": "no-desc-skill"}]
        client = MockLLM(responses=[NO_OVERLAP_RESPONSE])
        await detect_skill_overlap(client, "new skill", skills_without_desc)

        user_message = client.calls[0]["messages"][1]["content"]
        assert "no-desc-skill" in user_message
        assert "No description" in user_message

    @pytest.mark.asyncio
    async def test_uses_correct_system_prompt(self):
        """Verifies system prompt is for skill analysis."""
        client = MockLLM(responses=[NO_OVERLAP_RESPONSE])
        await detect_skill_overlap(client, "new skill", EXISTING_SKILLS)

        messages = client.calls[0]["messages"]
        assert messages[0]["role"] == "system"
        assert "skill analyst" in messages[0]["content"]
