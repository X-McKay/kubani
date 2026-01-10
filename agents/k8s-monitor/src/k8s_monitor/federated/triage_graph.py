"""
Triage Graph - Hybrid workflow for intelligent issue triage.

Implements the recommended "Triage Graph" pattern that combines deterministic
workflow steps with agent-based reasoning for complex cases.

The graph handles:
1. Initial classification (deterministic rules)
2. Severity assessment (deterministic + LLM for edge cases)
3. Routing to appropriate handler (agent or automated)
4. Feedback loop for learning

This reduces token usage by ~4x compared to pure agent approaches
while maintaining flexibility for complex cases.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TriageDecision(str, Enum):
    """Possible triage decisions."""

    AUTO_REMEDIATE = "auto_remediate"  # Known pattern, auto-fix
    AGENT_INVESTIGATE = "agent_investigate"  # Needs agent reasoning
    ESCALATE = "escalate"  # Human intervention needed
    ACKNOWLEDGE = "acknowledge"  # Benign, just log
    DEFER = "defer"  # Schedule for later


class IssueSeverity(str, Enum):
    """Issue severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class TriageContext:
    """Context passed through the triage graph."""

    # Input
    event_id: str
    resource_kind: str
    resource_name: str
    namespace: str
    reason: str
    message: str
    event_type: str  # Warning, Normal, Error
    count: int = 1

    # Enriched during triage
    severity: IssueSeverity = IssueSeverity.MEDIUM
    category: str = ""
    decision: TriageDecision = TriageDecision.AGENT_INVESTIGATE
    confidence: float = 0.0

    # Routing info
    handler: str = ""
    handler_params: dict[str, Any] = field(default_factory=dict)

    # Metadata
    triage_started: datetime = field(default_factory=lambda: datetime.now(UTC))
    triage_duration_ms: float = 0.0
    steps_executed: list[str] = field(default_factory=list)


class TriageResult(BaseModel):
    """Result of the triage process."""

    decision: TriageDecision
    severity: IssueSeverity
    confidence: float = Field(ge=0.0, le=1.0)
    handler: str
    reasoning: str
    suggested_action: str = ""


# -----------------------------------------------------------------------------
# Known Patterns (Deterministic Classification)
# -----------------------------------------------------------------------------

KNOWN_PATTERNS = {
    # Auto-remediable patterns
    "CrashLoopBackOff": {
        "severity": IssueSeverity.HIGH,
        "decision": TriageDecision.AUTO_REMEDIATE,
        "handler": "pod_restart",
        "confidence": 0.95,
    },
    "ImagePullBackOff": {
        "severity": IssueSeverity.HIGH,
        "decision": TriageDecision.AGENT_INVESTIGATE,
        "handler": "image_pull_investigator",
        "confidence": 0.9,
    },
    "OOMKilled": {
        "severity": IssueSeverity.CRITICAL,
        "decision": TriageDecision.AGENT_INVESTIGATE,
        "handler": "resource_analyzer",
        "confidence": 0.95,
    },
    "Unhealthy": {
        "severity": IssueSeverity.MEDIUM,
        "decision": TriageDecision.AUTO_REMEDIATE,
        "handler": "pod_restart",
        "confidence": 0.85,
    },
    "BackOff": {
        "severity": IssueSeverity.MEDIUM,
        "decision": TriageDecision.AUTO_REMEDIATE,
        "handler": "pod_restart",
        "confidence": 0.8,
    },
    # Benign patterns
    "DNSConfigForming": {
        "severity": IssueSeverity.INFO,
        "decision": TriageDecision.ACKNOWLEDGE,
        "handler": "acknowledge_benign",
        "confidence": 0.99,
    },
    "NoPods": {
        "severity": IssueSeverity.INFO,
        "decision": TriageDecision.ACKNOWLEDGE,
        "handler": "acknowledge_benign",
        "confidence": 0.95,
    },
    # Escalation patterns
    "NodeNotReady": {
        "severity": IssueSeverity.CRITICAL,
        "decision": TriageDecision.ESCALATE,
        "handler": "node_health_escalation",
        "confidence": 0.95,
    },
    "EvictionThresholdMet": {
        "severity": IssueSeverity.HIGH,
        "decision": TriageDecision.ESCALATE,
        "handler": "capacity_escalation",
        "confidence": 0.9,
    },
}

# Message patterns for additional classification
MESSAGE_PATTERNS = [
    {
        "pattern": r"Nameserver limits.*exceeded",
        "severity": IssueSeverity.INFO,
        "decision": TriageDecision.ACKNOWLEDGE,
        "reason": "DNS nameserver limit is informational",
    },
    {
        "pattern": r"Back-off restarting failed container",
        "severity": IssueSeverity.HIGH,
        "decision": TriageDecision.AUTO_REMEDIATE,
        "reason": "Container restart loop",
    },
    {
        "pattern": r"Liveness probe failed",
        "severity": IssueSeverity.HIGH,
        "decision": TriageDecision.AUTO_REMEDIATE,
        "reason": "Pod health check failing",
    },
    {
        "pattern": r"Readiness probe failed",
        "severity": IssueSeverity.MEDIUM,
        "decision": TriageDecision.DEFER,
        "reason": "Pod not ready, may recover",
    },
]


