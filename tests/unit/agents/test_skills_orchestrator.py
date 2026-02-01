"""Tests for SkillsOrchestrator base class."""

from pathlib import Path
from unittest.mock import patch

from kubani.agents._base.skills_orchestrator import SkillsOrchestrator


class TestSkillsOrchestrator:
    """Test the SkillsOrchestrator base class."""

    def test_orchestrator_inherits_kubani_agent(self):
        """SkillsOrchestrator should inherit from KubaniAgent."""
        from kubani.agents._base import KubaniAgent
        assert issubclass(SkillsOrchestrator, KubaniAgent)

    def test_orchestrator_discovers_skills(self):
        """Orchestrator should discover skills on init."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock_discover:
            mock_discover.return_value = []

            class TestOrchestrator(SkillsOrchestrator):
                AGENT_DIR = Path(__file__).parent
                async def on_skill_complete(self, skill_name, result):
                    pass

            TestOrchestrator()  # Instantiate to trigger skill discovery
            mock_discover.assert_called()

    def test_orchestrator_generates_skills_prompt(self):
        """Orchestrator should generate skills catalog for prompt."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock_discover:
            from kubani.framework.skills import KubaniSkill
            mock_discover.return_value = [
                KubaniSkill(
                    name="test-skill",
                    description="A test skill",
                    skill_path=Path("/test"),
                    license="MIT",
                    compatibility="None",
                    domain="news",
                    category="collection",
                )
            ]

            class TestOrchestrator(SkillsOrchestrator):
                AGENT_DIR = Path(__file__).parent
                async def on_skill_complete(self, skill_name, result):
                    pass

            orchestrator = TestOrchestrator()
            prompt = orchestrator._generate_skills_prompt()

            assert "test-skill" in prompt
            assert "A test skill" in prompt
