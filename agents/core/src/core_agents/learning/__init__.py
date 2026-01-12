"""
Continuous Learning System for Kubani Agents.

This module provides Voyager-inspired continuous learning capabilities:

- **Critic Agent**: Evaluates execution quality and provides feedback
- **Reflection Agent**: Synthesizes cross-agent knowledge and patterns
- **Skill Synthesizer**: Generates new skills from successful patterns
- **Learning Manager**: Orchestrates the entire learning lifecycle

Usage:
    from core_agents.learning import LearningManager, LearningConfig

    # Initialize the learning system
    config = LearningConfig(
        llm_api_url="https://llm.almckay.io/v1",
        discord_mcp_url="http://discord-mcp:8080",
    )
    manager = LearningManager(config)
    await manager.initialize()

    # Log an execution for learning
    await manager.log_execution(
        execution_id="exec-123",
        agent_name="k8s-monitor",
        task="Investigate pod failure",
        trace=[...],
        outcome={"resolved": True},
        success=True,
    )

    # Run learning cycle
    await manager.run_learning_cycle()
"""

# Re-export from voyager (the main learning system)
from core_agents.learning.voyager import (
    CriticAgent,
    ExecutionAnalysis,
    Knowledge,
    LearningConfig,
    LearningManager,
    ReflectionAgent,
    ReflectionReport,
    SkillCandidate,
    SkillSynthesizer,
)

# Pattern matching utilities
from core_agents.learning.patterns import (
    Pattern,
    PatternMatcher,
    PatternType,
)

# Evolution utilities
from core_agents.learning.evolution import (
    EvolutionResult,
    EvolutionStrategy,
    SkillEvolution,
    SkillVariant,
)

__all__ = [
    # Main learning system (Voyager-style)
    "LearningManager",
    "LearningConfig",
    "CriticAgent",
    "ExecutionAnalysis",
    "ReflectionAgent",
    "ReflectionReport",
    "Knowledge",
    "SkillSynthesizer",
    "SkillCandidate",
    # Pattern analysis
    "Pattern",
    "PatternMatcher",
    "PatternType",
    # Evolution
    "SkillEvolution",
    "EvolutionResult",
    "EvolutionStrategy",
    "SkillVariant",
]
