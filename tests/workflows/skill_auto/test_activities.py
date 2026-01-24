"""Tests for skill auto workflow activities."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    client = MagicMock()
    client.chat = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_detect_overlap_finds_similar_skill(mock_llm_client):
    """detect_skill_overlap should identify overlapping skills."""
    from kubani.workflows.skill_auto.activities import detect_skill_overlap
    from kubani.workflows.skill_auto.models import OverlapResult

    # Mock LLM response indicating overlap
    mock_llm_client.chat.return_value = {
        "content": """```json
{
    "has_overlap": true,
    "confidence": 0.82,
    "overlapping_skills": ["memory-troubleshooting"],
    "reasoning": "Both skills diagnose memory-related pod failures",
    "recommendation": "merge"
}
```""",
        "tokens": {"prompt": 100, "completion": 50, "total": 150},
    }

    result = await detect_skill_overlap(
        description="A skill that helps diagnose OOMKilled pods",
        existing_skills=[
            {"name": "memory-troubleshooting", "description": "Diagnose memory issues in pods"},
            {"name": "cpu-throttling", "description": "Diagnose CPU throttling issues"},
        ],
        llm_client=mock_llm_client,
    )

    assert isinstance(result, OverlapResult)
    assert result.has_overlap is True
    assert result.confidence > 0.8
    assert "memory-troubleshooting" in result.overlapping_skills


@pytest.mark.asyncio
async def test_detect_overlap_no_overlap(mock_llm_client):
    """detect_skill_overlap should return no overlap when skills are distinct."""
    from kubani.workflows.skill_auto.activities import detect_skill_overlap

    mock_llm_client.chat.return_value = {
        "content": """```json
{
    "has_overlap": false,
    "confidence": 0.95,
    "overlapping_skills": [],
    "reasoning": "This skill addresses a unique use case",
    "recommendation": "proceed"
}
```""",
        "tokens": {"prompt": 100, "completion": 50, "total": 150},
    }

    result = await detect_skill_overlap(
        description="A skill that manages Kubernetes RBAC policies",
        existing_skills=[
            {"name": "memory-troubleshooting", "description": "Diagnose memory issues"},
        ],
        llm_client=mock_llm_client,
    )

    assert result.has_overlap is False
    assert result.recommendation == "proceed"
