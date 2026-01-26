# tests/workflows/agent_auto/services/test_drafting_service.py
"""Integration tests for the DraftingService."""

import pytest

from kubani.workflows.agent_auto.services.drafting import DraftingService

from .mocks import MockFileSystem, MockLLMClient, MockSkillRepository


@pytest.mark.asyncio
async def test_draft_agent_identifies_missing_skills():
    """Tests that the drafting service correctly identifies skills that need to be created."""
    # Arrange
    mock_llm = MockLLMClient(response_to_return="...")  # Not used if using pure function
    mock_fs = MockFileSystem()
    # Mock repo has 'skill/a' but not 'skill/b'
    mock_repo = MockSkillRepository(existing_skills=[{"name": "skill/a"}])

    service = DraftingService(llm_client=mock_llm, fs=mock_fs, skill_repo=mock_repo)

    # Act
    # The description should trigger a requirement for both skills via the pure analysis function
    result = await service.draft_agent("An agent that needs skill/a and skill/b")

    # Assert
    assert result["missing_skills"] == ["skill/b"]
    assert "prompt.md" in list(result["files_to_create"].keys())[0]


@pytest.mark.asyncio
async def test_draft_agent_no_missing_skills_when_all_exist():
    """Tests that no missing skills are reported when all required skills exist."""
    # Arrange
    mock_llm = MockLLMClient()
    mock_fs = MockFileSystem()
    mock_repo = MockSkillRepository(
        existing_skills=[
            {"name": "skill/a"},
            {"name": "skill/b"},
        ]
    )

    service = DraftingService(llm_client=mock_llm, fs=mock_fs, skill_repo=mock_repo)

    # Act
    result = await service.draft_agent("An agent that needs skill/a and skill/b")

    # Assert
    assert result["missing_skills"] == []


@pytest.mark.asyncio
async def test_draft_agent_generates_files_content():
    """Tests that the drafting service generates proper file content."""
    # Arrange
    mock_llm = MockLLMClient()
    mock_fs = MockFileSystem()
    mock_repo = MockSkillRepository()

    service = DraftingService(llm_client=mock_llm, fs=mock_fs, skill_repo=mock_repo)

    # Act
    result = await service.draft_agent("A monitoring agent for kubernetes pods")

    # Assert
    files = result["files_to_create"]
    assert len(files) == 2

    # Check that prompt.md was generated
    prompt_files = [f for f in files.keys() if f.endswith("prompt.md")]
    assert len(prompt_files) == 1
    prompt_content = files[prompt_files[0]]
    assert "monitoring" in prompt_content.lower() or "kubernetes" in prompt_content.lower()

    # Check that config.yaml was generated
    config_files = [f for f in files.keys() if f.endswith("config.yaml")]
    assert len(config_files) == 1
    config_content = files[config_files[0]]
    assert "name:" in config_content
