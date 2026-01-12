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


class TestCriticAgent:
    """Tests for the Critic Agent."""

    def test_critic_initialization(self):
        """Test Critic Agent initialization."""
        from core_agents.learning.voyager.critic import CriticAgent
        
        critic = CriticAgent()
        
        assert critic.name == "critic"
        assert critic.evaluation_criteria is not None

    @pytest.mark.asyncio
    async def test_evaluate_execution_success(self):
        """Test successful execution evaluation."""
        from core_agents.learning.voyager.critic import CriticAgent, ExecutionContext, CriticEvaluation
        
        critic = CriticAgent()
        
        context = ExecutionContext(
            agent_id="test-agent",
            workflow_id="test-workflow-123",
            task_description="Investigate pod failure",
            actions_taken=["Get pod logs", "Check events", "Analyze memory"],
            outcome="Successfully identified OOM kill",
            success=True,
            duration_seconds=45.0,
            timestamp=datetime.now(timezone.utc),
        )
        
        with patch.object(critic, "_call_llm") as mock_llm:
            mock_llm.return_value = {
                "score": 0.85,
                "reasoning": "Good investigation process",
                "strengths": ["Thorough analysis"],
                "improvements": ["Could check resource limits earlier"],
                "learnings": ["OOM kills indicate memory pressure"],
            }
            
            evaluation = await critic.evaluate_execution(context)
            
            assert isinstance(evaluation, CriticEvaluation)
            assert evaluation.score == 0.85
            assert len(evaluation.strengths) > 0

    @pytest.mark.asyncio
    async def test_evaluate_execution_failure(self):
        """Test evaluation of failed execution."""
        from core_agents.learning.voyager.critic import CriticAgent, ExecutionContext
        
        critic = CriticAgent()
        
        context = ExecutionContext(
            agent_id="test-agent",
            workflow_id="test-workflow-456",
            task_description="Scale deployment",
            actions_taken=["Check current replicas"],
            outcome="Failed to scale - permission denied",
            success=False,
            duration_seconds=10.0,
            timestamp=datetime.now(timezone.utc),
        )
        
        with patch.object(critic, "_call_llm") as mock_llm:
            mock_llm.return_value = {
                "score": 0.3,
                "reasoning": "Failed due to RBAC issues",
                "strengths": [],
                "improvements": ["Check permissions before attempting action"],
                "learnings": ["RBAC permissions must be verified"],
            }
            
            evaluation = await critic.evaluate_execution(context)
            
            assert evaluation.score < 0.5
            assert len(evaluation.improvements) > 0

    @pytest.mark.asyncio
    async def test_batch_evaluate(self):
        """Test batch evaluation of multiple executions."""
        from core_agents.learning.voyager.critic import CriticAgent, ExecutionContext
        
        critic = CriticAgent()
        
        contexts = [
            ExecutionContext(
                agent_id="test-agent",
                workflow_id=f"workflow-{i}",
                task_description=f"Task {i}",
                actions_taken=["Action 1"],
                outcome="Success",
                success=True,
                duration_seconds=30.0,
                timestamp=datetime.now(timezone.utc),
            )
            for i in range(3)
        ]
        
        with patch.object(critic, "evaluate_execution") as mock_eval:
            mock_eval.return_value = MagicMock(score=0.8)
            
            evaluations = await critic.batch_evaluate(contexts)
            
            assert len(evaluations) == 3
            assert mock_eval.call_count == 3


