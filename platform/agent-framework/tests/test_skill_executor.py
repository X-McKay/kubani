"""Tests for SkillExecutor."""

import pytest
from agent_framework.skill_executor import SkillExecutor


class TestSkillExecutor:
    """Tests for SkillExecutor class."""

    def test_executor_creation(self, temp_skills_dir):
        """Test executor can be created."""
        executor = SkillExecutor(skills_dir=temp_skills_dir)
        assert executor.skills_dir == temp_skills_dir

    @pytest.mark.asyncio
    async def test_load_skill(self, temp_skills_dir):
        """Test skill loading."""
        executor = SkillExecutor(skills_dir=temp_skills_dir)

        skill = await executor.load_skill("test/example-skill")

        assert skill["name"] == "test/example-skill"
        assert "metadata" in skill
        assert skill["metadata"]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_execute_skill(self, temp_skills_dir):
        """Test skill execution."""
        executor = SkillExecutor(skills_dir=temp_skills_dir)

        trace = await executor.execute(
            "test/example-skill",
            context={"key": "value"},
        )

        assert trace.name == "test/example-skill"
        assert trace.input == {"key": "value"}
        assert trace.trace_id is not None
        assert len(trace.spans) > 0

    @pytest.mark.asyncio
    async def test_skill_not_found(self, temp_skills_dir):
        """Test error when skill not found."""
        executor = SkillExecutor(skills_dir=temp_skills_dir)

        with pytest.raises(ValueError, match="Skill not found"):
            await executor.load_skill("nonexistent-skill")
