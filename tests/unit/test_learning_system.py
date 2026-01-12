"""
Tests for the Voyager-inspired continuous learning system.

Tests cover:
- Critic Agent evaluation
- Reflection Agent synthesis
- Skill Synthesizer generation
- Learning Manager orchestration
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import json


class TestCriticAgent:
    """Tests for the Critic Agent."""

    def test_critic_initialization(self):
        """Test Critic Agent initialization."""
        from core_agents.learning.voyager.critic import CriticAgent
        
        critic = CriticAgent(
            llm_api_url="http://localhost:8000/v1",
            llm_model="test-model",
        )
        
        assert critic.llm_api_url == "http://localhost:8000/v1"
        assert critic.llm_model == "test-model"
        assert critic.auto_approve_threshold == 0.95

    def test_critic_custom_threshold(self):
        """Test Critic Agent with custom auto-approve threshold."""
        from core_agents.learning.voyager.critic import CriticAgent
        
        critic = CriticAgent(
            llm_api_url="http://localhost:8000/v1",
            llm_model="test-model",
            auto_approve_threshold=0.8,
        )
        
        assert critic.auto_approve_threshold == 0.8

    def test_execution_analysis_dataclass(self):
        """Test ExecutionAnalysis dataclass."""
        from core_agents.learning.voyager.critic import ExecutionAnalysis, CriticVerdict
        
        analysis = ExecutionAnalysis(
            execution_id="exec-123",
            agent_name="test-agent",
            task_summary="Test task",
            success=True,
            verdict=CriticVerdict.APPROVED,
            score=0.85,
            strengths=["Good"],
            weaknesses=["Slow"],
        )
        
        assert analysis.execution_id == "exec-123"
        assert analysis.success is True
        assert analysis.verdict == CriticVerdict.APPROVED

    def test_execution_analysis_to_dict(self):
        """Test ExecutionAnalysis serialization."""
        from core_agents.learning.voyager.critic import ExecutionAnalysis, CriticVerdict
        
        analysis = ExecutionAnalysis(
            execution_id="exec-123",
            agent_name="test-agent",
            task_summary="Test task",
            success=True,
            verdict=CriticVerdict.APPROVED,
            score=0.85,
            strengths=["Good"],
            weaknesses=["Slow"],
        )
        
        data = analysis.to_dict()
        
        assert data["execution_id"] == "exec-123"
        assert data["verdict"] == "approved"
        assert data["score"] == 0.85

    def test_skill_proposal_dataclass(self):
        """Test SkillProposal dataclass."""
        from core_agents.learning.voyager.critic import SkillProposal
        
        proposal = SkillProposal(
            name="test-skill",
            description="Test skill description",
            trigger_pattern="test trigger",
            implementation="# test code",
            examples=[{"input": "test", "output": "result"}],
            source_executions=["exec-1", "exec-2"],
            confidence=0.85,
        )
        
        assert proposal.name == "test-skill"
        assert proposal.confidence == 0.85
        assert len(proposal.source_executions) == 2

    def test_skill_review_dataclass(self):
        """Test SkillReview dataclass."""
        from core_agents.learning.voyager.critic import (
            SkillProposal, SkillReview, CriticVerdict
        )
        
        proposal = SkillProposal(
            name="test-skill",
            description="Test",
            trigger_pattern="test",
            implementation="# test",
            examples=[],
            source_executions=[],
            confidence=0.8,
        )
        
        review = SkillReview(
            proposal=proposal,
            verdict=CriticVerdict.APPROVED,
            score=0.9,
            feedback="Good skill",
            quality_checks={"clarity": True, "usefulness": True},
        )
        
        assert review.verdict == CriticVerdict.APPROVED
        assert review.score == 0.9

    def test_skill_review_to_dict(self):
        """Test SkillReview serialization."""
        from core_agents.learning.voyager.critic import (
            SkillProposal, SkillReview, CriticVerdict
        )
        
        proposal = SkillProposal(
            name="test-skill",
            description="Test",
            trigger_pattern="test",
            implementation="# test",
            examples=[],
            source_executions=[],
            confidence=0.8,
        )
        
        review = SkillReview(
            proposal=proposal,
            verdict=CriticVerdict.APPROVED,
            score=0.9,
            feedback="Good skill",
        )
        
        data = review.to_dict()
        
        assert data["proposal_name"] == "test-skill"
        assert data["verdict"] == "approved"

    def test_critic_verdict_enum(self):
        """Test CriticVerdict enum values."""
        from core_agents.learning.voyager.critic import CriticVerdict
        
        assert CriticVerdict.APPROVED.value == "approved"
        assert CriticVerdict.NEEDS_REVISION.value == "needs_revision"
        assert CriticVerdict.REJECTED.value == "rejected"
        assert CriticVerdict.NEEDS_MORE_DATA.value == "needs_more_data"


class TestReflectionAgent:
    """Tests for the Reflection Agent."""

    def test_reflection_initialization(self):
        """Test Reflection Agent initialization."""
        from core_agents.learning.voyager.reflection import ReflectionAgent
        
        agent = ReflectionAgent(
            llm_api_url="http://localhost:8000/v1",
            llm_model="test-model",
        )
        
        assert agent.llm_api_url == "http://localhost:8000/v1"
        assert agent.llm_model == "test-model"

    def test_knowledge_dataclass(self):
        """Test Knowledge dataclass."""
        from core_agents.learning.voyager.reflection import (
            Knowledge, KnowledgeType, KnowledgeImportance
        )
        
        knowledge = Knowledge(
            id="knowledge-1",
            type=KnowledgeType.SKILL_PATTERN,
            importance=KnowledgeImportance.HIGH,
            title="Memory Management Pattern",
            description="Pattern for handling memory issues",
            content={"pattern": "check_limits_first"},
            source_agents=["k8s-monitor"],
            source_executions=["exec-1"],
            tags=["memory", "k8s"],
        )
        
        assert knowledge.id == "knowledge-1"
        assert knowledge.type == KnowledgeType.SKILL_PATTERN
        assert knowledge.importance == KnowledgeImportance.HIGH

    def test_knowledge_to_dict(self):
        """Test Knowledge serialization."""
        from core_agents.learning.voyager.reflection import (
            Knowledge, KnowledgeType, KnowledgeImportance
        )
        
        knowledge = Knowledge(
            id="knowledge-1",
            type=KnowledgeType.DOMAIN_INSIGHT,
            importance=KnowledgeImportance.MEDIUM,
            title="Test Knowledge",
            description="Test description",
            content={"key": "value"},
            source_agents=["test-agent"],
            source_executions=["exec-1"],
        )
        
        data = knowledge.to_dict()
        
        assert data["id"] == "knowledge-1"
        assert data["type"] == "domain_insight"
        assert data["importance"] == "medium"

    def test_reflection_report_dataclass(self):
        """Test ReflectionReport dataclass."""
        from core_agents.learning.voyager.reflection import (
            ReflectionReport, Knowledge, KnowledgeType, KnowledgeImportance
        )
        from datetime import datetime, timezone
        
        report = ReflectionReport(
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            total_executions=100,
            success_rate=0.85,
            key_learnings=[],
            skill_proposals=[],
            improvement_areas=["Error handling"],
            cross_agent_patterns=[],
            recommendations=["Improve logging"],
        )
        
        assert report.total_executions == 100
        assert report.success_rate == 0.85

    def test_knowledge_type_enum(self):
        """Test KnowledgeType enum values."""
        from core_agents.learning.voyager.reflection import KnowledgeType
        
        assert KnowledgeType.SKILL_PATTERN.value == "skill_pattern"
        assert KnowledgeType.FAILURE_PATTERN.value == "failure_pattern"
        assert KnowledgeType.DOMAIN_INSIGHT.value == "domain_insight"

    def test_knowledge_importance_enum(self):
        """Test KnowledgeImportance enum values."""
        from core_agents.learning.voyager.reflection import KnowledgeImportance
        
        assert KnowledgeImportance.CRITICAL.value == "critical"
        assert KnowledgeImportance.HIGH.value == "high"
        assert KnowledgeImportance.MEDIUM.value == "medium"
        assert KnowledgeImportance.LOW.value == "low"


class TestSkillSynthesizer:
    """Tests for the Skill Synthesizer."""

    def test_synthesizer_initialization(self):
        """Test Skill Synthesizer initialization."""
        from core_agents.learning.voyager.synthesizer import SkillSynthesizer
        from core_agents.learning.voyager.critic import CriticAgent
        
        critic = CriticAgent(
            llm_api_url="http://localhost:8000/v1",
            llm_model="test-model",
        )
        
        synthesizer = SkillSynthesizer(
            llm_api_url="http://localhost:8000/v1",
            llm_model="test-model",
            critic=critic,
        )
        
        assert synthesizer.llm_api_url == "http://localhost:8000/v1"
        assert synthesizer.critic is critic
        assert synthesizer.max_revisions == 3

    def test_synthesizer_custom_max_revisions(self):
        """Test Skill Synthesizer with custom max revisions."""
        from core_agents.learning.voyager.synthesizer import SkillSynthesizer
        from core_agents.learning.voyager.critic import CriticAgent
        
        critic = CriticAgent(
            llm_api_url="http://localhost:8000/v1",
            llm_model="test-model",
        )
        
        synthesizer = SkillSynthesizer(
            llm_api_url="http://localhost:8000/v1",
            llm_model="test-model",
            critic=critic,
            max_revisions=5,
        )
        
        assert synthesizer.max_revisions == 5

    def test_skill_candidate_dataclass(self):
        """Test SkillCandidate dataclass."""
        from core_agents.learning.voyager.synthesizer import SkillCandidate, SkillStatus
        
        candidate = SkillCandidate(
            id="skill-1",
            name="test-skill",
            description="Test skill",
            trigger_pattern="test trigger",
            implementation="# test code",
            examples=[{"input": "test"}],
            source_executions=["exec-1"],
            confidence=0.85,
        )
        
        assert candidate.id == "skill-1"
        assert candidate.status == SkillStatus.DRAFT
        assert candidate.revision_count == 0

    def test_skill_candidate_to_proposal(self):
        """Test SkillCandidate to SkillProposal conversion."""
        from core_agents.learning.voyager.synthesizer import SkillCandidate
        from core_agents.learning.voyager.critic import SkillProposal
        
        candidate = SkillCandidate(
            id="skill-1",
            name="test-skill",
            description="Test skill",
            trigger_pattern="test trigger",
            implementation="# test code",
            examples=[],
            source_executions=["exec-1"],
            confidence=0.85,
        )
        
        proposal = candidate.to_proposal()
        
        assert isinstance(proposal, SkillProposal)
        assert proposal.name == "test-skill"
        assert proposal.confidence == 0.85

    def test_skill_candidate_to_dict(self):
        """Test SkillCandidate serialization."""
        from core_agents.learning.voyager.synthesizer import SkillCandidate
        
        candidate = SkillCandidate(
            id="skill-1",
            name="test-skill",
            description="Test skill",
            trigger_pattern="test trigger",
            implementation="# test code",
            examples=[],
            source_executions=["exec-1"],
            confidence=0.85,
        )
        
        data = candidate.to_dict()
        
        assert data["id"] == "skill-1"
        assert data["name"] == "test-skill"
        assert data["status"] == "draft"

    def test_skill_candidate_to_discord_message(self):
        """Test SkillCandidate Discord message formatting."""
        from core_agents.learning.voyager.synthesizer import SkillCandidate
        
        candidate = SkillCandidate(
            id="skill-1",
            name="diagnose-oom",
            description="Diagnose OOM issues",
            trigger_pattern="pod OOMKilled",
            implementation="# Check memory",
            examples=[],
            source_executions=["exec-1"],
            confidence=0.85,
        )
        
        message = candidate.to_discord_message()
        
        assert "diagnose-oom" in message
        assert "Diagnose OOM issues" in message
        assert "85.0%" in message

    def test_skill_status_enum(self):
        """Test SkillStatus enum values."""
        from core_agents.learning.voyager.synthesizer import SkillStatus
        
        assert SkillStatus.DRAFT.value == "draft"
        assert SkillStatus.UNDER_REVIEW.value == "under_review"
        assert SkillStatus.APPROVED.value == "approved"
        assert SkillStatus.DEPLOYED.value == "deployed"


class TestLearningManager:
    """Tests for the Learning Manager."""

    def test_learning_config_defaults(self):
        """Test LearningConfig default values."""
        from core_agents.learning.voyager.manager import LearningConfig
        
        config = LearningConfig()
        
        assert config.llm_api_url == "http://localhost:8000/v1"
        assert config.llm_model == "Qwen/Qwen3-14B"
        assert config.auto_approve_threshold == 0.95
        assert config.min_examples_for_skill == 3
        assert config.reflection_interval_hours == 24

    def test_learning_config_custom_values(self):
        """Test LearningConfig with custom values."""
        from core_agents.learning.voyager.manager import LearningConfig
        
        config = LearningConfig(
            llm_api_url="http://custom:8000/v1",
            llm_model="custom-model",
            auto_approve_threshold=0.8,
            min_examples_for_skill=5,
            reflection_interval_hours=12,
        )
        
        assert config.llm_api_url == "http://custom:8000/v1"
        assert config.llm_model == "custom-model"
        assert config.auto_approve_threshold == 0.8

    def test_execution_record_dataclass(self):
        """Test ExecutionRecord dataclass."""
        from core_agents.learning.voyager.manager import ExecutionRecord
        
        record = ExecutionRecord(
            id="exec-1",
            agent_name="test-agent",
            task="Test task",
            trace=[{"step": 1, "action": "test"}],
            outcome={"result": "success"},
            success=True,
        )
        
        assert record.id == "exec-1"
        assert record.success is True
        assert record.analysis is None

    def test_interaction_logger_initialization(self):
        """Test InteractionLogger initialization."""
        from core_agents.learning.voyager.manager import InteractionLogger
        
        logger = InteractionLogger()
        
        assert logger.executions == []
        assert logger.discord_interactions == []

    @pytest.mark.asyncio
    async def test_interaction_logger_log_execution(self):
        """Test logging an execution."""
        from core_agents.learning.voyager.manager import InteractionLogger
        
        logger = InteractionLogger()
        
        record = await logger.log_execution(
            execution_id="exec-1",
            agent_name="test-agent",
            task="Test task",
            trace=[{"step": 1}],
            outcome={"result": "success"},
            success=True,
        )
        
        assert record.id == "exec-1"
        assert len(logger.executions) == 1

    def test_learning_manager_initialization(self):
        """Test LearningManager initialization."""
        from core_agents.learning.voyager.manager import LearningManager, LearningConfig
        
        config = LearningConfig()
        manager = LearningManager(config)
        
        assert manager.config == config
        assert manager.critic is not None
        assert manager.reflection is not None
        assert manager.synthesizer is not None
        assert manager.logger is not None


class TestLearningSystemIntegration:
    """Integration tests for the learning system components."""

    def test_critic_to_synthesizer_flow(self):
        """Test data flow from Critic to Synthesizer."""
        from core_agents.learning.voyager.critic import (
            ExecutionAnalysis, CriticVerdict, SkillProposal
        )
        from core_agents.learning.voyager.synthesizer import SkillCandidate
        
        # Create an execution analysis with skill opportunities
        analysis = ExecutionAnalysis(
            execution_id="exec-1",
            agent_name="k8s-monitor",
            task_summary="Diagnose OOM",
            success=True,
            verdict=CriticVerdict.APPROVED,
            score=0.9,
            skill_opportunities=[
                {
                    "name": "diagnose-oom",
                    "description": "Diagnose OOM issues",
                    "trigger": "oom_killed",
                    "confidence": 0.85,
                }
            ],
        )
        
        # Create a skill candidate from the opportunity
        opp = analysis.skill_opportunities[0]
        candidate = SkillCandidate(
            id="skill-1",
            name=opp["name"],
            description=opp["description"],
            trigger_pattern=opp["trigger"],
            implementation="# Implementation",
            examples=[],
            source_executions=[analysis.execution_id],
            confidence=opp["confidence"],
        )
        
        # Convert to proposal for review
        proposal = candidate.to_proposal()
        
        assert proposal.name == "diagnose-oom"
        assert analysis.execution_id in proposal.source_executions

    def test_full_config_to_manager_flow(self):
        """Test creating a manager with full configuration."""
        from core_agents.learning.voyager.manager import LearningManager, LearningConfig
        
        config = LearningConfig(
            llm_api_url="http://localhost:8000/v1",
            llm_model="test-model",
            qdrant_host="localhost",
            qdrant_port=6333,
            neo4j_uri="bolt://localhost:7687",
            discord_mcp_url="http://localhost:8080",
            registry_url="http://localhost:8000",
            critic_enabled=True,
            reflection_enabled=True,
            auto_synthesis_enabled=True,
        )
        
        manager = LearningManager(config)
        
        assert manager.critic.llm_api_url == config.llm_api_url
        assert manager.reflection.llm_api_url == config.llm_api_url