class TestReflectionAgent:
    """Tests for the Reflection Agent."""

    def test_reflection_initialization(self):
        """Test Reflection Agent initialization."""
        from core_agents.learning.voyager.reflection import ReflectionAgent
        
        agent = ReflectionAgent()
        
        assert agent.name == "reflection"

    @pytest.mark.asyncio
    async def test_synthesize_learnings(self):
        """Test learning synthesis."""
        from core_agents.learning.voyager.reflection import ReflectionAgent, Learning, ReflectionResult
        
        agent = ReflectionAgent()
        
        learnings = [
            Learning(
                id="learning-1",
                agent_id="k8s-monitor",
                content="OOM kills indicate memory pressure",
                learning_type="pattern",
                confidence=0.85,
                timestamp=datetime.now(timezone.utc),
            ),
            Learning(
                id="learning-2",
                agent_id="k8s-monitor",
                content="Memory limits should be set based on actual usage",
                learning_type="best_practice",
                confidence=0.9,
                timestamp=datetime.now(timezone.utc),
            ),
        ]
        
        with patch.object(agent, "_call_llm") as mock_llm:
            mock_llm.return_value = {
                "patterns": [{"name": "Memory Management", "description": "..."}],
                "insights": ["Memory issues are common"],
                "knowledge_updates": [],
                "skill_suggestions": [],
            }
            
            result = await agent.synthesize_learnings(learnings)
            
            assert isinstance(result, ReflectionResult)
            assert len(result.patterns) > 0

    @pytest.mark.asyncio
    async def test_identify_patterns(self):
        """Test pattern identification across learnings."""
        from core_agents.learning.voyager.reflection import ReflectionAgent, Learning
        
        agent = ReflectionAgent()
        
        learnings = [
            Learning(
                id=f"learning-{i}",
                agent_id="k8s-monitor",
                content=f"Learning {i} about memory",
                learning_type="pattern",
                confidence=0.8,
                timestamp=datetime.now(timezone.utc),
            )
            for i in range(5)
        ]
        
        with patch.object(agent, "_call_llm") as mock_llm:
            mock_llm.return_value = {
                "patterns": [
                    {"name": "Memory Pattern", "occurrences": 5, "confidence": 0.9}
                ],
            }
            
            patterns = await agent.identify_patterns(learnings)
            
            assert len(patterns) > 0

    @pytest.mark.asyncio
    async def test_update_knowledge_graph(self):
        """Test knowledge graph updates."""
        from core_agents.learning.voyager.reflection import ReflectionAgent, ReflectionResult
        
        agent = ReflectionAgent()
        
        result = ReflectionResult(
            patterns=[],
            insights=["New insight"],
            knowledge_updates=[
                {"entity": "kubernetes/memory", "relationship": "causes", "target": "oom-kill"}
            ],
            skill_suggestions=[],
        )
        
        with patch.object(agent, "_memory_client") as mock_memory:
            mock_memory.create_relationship = AsyncMock()
            
            await agent.update_knowledge_graph(result)
            
            mock_memory.create_relationship.assert_called()


