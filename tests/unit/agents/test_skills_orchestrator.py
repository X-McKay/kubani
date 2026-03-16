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
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_load:
            mock_load.return_value = []

            class TestOrchestrator(SkillsOrchestrator):
                AGENT_DIR = Path(__file__).parent

                async def on_skill_complete(self, skill_name, result):
                    pass

            TestOrchestrator()
            mock_load.assert_called()

    def test_orchestrator_generates_skills_prompt(self):
        """Orchestrator should generate skills catalog for prompt."""
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_load:
            mock_load.return_value = [
                {
                    "name": "test-skill",
                    "description": "A test skill",
                    "path": "/test",
                    "metadata": {"domain": "news", "category": "collection"},
                }
            ]

            class TestOrchestrator(SkillsOrchestrator):
                AGENT_DIR = Path(__file__).parent
                SKILLS_DOMAIN = "news"
                SKILLS_CATEGORY = "collection"

                async def on_skill_complete(self, skill_name, result):
                    pass

            orchestrator = TestOrchestrator()
            prompt = orchestrator._generate_skills_prompt()

            assert "test-skill" in prompt
            assert "A test skill" in prompt

    def test_orchestrator_filters_by_domain_category(self):
        """Orchestrator should filter skills by domain and category."""
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_load:
            mock_load.return_value = [
                {
                    "name": "match-skill",
                    "description": "Matching",
                    "path": "/a",
                    "metadata": {"domain": "news", "category": "collection"},
                },
                {
                    "name": "wrong-domain",
                    "description": "Wrong domain",
                    "path": "/b",
                    "metadata": {"domain": "k8s", "category": "collection"},
                },
                {
                    "name": "wrong-category",
                    "description": "Wrong category",
                    "path": "/c",
                    "metadata": {"domain": "news", "category": "analysis"},
                },
            ]

            class TestOrchestrator(SkillsOrchestrator):
                AGENT_DIR = Path(__file__).parent
                SKILLS_DOMAIN = "news"
                SKILLS_CATEGORY = "collection"

                async def on_skill_complete(self, skill_name, result):
                    pass

            orchestrator = TestOrchestrator()
            assert len(orchestrator.skills) == 1
            assert orchestrator.skills[0]["name"] == "match-skill"