# -----------------------------------------------------------------------------
# Triage Graph Nodes
# -----------------------------------------------------------------------------


async def classify_by_pattern(ctx: TriageContext) -> TriageContext:
    """
    Node 1: Classify by known patterns.

    Fast, deterministic classification using pattern matching.
    """
    ctx.steps_executed.append("classify_by_pattern")

    # Check known patterns
    if ctx.reason in KNOWN_PATTERNS:
        pattern = KNOWN_PATTERNS[ctx.reason]
        ctx.severity = pattern["severity"]
        ctx.decision = pattern["decision"]
        ctx.handler = pattern["handler"]
        ctx.confidence = pattern["confidence"]
        ctx.category = "known_pattern"
        logger.debug(f"Pattern match: {ctx.reason} -> {ctx.decision}")
        return ctx

    # Check message patterns
    import re

    for mp in MESSAGE_PATTERNS:
        if re.search(mp["pattern"], ctx.message, re.IGNORECASE):
            ctx.severity = mp["severity"]
            ctx.decision = mp["decision"]
            ctx.confidence = 0.85
            ctx.category = "message_pattern"
            logger.debug(f"Message pattern match: {mp['reason']}")
            return ctx

    # No pattern match - needs further analysis
    ctx.confidence = 0.0
    ctx.category = "unknown"
    return ctx


async def assess_severity(ctx: TriageContext) -> TriageContext:
    """
    Node 2: Assess severity based on context.

    Considers event count, resource type, and namespace.
    """
    ctx.steps_executed.append("assess_severity")

    # Already classified with high confidence
    if ctx.confidence >= 0.8:
        return ctx

    # Severity modifiers
    severity_score = 2  # Start at medium (0=info, 1=low, 2=medium, 3=high, 4=critical)

    # High event count increases severity
    if ctx.count > 10:
        severity_score += 1
    if ctx.count > 50:
        severity_score += 1

    # Production namespaces are more critical
    if ctx.namespace in ["production", "prod", "default"]:
        severity_score += 1

    # Error events are more severe than warnings
    if ctx.event_type == "Error":
        severity_score += 1

    # Map score to severity
    severity_map = {
        0: IssueSeverity.INFO,
        1: IssueSeverity.LOW,
        2: IssueSeverity.MEDIUM,
        3: IssueSeverity.HIGH,
        4: IssueSeverity.CRITICAL,
    }
    ctx.severity = severity_map.get(min(severity_score, 4), IssueSeverity.MEDIUM)

    return ctx


async def route_decision(ctx: TriageContext) -> TriageContext:
    """
    Node 3: Make routing decision.

    Determines whether to auto-remediate, investigate, or escalate.
    """
    ctx.steps_executed.append("route_decision")

    # Already decided with high confidence
    if ctx.confidence >= 0.8:
        return ctx

    # Decision logic for unknown patterns
    if ctx.severity == IssueSeverity.CRITICAL:
        # Critical issues need agent investigation
        ctx.decision = TriageDecision.AGENT_INVESTIGATE
        ctx.handler = "full_investigation"
        ctx.confidence = 0.7

    elif ctx.severity == IssueSeverity.HIGH:
        # High severity - agent investigates
        ctx.decision = TriageDecision.AGENT_INVESTIGATE
        ctx.handler = "targeted_investigation"
        ctx.confidence = 0.7

    elif ctx.severity == IssueSeverity.MEDIUM:
        # Medium - try auto-remediation first
        ctx.decision = TriageDecision.AUTO_REMEDIATE
        ctx.handler = "pod_restart"
        ctx.confidence = 0.6

    elif ctx.severity == IssueSeverity.LOW:
        # Low - defer for batch processing
        ctx.decision = TriageDecision.DEFER
        ctx.handler = "batch_processor"
        ctx.confidence = 0.7

    else:
        # Info - just acknowledge
        ctx.decision = TriageDecision.ACKNOWLEDGE
        ctx.handler = "acknowledge_benign"
        ctx.confidence = 0.8

    return ctx


async def llm_classification(ctx: TriageContext) -> TriageContext:
    """
    Node 4: LLM-based classification for low-confidence cases.

    Only called when deterministic classification has low confidence.
    """
    ctx.steps_executed.append("llm_classification")

    # Skip if already confident
    if ctx.confidence >= 0.7:
        return ctx

    try:
        from core_agents.factory import AgentFactory, AgentConfig

        factory = AgentFactory()
        classifier = factory.create_agent(
            AgentConfig(
                name="triage-classifier",
                description="Classifies Kubernetes issues",
                system_prompt="""You are a Kubernetes expert. Classify this issue.

Respond with JSON:
{
    "severity": "critical|high|medium|low|info",
    "decision": "auto_remediate|agent_investigate|escalate|acknowledge|defer",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}""",
                tools=[],
                enable_observability=False,
            )
        )

        prompt = f"""Classify this Kubernetes issue:
- Resource: {ctx.resource_kind}/{ctx.resource_name}
- Namespace: {ctx.namespace}
- Event: {ctx.reason}
- Message: {ctx.message}
- Count: {ctx.count}
- Type: {ctx.event_type}"""

        result = classifier(prompt)
        response = str(result.message if hasattr(result, "message") else result)

        # Parse JSON response
        import json

        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(response[json_start:json_end])

            ctx.severity = IssueSeverity(data.get("severity", "medium"))
            ctx.decision = TriageDecision(data.get("decision", "agent_investigate"))
            ctx.confidence = float(data.get("confidence", 0.7))
            ctx.category = "llm_classified"

            logger.info(f"LLM classified {ctx.reason} as {ctx.decision} ({ctx.confidence:.0%})")

    except Exception as e:
        logger.warning(f"LLM classification failed: {e}")
        # Fall back to agent investigation
        ctx.decision = TriageDecision.AGENT_INVESTIGATE
        ctx.handler = "full_investigation"
        ctx.confidence = 0.5

    return ctx


