"""
K8s Monitor Syndicate - Kubernetes cluster health monitoring.

Orchestrates event classification, issue remediation, and skill learning
to keep the cluster healthy and improve over time.

Usage:
    from syndicates.k8s_monitor import K8sMonitorSyndicate

    syndicate = K8sMonitorSyndicate()
    await syndicate.start()
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from kubani.agents.event_classifier import EventClassifierAgent, K8sEvent
from kubani.agents.remediator import IssueContext, RemediatorAgent
from kubani.agents.skill_learner import SkillLearnerAgent
from kubani.framework.events import EventType, get_event_bus
from kubani.syndicates._base import Syndicate

logger = logging.getLogger(__name__)


class K8sMonitorSyndicate(Syndicate):
    """
    Kubernetes cluster health monitoring syndicate.

    Orchestrates three agents:
    - EventClassifierAgent: Watches and classifies K8s events
    - RemediatorAgent: Investigates and fixes issues
    - SkillLearnerAgent: Learns from failures to improve

    The syndicate runs continuously, watching for events and
    coordinating remediation efforts.
    """

    SYNDICATE_DIR = Path(__file__).parent

    agents = [
        EventClassifierAgent,
        RemediatorAgent,
        SkillLearnerAgent,
    ]

    def __init__(self, syndicate_dir: Path | None = None):
        """Initialize the K8s Monitor syndicate."""
        super().__init__(syndicate_dir)
        self._event_bus = None

    async def run(self) -> None:
        """
        Main orchestration loop.

        Runs three concurrent tasks:
        1. Event watching and classification
        2. Issue remediation
        3. Periodic skill learning
        """
        self._event_bus = await get_event_bus()

        # Get agent instances
        classifier = self.get_agent(EventClassifierAgent)
        remediator = self.get_agent(RemediatorAgent)
        learner = self.get_agent(SkillLearnerAgent)

        logger.info(f"Starting {self.name} with agents: {[a.__name__ for a in self.agents]}")

        # Run all tasks concurrently
        await asyncio.gather(
            self._watch_and_classify(classifier, remediator),
            self._handle_remediation_failures(learner),
            self._periodic_skill_learning(learner),
        )

    async def _watch_and_classify(
        self,
        classifier: EventClassifierAgent,
        remediator: RemediatorAgent,
    ) -> None:
        """Watch K8s events, classify them, and trigger remediation."""
        logger.info("Starting event watch loop")

        async for event in self._event_bus.subscribe(
            EventType.K8S_ISSUE_DETECTED,
            consumer_group=self.name,
            consumer_name=f"{self.name}-classifier",
        ):
            if not self._running:
                break

            try:
                await self._process_event(event, classifier, remediator)
            except Exception as e:
                logger.error(f"Error processing event: {e}")

    async def _process_event(
        self,
        event: Any,
        classifier: EventClassifierAgent,
        remediator: RemediatorAgent,
    ) -> None:
        """Process a single K8s event."""
        payload = event.payload
        k8s_event_data = payload.get("event", {})

        # Create K8sEvent from payload
        k8s_event = K8sEvent.from_dict(k8s_event_data)

        # Check if event should be ignored
        if classifier.should_ignore_event(k8s_event):
            logger.debug(f"Ignoring event: {k8s_event.reason}")
            return

        # Classify the event
        classification = await classifier.classify_event(k8s_event)

        logger.info(
            f"Classified {k8s_event.reason}: "
            f"severity={classification.severity}, "
            f"actionable={classification.is_actionable}"
        )

        # If actionable, hand off to remediator
        if classification.is_actionable:
            await self.handoff(
                from_agent=classifier,
                to_agent=remediator,
                context={
                    "event": k8s_event.to_dict(),
                    "classification": classification.model_dump(),
                },
                reason=f"Actionable {classification.severity} issue: {k8s_event.reason}",
            )

            # Create issue context for remediator
            issue_context = IssueContext(
                event_id=event.id,
                pod_name=k8s_event.name,
                namespace=k8s_event.namespace,
                kind=k8s_event.kind,
                reason=k8s_event.reason,
                message=k8s_event.message,
                severity=classification.severity,
                event_type=k8s_event.type,
            )

            # Run remediation
            success, summary = await remediator.handle_issue(issue_context)

            # Publish result
            event_type = (
                EventType.K8S_REMEDIATION_COMPLETED if success else EventType.K8S_REMEDIATION_FAILED
            )

            await self._event_bus.publish(
                event_type,
                {
                    "issue_id": event.id,
                    "resource": f"{k8s_event.kind}/{k8s_event.name}",
                    "namespace": k8s_event.namespace,
                    "reason": k8s_event.reason,
                    "success": success,
                    "summary": summary,
                },
                source=self.name,
            )

    async def _handle_remediation_failures(
        self,
        learner: SkillLearnerAgent,
    ) -> None:
        """Listen for remediation failures and record them for learning."""
        logger.info("Starting remediation failure handler")

        async for event in self._event_bus.subscribe(
            EventType.K8S_REMEDIATION_FAILED,
            consumer_group=f"{self.name}-learner",
            consumer_name=f"{self.name}-learner",
        ):
            if not self._running:
                break

            try:
                payload = event.payload
                if payload.get("escalated", True):  # Only learn from escalated failures
                    learner.record_incident(payload)
                    logger.info(f"Recorded failure for learning: {payload.get('reason')}")
            except Exception as e:
                logger.error(f"Error recording failure: {e}")

    async def _periodic_skill_learning(
        self,
        learner: SkillLearnerAgent,
    ) -> None:
        """Periodically analyze failures and propose new skills."""
        schedule = self.config.get("schedule", {}).get("learn_skills", {})
        if not schedule.get("enabled", True):
            logger.info("Skill learning disabled")
            return

        # Run every 6 hours (or as configured)
        interval_hours = 6
        interval_seconds = interval_hours * 3600

        logger.info(f"Starting skill learning loop (every {interval_hours}h)")

        while self._running:
            await asyncio.sleep(interval_seconds)

            if not self._running:
                break

            try:
                proposals = await learner.analyze_and_propose()
                if proposals > 0:
                    logger.info(f"Proposed {proposals} new skills")
            except Exception as e:
                logger.error(f"Error in skill learning: {e}")
