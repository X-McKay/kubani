"""
Event Classifier Agent - Event classification by severity and category.

Classifies events using known patterns and LLM intelligence.

Usage:
    from kubani.agents.event_classifier import EventClassifierAgent

    agent = EventClassifierAgent()
    classification = await agent.classify_event(event)
"""

from kubani.agents.event_classifier.agent import (
    ClassificationMethod,
    EventClassification,
    EventClassifierAgent,
    K8sEvent,
)

__all__ = [
    "EventClassifierAgent",
    "EventClassification",
    "ClassificationMethod",
    "K8sEvent",
]
