"""Tests for skill policy filtering."""

import pytest

from kubani.framework.skills.policies import SKILL_POLICIES, filter_skills


def _skill(name: str) -> dict:
    """Create a minimal skill dict for testing."""
    return {"name": name, "description": f"Test: {name}"}


@pytest.fixture
def all_skills():
    """A representative set of skills spanning all domains."""
    return [
        _skill("k8s/diagnostic/check-pods"),
        _skill("k8s/remediation/restart-pod"),
        _skill("k8s/collection/get-cluster-health"),
        _skill("news/analysis/sentiment"),
        _skill("news/collection/rss-feed"),
        _skill("general/missions/run-check"),
        _skill("general/notifications/send-alert"),
        _skill("general/analytics/detect-anomaly"),
        _skill("general/memory/store-context"),
        _skill("_development/test-skill"),
    ]


class TestFilterSkills:
    def test_nexus_allows_all_except_dev(self, all_skills):
        result = filter_skills(all_skills, "nexus")
        names = {s["name"] for s in result}
        assert len(result) == 9  # all except _development
        assert "_development/test-skill" not in names

    def test_nexus_proactive_restricts_to_allowed_domains(self, all_skills):
        result = filter_skills(all_skills, "nexus-proactive")
        names = {s["name"] for s in result}

        # k8s/* allowed
        assert "k8s/diagnostic/check-pods" in names
        assert "k8s/remediation/restart-pod" in names
        assert "k8s/collection/get-cluster-health" in names
        # general/missions/*, general/notifications/*, general/analytics/* allowed
        assert "general/missions/run-check" in names
        assert "general/notifications/send-alert" in names
        assert "general/analytics/detect-anomaly" in names
        # news/* NOT allowed
        assert "news/analysis/sentiment" not in names
        assert "news/collection/rss-feed" not in names
        # general/memory/* NOT allowed
        assert "general/memory/store-context" not in names
        # _development/* denied
        assert "_development/test-skill" not in names

    def test_nexus_computer_allows_all_except_dev(self, all_skills):
        result = filter_skills(all_skills, "nexus-computer")
        assert len(result) == 9

    def test_unknown_policy_falls_back_to_nexus(self, all_skills):
        result = filter_skills(all_skills, "nonexistent-policy")
        assert len(result) == 9  # same as nexus

    def test_denied_takes_priority_over_allowed(self):
        """A skill matching both allowed and denied patterns is excluded."""
        skills = [_skill("_development/k8s/test-thing")]
        result = filter_skills(skills, "nexus")
        assert len(result) == 0

    def test_empty_input_returns_empty(self):
        result = filter_skills([], "nexus")
        assert result == []

    def test_all_expected_policies_exist(self):
        assert "nexus" in SKILL_POLICIES
        assert "nexus-proactive" in SKILL_POLICIES
        assert "nexus-computer" in SKILL_POLICIES

    def test_each_policy_has_allowed_and_denied(self):
        for name, rules in SKILL_POLICIES.items():
            assert "allowed" in rules, f"Policy '{name}' missing 'allowed'"
            assert "denied" in rules, f"Policy '{name}' missing 'denied'"
