"""Tests for Reflection agent models."""

from datetime import datetime

from kubani.agents.reflection.models import (
    InsightType,
    ReflectionInsight,
    ReflectionResult,
)


class TestInsightType:
    """Tests for InsightType enum."""

    def test_all_types_exist(self):
        """Test that all expected insight types exist."""
        assert InsightType.PATTERN.value == "pattern"
        assert InsightType.ANTI_PATTERN.value == "anti_pattern"
        assert InsightType.BEST_PRACTICE.value == "best_practice"
        assert InsightType.KNOWLEDGE.value == "knowledge"
        assert InsightType.SKILL_OPPORTUNITY.value == "skill_opportunity"


class TestReflectionInsight:
    """Tests for ReflectionInsight dataclass."""

    def test_default_insight(self):
        """Test default insight values."""
        insight = ReflectionInsight()
        assert insight.title == ""
        assert insight.insight_type == InsightType.PATTERN
        assert insight.description == ""
        assert insight.evidence == []
        assert insight.confidence == 0.0
        assert insight.applicable_domains == []
        assert insight.applicable_agents == []
        assert isinstance(insight.timestamp, datetime)

    def test_custom_insight(self):
        """Test custom insight values."""
        insight = ReflectionInsight(
            title="OOM Recovery Pattern",
            insight_type=InsightType.BEST_PRACTICE,
            description="When pods crash with OOM, increase memory limits",
            evidence=["exec-1", "exec-2"],
            confidence=0.85,
            applicable_domains=["k8s"],
            applicable_agents=["k8s-monitor"],
        )
        assert insight.title == "OOM Recovery Pattern"
        assert insight.insight_type == InsightType.BEST_PRACTICE
        assert insight.confidence == 0.85
        assert "k8s" in insight.applicable_domains

    def test_to_dict(self):
        """Test conversion to dictionary."""
        insight = ReflectionInsight(
            title="Test Insight",
            insight_type=InsightType.KNOWLEDGE,
            description="Some knowledge",
            confidence=0.9,
        )
        data = insight.to_dict()
        assert data["title"] == "Test Insight"
        assert data["insight_type"] == "knowledge"
        assert data["description"] == "Some knowledge"
        assert data["confidence"] == 0.9

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "insight_id": "ins-123",
            "title": "Loaded Insight",
            "insight_type": "anti_pattern",
            "description": "Bad pattern",
            "evidence": ["e1", "e2"],
            "confidence": 0.7,
            "applicable_domains": ["news"],
            "applicable_agents": ["news-agent"],
        }
        insight = ReflectionInsight.from_dict(data)
        assert insight.insight_id == "ins-123"
        assert insight.title == "Loaded Insight"
        assert insight.insight_type == InsightType.ANTI_PATTERN
        assert insight.confidence == 0.7


class TestReflectionResult:
    """Tests for ReflectionResult dataclass."""

    def test_default_result(self):
        """Test default result values."""
        result = ReflectionResult()
        assert result.patterns == []
        assert result.anti_patterns == []
        assert result.best_practices == []
        assert result.knowledge == []
        assert result.skill_opportunities == []
        assert result.evaluations_analyzed == 0
        assert result.time_window_hours == 24

    def test_all_insights_property(self):
        """Test all_insights aggregation."""
        pattern = ReflectionInsight(title="P1", insight_type=InsightType.PATTERN)
        anti = ReflectionInsight(title="A1", insight_type=InsightType.ANTI_PATTERN)
        result = ReflectionResult(
            patterns=[pattern],
            anti_patterns=[anti],
        )
        all_insights = result.all_insights
        assert len(all_insights) == 2
        assert pattern in all_insights
        assert anti in all_insights

    def test_total_insights_property(self):
        """Test total_insights count."""
        result = ReflectionResult(
            patterns=[ReflectionInsight()],
            best_practices=[ReflectionInsight(), ReflectionInsight()],
        )
        assert result.total_insights == 3

    def test_to_dict(self):
        """Test conversion to dictionary."""
        insight = ReflectionInsight(title="Test")
        result = ReflectionResult(
            patterns=[insight],
            evaluations_analyzed=10,
            agents_analyzed=["agent1", "agent2"],
            time_window_hours=48,
        )
        data = result.to_dict()
        assert len(data["patterns"]) == 1
        assert data["evaluations_analyzed"] == 10
        assert data["agents_analyzed"] == ["agent1", "agent2"]
        assert data["time_window_hours"] == 48
