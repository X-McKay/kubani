"""Tests for PromoteWorkflow and promotion-related activities.

Phase 4 of skill-auto implementation:
- check_promotion_overlap activity (blocks if overlap)
- PromoteWorkflow child workflow
- Discord approval reaction handling
- Registry sync on promotion
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

# ============================================================================
# Tests for check_promotion_overlap activity
# ============================================================================


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    client = MagicMock()
    client.chat = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_check_promotion_overlap_blocks_on_overlap(mock_llm_client):
    """check_promotion_overlap should raise SkillOverlapError when overlap detected."""
    from kubani.workflows.skill_auto.activities import check_promotion_overlap
    from kubani.workflows.skill_auto.models import SkillOverlapError

    # Mock LLM response indicating overlap
    mock_llm_client.chat.return_value = {
        "content": """```json
{
    "has_overlap": true,
    "confidence": 0.88,
    "overlapping_skills": ["memory-troubleshooting"],
    "reasoning": "Both skills diagnose memory-related pod failures",
    "recommendation": "abort"
}
```""",
    }

    with pytest.raises(SkillOverlapError) as exc_info:
        await check_promotion_overlap(
            skill_name="oom-diagnostics",
            skill_description="Diagnose OOMKilled pod failures",
            production_skills=[
                {"name": "memory-troubleshooting", "description": "Diagnose memory issues"},
            ],
            llm_client=mock_llm_client,
            allow_overlap=False,
        )

    assert "memory-troubleshooting" in str(exc_info.value)
    assert exc_info.value.skill_name == "oom-diagnostics"
    assert "memory-troubleshooting" in exc_info.value.overlapping


@pytest.mark.asyncio
async def test_check_promotion_overlap_allows_with_flag(mock_llm_client):
    """check_promotion_overlap should warn but allow when allow_overlap=True."""
    from kubani.workflows.skill_auto.activities import check_promotion_overlap
    from kubani.workflows.skill_auto.models import OverlapResult

    mock_llm_client.chat.return_value = {
        "content": """```json
{
    "has_overlap": true,
    "confidence": 0.88,
    "overlapping_skills": ["memory-troubleshooting"],
    "reasoning": "Both skills diagnose memory-related pod failures",
    "recommendation": "abort"
}
```""",
    }

    result = await check_promotion_overlap(
        skill_name="oom-diagnostics",
        skill_description="Diagnose OOMKilled pod failures",
        production_skills=[
            {"name": "memory-troubleshooting", "description": "Diagnose memory issues"},
        ],
        llm_client=mock_llm_client,
        allow_overlap=True,  # Override
    )

    # Should return OverlapResult with warning instead of raising
    assert isinstance(result, OverlapResult)
    assert result.has_overlap is True
    assert result.overlapping_skills == ["memory-troubleshooting"]


@pytest.mark.asyncio
async def test_check_promotion_overlap_proceeds_when_no_overlap(mock_llm_client):
    """check_promotion_overlap should return success when no overlap."""
    from kubani.workflows.skill_auto.activities import check_promotion_overlap
    from kubani.workflows.skill_auto.models import OverlapResult

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
    }

    result = await check_promotion_overlap(
        skill_name="rbac-manager",
        skill_description="Manage RBAC policies",
        production_skills=[
            {"name": "memory-troubleshooting", "description": "Diagnose memory issues"},
        ],
        llm_client=mock_llm_client,
        allow_overlap=False,
    )

    assert isinstance(result, OverlapResult)
    assert result.has_overlap is False
    assert result.recommendation == "proceed"


@pytest.mark.asyncio
async def test_check_promotion_overlap_empty_production_skills(mock_llm_client):
    """check_promotion_overlap should proceed when no production skills exist."""
    from kubani.workflows.skill_auto.activities import check_promotion_overlap
    from kubani.workflows.skill_auto.models import OverlapResult

    result = await check_promotion_overlap(
        skill_name="new-skill",
        skill_description="A brand new skill",
        production_skills=[],
        llm_client=mock_llm_client,
        allow_overlap=False,
    )

    assert isinstance(result, OverlapResult)
    assert result.has_overlap is False


# ============================================================================
# Tests for promote_skill activity
# ============================================================================


@pytest.mark.asyncio
async def test_promote_skill_moves_to_production(tmp_path):
    """promote_skill should move skill from _development to production location."""
    from kubani.workflows.skill_auto.activities import promote_skill

    # Create development skill
    dev_dir = tmp_path / "skills" / "_development" / "test-skill"
    dev_dir.mkdir(parents=True)
    (dev_dir / "SKILL.md").write_text("---\nname: test-skill\n---\n# Test")
    (dev_dir / "test_cases.yaml").write_text("test_cases: []")
    (dev_dir / "metadata.json").write_text('{"status": "development"}')

    result = await promote_skill(
        skill_path=str(dev_dir),
        target_category="general",
        skills_root=str(tmp_path / "skills"),
    )

    # Verify skill moved
    prod_path = tmp_path / "skills" / "general" / "test-skill"
    assert prod_path.exists()
    assert (prod_path / "SKILL.md").exists()
    assert result["promoted_path"] == str(prod_path)
    assert result["success"] is True

    # Original dev path should be removed
    assert not dev_dir.exists()


@pytest.mark.asyncio
async def test_promote_skill_updates_metadata(tmp_path):
    """promote_skill should update metadata status to 'production'."""
    import json

    from kubani.workflows.skill_auto.activities import promote_skill

    # Create development skill with metadata
    dev_dir = tmp_path / "skills" / "_development" / "test-skill"
    dev_dir.mkdir(parents=True)
    (dev_dir / "SKILL.md").write_text("---\nname: test-skill\n---\n# Test")
    (dev_dir / "test_cases.yaml").write_text("test_cases: []")
    (dev_dir / "metadata.json").write_text(
        json.dumps({"status": "development", "created_by": "auto-mode"})
    )

    await promote_skill(
        skill_path=str(dev_dir),
        target_category="general",
        skills_root=str(tmp_path / "skills"),
    )

    # Check metadata updated
    prod_metadata = json.loads(
        (tmp_path / "skills" / "general" / "test-skill" / "metadata.json").read_text()
    )
    assert prod_metadata["status"] == "production"
    assert "promoted_at" in prod_metadata


# ============================================================================
# Tests for await_approval activity
# ============================================================================


@pytest.mark.asyncio
async def test_await_approval_returns_approved_on_checkmark():
    """await_approval should return approved=True when checkmark reaction received."""
    from kubani.workflows.skill_auto.activities import await_approval

    mock_discord = AsyncMock()
    mock_discord.add_reaction = AsyncMock()
    mock_discord.await_reaction = AsyncMock(
        return_value={
            "emoji": "\u2705",  # Checkmark
            "user_id": "user123",
            "user_name": "reviewer",
        }
    )

    result = await await_approval(
        channel_id="channel123",
        message_id="message123",
        discord_client=mock_discord,
        timeout_seconds=300,
    )

    assert result["approved"] is True
    assert result["reviewer"] == "reviewer"


@pytest.mark.asyncio
async def test_await_approval_returns_rejected_on_x():
    """await_approval should return approved=False when X reaction received."""
    from kubani.workflows.skill_auto.activities import await_approval

    mock_discord = AsyncMock()
    mock_discord.add_reaction = AsyncMock()
    mock_discord.await_reaction = AsyncMock(
        return_value={
            "emoji": "\u274c",  # X mark
            "user_id": "user123",
            "user_name": "reviewer",
        }
    )

    result = await await_approval(
        channel_id="channel123",
        message_id="message123",
        discord_client=mock_discord,
        timeout_seconds=300,
    )

    assert result["approved"] is False
    assert result["rejected"] is True


@pytest.mark.asyncio
async def test_await_approval_times_out():
    """await_approval should return timeout when no reaction received."""
    from kubani.workflows.skill_auto.activities import await_approval

    mock_discord = AsyncMock()
    mock_discord.add_reaction = AsyncMock()
    mock_discord.await_reaction = AsyncMock(return_value=None)  # Timeout

    result = await await_approval(
        channel_id="channel123",
        message_id="message123",
        discord_client=mock_discord,
        timeout_seconds=1,
    )

    assert result["approved"] is False
    assert result["timeout"] is True


@pytest.mark.asyncio
async def test_await_approval_adds_reaction_options():
    """await_approval should add checkmark and X reaction options to message."""
    from kubani.workflows.skill_auto.activities import await_approval

    mock_discord = AsyncMock()
    mock_discord.add_reaction = AsyncMock()
    mock_discord.await_reaction = AsyncMock(return_value={"emoji": "\u2705", "user_name": "rev"})

    await await_approval(
        channel_id="channel123",
        message_id="message123",
        discord_client=mock_discord,
        timeout_seconds=300,
    )

    # Should add both reactions as options
    calls = mock_discord.add_reaction.call_args_list
    emojis = [call.kwargs.get("emoji") or call[1].get("emoji") for call in calls]
    assert "\u2705" in emojis  # Checkmark
    assert "\u274c" in emojis  # X mark


# ============================================================================
# Tests for sync_registry activity
# ============================================================================


@pytest.mark.asyncio
async def test_sync_registry_registers_skill(tmp_path):
    """sync_registry should register skill in the registry."""
    from kubani.workflows.skill_auto.activities import sync_registry

    # Create skill
    skill_dir = tmp_path / "skills" / "general" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
version: "1.0.0"
category: general
triggers:
  - test_trigger
---
# Test Skill
""")

    mock_registry_client = AsyncMock()
    mock_registry_client.register_skill = AsyncMock(
        return_value={"registered": True, "skill_id": "skill-123"}
    )

    result = await sync_registry(
        skill_path=str(skill_dir),
        registry_client=mock_registry_client,
    )

    assert result["synced"] is True
    mock_registry_client.register_skill.assert_called_once()