class TestSkillSynthesizer:
    """Tests for the Skill Synthesizer."""

    def test_synthesizer_initialization(self):
        """Test Skill Synthesizer initialization."""
        from core_agents.learning.voyager.synthesizer import SkillSynthesizer
        
        synthesizer = SkillSynthesizer()
        
        assert synthesizer.name == "skill-synthesizer"

    @pytest.mark.asyncio
    async def test_propose_skill(self):
        """Test skill proposal generation."""
        from core_agents.learning.voyager.synthesizer import SkillSynthesizer, SkillProposal
        from core_agents.learning.voyager.critic import CriticEvaluation
        
        synthesizer = SkillSynthesizer()
        
        evaluations = [
            CriticEvaluation(
                execution_id="exec-1",
                score=0.9,
                reasoning="Excellent memory diagnosis",
                strengths=["Thorough analysis"],
                improvements=[],
                learnings=["OOM pattern detection"],
                timestamp=datetime.now(timezone.utc),
            ),
        ]
        
        with patch.object(synthesizer, "_call_llm") as mock_llm:
            mock_llm.return_value = {
                "name": "diagnose-oom-kill",
                "description": "Diagnose OOM kill issues",
                "category": "k8s/diagnostic",
                "triggers": ["oom_killed"],
                "implementation": "# Skill implementation...",
                "confidence": 0.85,
            }
            
            proposal = await synthesizer.propose_skill(evaluations)
            
            assert isinstance(proposal, SkillProposal)
            assert proposal.name == "diagnose-oom-kill"
            assert proposal.confidence >= 0.0

    @pytest.mark.asyncio
    async def test_validate_skill(self):
        """Test skill validation."""
        from core_agents.learning.voyager.synthesizer import SkillSynthesizer, SkillProposal
        
        synthesizer = SkillSynthesizer()
        
        proposal = SkillProposal(
            id="proposal-1",
            name="test-skill",
            description="Test skill",
            category="test",
            triggers=["test_trigger"],
            implementation="# Valid implementation",
            confidence=0.8,
            source_evaluations=["eval-1"],
            timestamp=datetime.now(timezone.utc),
        )
        
        with patch.object(synthesizer, "_validate_syntax") as mock_syntax, \
             patch.object(synthesizer, "_validate_safety") as mock_safety:
            mock_syntax.return_value = True
            mock_safety.return_value = True
            
            is_valid = await synthesizer.validate_skill(proposal)
            
            assert is_valid is True

    @pytest.mark.asyncio
    async def test_generate_skill_markdown(self):
        """Test skill Markdown generation."""
        from core_agents.learning.voyager.synthesizer import SkillSynthesizer, SkillProposal
        
        synthesizer = SkillSynthesizer()
        
        proposal = SkillProposal(
            id="proposal-1",
            name="test-skill",
            description="Test skill description",
            category="k8s/diagnostic",
            triggers=["test_trigger"],
            implementation="# Implementation code",
            confidence=0.85,
            source_evaluations=["eval-1"],
            timestamp=datetime.now(timezone.utc),
        )
        
        markdown = synthesizer.generate_skill_markdown(proposal)
        
        assert "test-skill" in markdown
        assert "k8s/diagnostic" in markdown
        assert "test_trigger" in markdown


class TestLearningManager:
    """Tests for the Learning Manager."""

    def test_manager_initialization(self):
        """Test Learning Manager initialization."""
        from core_agents.learning.voyager.manager import LearningManager
        
        manager = LearningManager()
        
        assert manager.critic is not None
        assert manager.reflection is not None
        assert manager.synthesizer is not None

    @pytest.mark.asyncio
    async def test_process_execution(self):
        """Test processing a single execution."""
        from core_agents.learning.voyager.manager import LearningManager
        from core_agents.learning.voyager.critic import ExecutionContext
        
        manager = LearningManager()
        
        context = ExecutionContext(
            agent_id="test-agent",
            workflow_id="workflow-123",
            task_description="Test task",
            actions_taken=["Action 1"],
            outcome="Success",
            success=True,
            duration_seconds=30.0,
            timestamp=datetime.now(timezone.utc),
        )
        
        with patch.object(manager.critic, "evaluate_execution") as mock_eval, \
             patch.object(manager, "_store_evaluation") as mock_store:
            mock_eval.return_value = MagicMock(score=0.8)
            mock_store.return_value = None
            
            evaluation = await manager.process_execution(context)
            
            assert evaluation is not None
            mock_store.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_reflection_cycle(self):
        """Test running a reflection cycle."""
        from core_agents.learning.voyager.manager import LearningManager
        
        manager = LearningManager()
        
        with patch.object(manager, "_get_recent_learnings") as mock_learnings, \
             patch.object(manager.reflection, "synthesize_learnings") as mock_synth, \
             patch.object(manager, "_store_reflection_result") as mock_store:
            mock_learnings.return_value = []
            mock_synth.return_value = MagicMock(patterns=[], insights=[])
            mock_store.return_value = None
            
            result = await manager.run_reflection_cycle()
            
            assert result is not None

    @pytest.mark.asyncio
    async def test_propose_new_skills(self):
        """Test proposing new skills."""
        from core_agents.learning.voyager.manager import LearningManager
        
        manager = LearningManager()
        
        with patch.object(manager, "_get_high_quality_evaluations") as mock_evals, \
             patch.object(manager.synthesizer, "propose_skill") as mock_propose, \
             patch.object(manager, "_submit_for_approval") as mock_submit:
            mock_evals.return_value = [MagicMock(score=0.9)]
            mock_propose.return_value = MagicMock(confidence=0.85)
            mock_submit.return_value = None
            
            proposals = await manager.propose_new_skills()
            
            assert len(proposals) > 0

    @pytest.mark.asyncio
    async def test_handle_approval(self):
        """Test handling skill approval."""
        from core_agents.learning.voyager.manager import LearningManager
        from core_agents.learning.voyager.synthesizer import SkillProposal
        
        manager = LearningManager()
        
        proposal = SkillProposal(
            id="proposal-1",
            name="approved-skill",
            description="Approved skill",
            category="test",
            triggers=["trigger"],
            implementation="# Code",
            confidence=0.9,
            source_evaluations=[],
            timestamp=datetime.now(timezone.utc),
        )
        
        with patch.object(manager, "_deploy_skill") as mock_deploy, \
             patch.object(manager, "_notify_deployment") as mock_notify:
            mock_deploy.return_value = True
            mock_notify.return_value = None
            
            success = await manager.handle_approval(proposal.id, approved=True)
            
            assert success is True
            mock_deploy.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_rejection(self):
        """Test handling skill rejection."""
        from core_agents.learning.voyager.manager import LearningManager
        
        manager = LearningManager()
        
        with patch.object(manager, "_mark_rejected") as mock_reject:
            mock_reject.return_value = None
            
            success = await manager.handle_approval("proposal-1", approved=False)
            
            assert success is True
            mock_reject.assert_called_once()