async def finalize_triage(ctx: TriageContext) -> TriageContext:
    """
    Node 5: Finalize triage and prepare for execution.

    Sets handler parameters and calculates duration.
    """
    ctx.steps_executed.append("finalize_triage")

    # Set handler if not already set
    if not ctx.handler:
        handler_map = {
            TriageDecision.AUTO_REMEDIATE: "pod_restart",
            TriageDecision.AGENT_INVESTIGATE: "full_investigation",
            TriageDecision.ESCALATE: "escalation_handler",
            TriageDecision.ACKNOWLEDGE: "acknowledge_benign",
            TriageDecision.DEFER: "batch_processor",
        }
        ctx.handler = handler_map.get(ctx.decision, "full_investigation")

    # Set handler parameters
    ctx.handler_params = {
        "resource_kind": ctx.resource_kind,
        "resource_name": ctx.resource_name,
        "namespace": ctx.namespace,
        "severity": ctx.severity.value,
        "reason": ctx.reason,
    }

    # Calculate duration
    ctx.triage_duration_ms = (datetime.now(UTC) - ctx.triage_started).total_seconds() * 1000

    logger.info(
        f"Triage complete: {ctx.reason} -> {ctx.decision.value} "
        f"(severity={ctx.severity.value}, confidence={ctx.confidence:.0%}, "
        f"duration={ctx.triage_duration_ms:.0f}ms)"
    )

    return ctx


# -----------------------------------------------------------------------------
# Triage Graph Executor
# -----------------------------------------------------------------------------


class TriageGraph:
    """
    Executes the triage workflow graph.

    The graph structure:
    1. classify_by_pattern (always)
    2. assess_severity (always)
    3. route_decision (always)
    4. llm_classification (conditional: if confidence < 0.7)
    5. finalize_triage (always)
    """

    def __init__(self):
        self.nodes = [
            ("classify_by_pattern", classify_by_pattern, lambda ctx: True),
            ("assess_severity", assess_severity, lambda ctx: True),
            ("route_decision", route_decision, lambda ctx: True),
            ("llm_classification", llm_classification, lambda ctx: ctx.confidence < 0.7),
            ("finalize_triage", finalize_triage, lambda ctx: True),
        ]

    async def execute(self, ctx: TriageContext) -> TriageResult:
        """Execute the triage graph."""
        for node_name, node_fn, condition in self.nodes:
            if condition(ctx):
                try:
                    ctx = await node_fn(ctx)
                except Exception as e:
                    logger.error(f"Node {node_name} failed: {e}")
                    # Continue with default values

        return TriageResult(
            decision=ctx.decision,
            severity=ctx.severity,
            confidence=ctx.confidence,
            handler=ctx.handler,
            reasoning=f"Triage via {', '.join(ctx.steps_executed)}",
            suggested_action=self._get_suggested_action(ctx),
        )

    def _get_suggested_action(self, ctx: TriageContext) -> str:
        """Get suggested action based on decision."""
        actions = {
            TriageDecision.AUTO_REMEDIATE: f"Restart {ctx.resource_kind}/{ctx.resource_name}",
            TriageDecision.AGENT_INVESTIGATE: "Run full agent investigation",
            TriageDecision.ESCALATE: "Alert on-call engineer",
            TriageDecision.ACKNOWLEDGE: "Log and close as benign",
            TriageDecision.DEFER: "Add to batch processing queue",
        }
        return actions.get(ctx.decision, "Unknown action")


# -----------------------------------------------------------------------------
# Integration with Healer
# -----------------------------------------------------------------------------


async def triage_issue(
    event_id: str,
    resource_kind: str,
    resource_name: str,
    namespace: str,
    reason: str,
    message: str,
    event_type: str = "Warning",
    count: int = 1,
) -> TriageResult:
    """
    Triage an issue using the graph workflow.

    This is the main entry point for the triage system.
    """
    ctx = TriageContext(
        event_id=event_id,
        resource_kind=resource_kind,
        resource_name=resource_name,
        namespace=namespace,
        reason=reason,
        message=message,
        event_type=event_type,
        count=count,
    )

    graph = TriageGraph()
    return await graph.execute(ctx)
