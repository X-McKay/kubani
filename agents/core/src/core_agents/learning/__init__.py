"""
Continuous Learning Framework for Kubani Agents.

This module implements Recommendation #10 from the comprehensive improvement plan:
"Enhance the Explorer with Continuous Learning"

The framework provides:
1. Real-time learning from agent interactions
2. Skill evolution and refinement
3. Pattern recognition from failures
4. Knowledge persistence and sharing

Usage:
    from core_agents.learning import LearningManager, LearningConfig

    # Create learning manager
    manager = LearningManager()

    # Record an interaction for learning
    await manager.record_interaction(
        agent_id="k8s-healer",
        input_data={"issue": "CrashLoopBackOff"},
        output_data={"action": "restart_pod"},
        success=True,
    )

    # Get learned patterns
    patterns = await manager.get_patterns("k8s-healer")
"""

from core_agents.learning.manager import (
    LearningManager,
    LearningConfig,
    get_learning_manager,
)
from core_agents.learning.patterns import (
    Pattern,
    PatternMatcher,
    PatternType,
)
from core_agents.learning.evolution import (
    SkillEvolution,
    EvolutionStrategy,
)

__all__ = [
    # Manager
    "LearningManager",
    "LearningConfig",
    "get_learning_manager",
    # Patterns
    "Pattern",
    "PatternMatcher",
    "PatternType",
    # Evolution
    "SkillEvolution",
    "EvolutionStrategy",
]