class TestDiscordApprovalWorkflow:
    """Tests for the Discord approval workflow."""

    @pytest.mark.asyncio
    async def test_post_approval_request(self):
        """Test posting approval request to Discord."""
        from core_agents.learning.voyager.manager import LearningManager
        from core_agents.learning.voyager.synthesizer import SkillProposal
        
        manager = LearningManager()
        
        proposal = SkillProposal(
            id="proposal-1",
            name="new-skill",
            description="New skill for approval",
            category="k8s/diagnostic",
            triggers=["trigger"],
            implementation="# Code",
            confidence=0.85,
            source_evaluations=["eval-1"],
            timestamp=datetime.now(timezone.utc),
        )
        
        with patch.object(manager, "_discord_client") as mock_discord:
            mock_discord.send_embed = AsyncMock(return_value={"id": "msg-123"})
            mock_discord.add_reaction = AsyncMock()
            
            message_id = await manager._post_approval_request(proposal)
            
            assert message_id == "msg-123"
            # Should add approval reactions
            assert mock_discord.add_reaction.call_count >= 3

    @pytest.mark.asyncio
    async def test_check_approval_status(self):
        """Test checking approval status from reactions."""
        from core_agents.learning.voyager.manager import LearningManager
        
        manager = LearningManager()
        
        with patch.object(manager, "_discord_client") as mock_discord:
            mock_discord.get_reactions = AsyncMock(return_value={
                "✅": 3,
                "❌": 1,
                "🔄": 0,
            })
            
            status = await manager._check_approval_status("msg-123")
            
            assert status == "approved"  # More approvals than rejections

    @pytest.mark.asyncio
    async def test_approval_timeout(self):
        """Test approval timeout handling."""
        from core_agents.learning.voyager.manager import LearningManager
        
        manager = LearningManager()
        
        with patch.object(manager, "_get_pending_proposals") as mock_pending, \
             patch.object(manager, "_check_proposal_age") as mock_age, \
             patch.object(manager, "_handle_timeout") as mock_timeout:
            mock_pending.return_value = [{"id": "old-proposal"}]
            mock_age.return_value = 73  # Hours (> 72 hour timeout)
            mock_timeout.return_value = None
            
            await manager.check_approval_timeouts()
            
            mock_timeout.assert_called_once()