@pytest.mark.asyncio
async def test_sync_registry_handles_failure():
    """sync_registry should return error on failure but not raise."""
    from kubani.workflows.skill_auto.activities import sync_registry

    mock_registry_client = AsyncMock()
    mock_registry_client.register_skill = AsyncMock(side_effect=Exception("Network error"))

    result = await sync_registry(
        skill_path="/nonexistent/path",
        registry_client=mock_registry_client,
    )

    assert result["synced"] is False
    assert "error" in result


# ============================================================================
# Tests for send_promotion_request activity
# ============================================================================


@pytest.mark.asyncio
async def test_send_promotion_request_formats_message():
    """send_promotion_request should send a formatted Discord message with reactions."""
    from kubani.workflows.skill_auto.activities import send_promotion_request
    from kubani.workflows.skill_auto.models import EvalMetrics

    mock_discord = AsyncMock()
    mock_discord.send_embed = AsyncMock(return_value={"message_id": "msg123"})

    metrics = EvalMetrics(
        accuracy=0.88,
        latency_ms=1200,
        tests_passed=8,
        tests_total=9,
        critic_confidence=0.85,
    )

    result = await send_promotion_request(
        skill_name="test-skill",
        skill_path="kubani/skills/_development/test-skill",
        metrics=metrics,
        iterations=3,
        channel="skill-notifications",
        discord_client=mock_discord,
    )

    assert result["sent"] is True
    assert result["message_id"] == "msg123"

    # Verify embed contains promotion info
    call_args = mock_discord.send_embed.call_args
    embed = call_args.kwargs.get("embed") or call_args[1].get("embed")
    assert "test-skill" in embed["title"]
    assert "88" in str(embed)  # Accuracy percentage


