"""
Learning System Syndicate event types.

These are domain-specific events for the learning syndicate.
They follow the convention: "learning:{action}".

Usage:
    from kubani.syndicates.learning_system.events import EVALUATION_COMPLETE

    await event_bus.publish(
        EVALUATION_COMPLETE,
        {"evaluations": 10, "avg_score": 0.85},
        source="learning-system",
    )
"""

# Critic agent events
EVALUATION_COMPLETE = "learning:evaluation_complete"
EVALUATION_STARTED = "learning:evaluation_started"

# Reflection agent events
REFLECTION_COMPLETE = "learning:reflection_complete"
REFLECTION_STARTED = "learning:reflection_started"

# Skill synthesizer events
SKILL_PROPOSED = "learning:skill_proposed"
SKILL_APPROVED = "learning:skill_approved"
SKILL_REJECTED = "learning:skill_rejected"
SKILL_DEPLOYED = "learning:skill_deployed"

# Learning cycle events
CYCLE_STARTED = "learning:cycle_started"
CYCLE_COMPLETE = "learning:cycle_complete"
