"""
Voyager-style Continuous Learning System.

A sophisticated learning system inspired by MineDojo's Voyager that enables
agents to continuously improve through:

1. **Critic Agent**: Evaluates executions and skill proposals
2. **Reflection Agent**: Synthesizes cross-agent knowledge
3. **Skill Synthesizer**: Generates new skills from patterns
4. **Learning Manager**: Orchestrates the entire system

Key Features:
- Automatic skill discovery from successful execution patterns
- Quality gates via Critic Agent review
- Cross-agent knowledge sharing via shared memory (Qdrant, Neo4j)
- Discord-based approval workflow for new skills
- Periodic reflection reports

Usage:
    from core_agents.learning.voyager import get_learning_manager, LearningConfig

    config = LearningConfig(
        llm_api_url="http://localhost:8000/v1",
        discord_mcp_url="http://localhost:8080",
    )

    manager = get_learning_manager(config)
    await manager.start()

    # Log executions
    await manager.on_execution_complete(
        execution_id="exec_123",
        agent_name="k8s-monitor",
        task="Diagnose pod failure",
        trace=[...],
        outcome={...},
        success=True,
    )

    # Handle Discord feedback
    await manager.on_discord_feedback(
        message_id="msg_456",
        channel_id="learning",
        reaction="✅",
        user="admin",
    )
"""

from core_agents.learning.voyager.critic import (
    CriticAgent,
    CriticVerdict,
    ExecutionAnalysis,
    SkillProposal,
    SkillReview,
)
from core_agents.learning.voyager.manager import (
    ExecutionRecord,
    InteractionLogger,
    LearningConfig,
    LearningManager,
    get_learning_manager,
)
from core_agents.learning.voyager.reflection import (
    Knowledge,
    KnowledgeImportance,
    KnowledgeType,
    ReflectionAgent,
    ReflectionReport,
)
from core_agents.learning.voyager.synthesizer import (
    SkillCandidate,
    SkillStatus,
    SkillSynthesizer,
)

__all__ = [
    # Critic
    "CriticAgent",
    "CriticVerdict",
    "ExecutionAnalysis",
    "SkillProposal",
    "SkillReview",
    # Reflection
    "ReflectionAgent",
    "ReflectionReport",
    "Knowledge",
    "KnowledgeType",
    "KnowledgeImportance",
    # Synthesizer
    "SkillSynthesizer",
    "SkillCandidate",
    "SkillStatus",
    # Manager
    "LearningManager",
    "LearningConfig",
    "InteractionLogger",
    "ExecutionRecord",
    "get_learning_manager",
]