# ============================================================================
# Tests for PromoteWorkflow
# ============================================================================


@pytest.mark.asyncio
async def test_promote_workflow_model_exists():
    """PromoteWorkflowInput and PromoteWorkflowResult models should exist."""
    from kubani.workflows.skill_auto.models import PromoteWorkflowInput, PromoteWorkflowResult

    input = PromoteWorkflowInput(
        skill_path="kubani/skills/_development/test-skill",
        skill_name="test-skill",
        skill_description="A test skill",
        metrics=None,
        iterations=3,
        allow_overlap=False,
        notify_channel="skill-notifications",
    )

    assert input.skill_name == "test-skill"

    result = PromoteWorkflowResult(
        promoted=True,
        promoted_path="kubani/skills/general/test-skill",
        approved_by="reviewer",
    )

    assert result.promoted is True


def test_promote_workflow_is_decorated():
    """PromoteWorkflow should be a Temporal workflow."""

    from kubani.workflows.skill_auto.promote import PromoteWorkflow

    # Check workflow decoration
    assert hasattr(PromoteWorkflow, "__temporal_workflow_definition")


def test_promote_workflow_has_run_method():
    """PromoteWorkflow should have a run method."""
    from kubani.workflows.skill_auto.promote import PromoteWorkflow

    assert hasattr(PromoteWorkflow, "run")
    assert callable(PromoteWorkflow.run)
