"""
TriageAgent - Quick assessment and routing to specialists.

Tier 2 agent in the hierarchy that receives work from the Coordinator,
performs initial assessment, and routes to appropriate diagnosticians.
"""

import logging

from strands import Agent

from k8s_monitor.agents.base import create_agent
from k8s_monitor.agents.context import (
    HandoffContext,
    ResourceType,
    Severity,
    Urgency,
)
from k8s_monitor.tools import search_memories

logger = logging.getLogger(__name__)


TRIAGE_PROMPT = """/no_think
You are TriageAgent - the assessment and routing specialist.

ROLE: Quickly assess incoming issues and route to the right diagnostician.

PROCESS:
1. Analyze the issue/request type
2. Check memories for similar past issues
3. Determine resource type and severity
4. Route to appropriate specialist

RESOURCE TYPE DETECTION:
- Pod names, "CrashLoopBackOff", "OOMKilled", "ImagePullBackOff" → POD
- Node names, "NotReady", "MemoryPressure", "DiskPressure" → NODE
- "NetworkPolicy", "Service unreachable", "DNS" → NETWORK
- "PVC", "volume", "storage", "disk full" → STORAGE

SEVERITY ASSESSMENT:
- CRITICAL: Service down, node not ready, multiple failures
- WARNING: Single pod issue, high resource usage
- INFO: Informational queries, status checks

OUTPUT FORMAT:
After assessment, provide:
RESOURCE_TYPE: <pod|node|network|storage|unknown>
SEVERITY: <critical|warning|info>
URGENCY: <immediate|high|normal|low>
SUMMARY: <one line summary of the issue>
RECOMMENDATION: <which specialist should handle this>

Be quick and decisive. Don't investigate deeply - that's the diagnostician's job."""


class TriageAgent:
    """
    Tier 2 triage agent for issue assessment.

    Responsibilities:
    - Receive issues from Coordinator
    - Quick initial assessment
    - Memory lookup for similar issues
    - Route to appropriate diagnostician
    """

    NAME = "triage_agent"
    DESCRIPTION = "Assesses issues and routes to specialist diagnosticians"

    TOOLS = [
        search_memories,
    ]

    def __init__(self):
        self._agent: Agent | None = None

    @property
    def agent(self) -> Agent:
        """Lazy initialization of the Strands agent."""
        if self._agent is None:
            self._agent = create_agent(
                name=self.NAME,
                description=self.DESCRIPTION,
                system_prompt=TRIAGE_PROMPT,
                tools=self.TOOLS,
                enable_mcp=True,  # For quick K8s lookups
            )
        return self._agent

    def assess(self, context: HandoffContext) -> HandoffContext:
        """
        Assess an issue and enrich the context.

        Args:
            context: The handoff context with issue details

        Returns:
            Enriched context with assessment results
        """
        logger.info(f"[{self.NAME}] Assessing request {context.request_id}")

        # Build assessment prompt
        prompt = self._build_prompt(context)

        try:
            result = str(self.agent(prompt))
            self._process_result(context, result)
        except Exception as e:
            logger.error(f"[{self.NAME}] Assessment failed: {e}")
            context.add_finding(
                agent=self.NAME,
                description=f"Triage assessment failed: {e}",
                severity=Severity.WARNING,
            )

        return context

    def triage(self, prompt: str) -> HandoffContext:
        """
        Perform triage on a new issue.

        Args:
            prompt: The issue description

        Returns:
            HandoffContext with assessment results
        """
        # Create a new context for this issue
        context = HandoffContext.for_issue(prompt)
        return self.assess(context)

    def _build_prompt(self, context: HandoffContext) -> str:
        """Build the triage prompt from context."""
        parts = [
            "Assess this issue and determine the appropriate specialist.",
            "",
            "ISSUE DESCRIPTION:",
            context.original_prompt,
        ]

        if context.resource_name:
            parts.extend(
                [
                    "",
                    f"RESOURCE: {context.resource_name}",
                ]
            )

        if context.namespace:
            parts.append(f"NAMESPACE: {context.namespace}")

        if context.evidence:
            parts.extend(
                [
                    "",
                    "EXISTING EVIDENCE:",
                ]
            )
            for key, value in context.evidence.items():
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "..."
                parts.append(f"  {key}: {value}")

        parts.extend(
            [
                "",
                "First check if there are similar past issues using search_memories.",
                "Then provide your assessment.",
            ]
        )

        return "\n".join(parts)

    def _process_result(self, context: HandoffContext, result: str) -> None:
        """Process the assessment result and update context."""
        # Extract resource type
        resource_type = self._extract_resource_type(result)
        if resource_type and not context.resource_type:
            context.resource_type = resource_type

        # Extract severity
        severity = self._extract_severity(result)
        if severity and not context.severity:
            context.severity = severity

        # Extract urgency
        urgency = self._extract_urgency(result)
        if urgency and not context.urgency:
            context.urgency = urgency

        # Extract summary
        summary = self._extract_field(result, "SUMMARY")
        if summary:
            context.add_finding(
                agent=self.NAME,
                description=summary,
                severity=severity or Severity.INFO,
            )

        # Add raw result as evidence
        context.add_evidence(f"{self.NAME}_assessment", result)

        logger.info(
            f"[{self.NAME}] Assessment complete: "
            f"type={resource_type}, severity={severity}, urgency={urgency}"
        )

    def _extract_field(self, text: str, field: str) -> str | None:
        """Extract a field value from the result text."""
        import re

        pattern = rf"{field}:\s*(.+?)(?:\n[A-Z_]+:|$)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _extract_resource_type(self, result: str) -> ResourceType | None:
        """Extract resource type from assessment result."""
        type_str = self._extract_field(result, "RESOURCE_TYPE")
        if not type_str:
            return None

        type_map = {
            "pod": ResourceType.POD,
            "node": ResourceType.NODE,
            "network": ResourceType.NETWORK_POLICY,  # Map "network" to NETWORK_POLICY
            "storage": ResourceType.PVC,  # Map "storage" to PVC
            "deployment": ResourceType.DEPLOYMENT,
            "service": ResourceType.SERVICE,
            "pvc": ResourceType.PVC,
            "ingress": ResourceType.INGRESS,
            "networkpolicy": ResourceType.NETWORK_POLICY,
        }
        return type_map.get(type_str.lower())

    def _extract_severity(self, result: str) -> Severity | None:
        """Extract severity from assessment result."""
        sev_str = self._extract_field(result, "SEVERITY")
        if not sev_str:
            return None

        sev_map = {
            "critical": Severity.CRITICAL,
            "warning": Severity.WARNING,
            "info": Severity.INFO,
        }
        return sev_map.get(sev_str.lower())

    def _extract_urgency(self, result: str) -> Urgency | None:
        """Extract urgency from assessment result."""
        urg_str = self._extract_field(result, "URGENCY")
        if not urg_str:
            return None

        # Map various urgency terms to the available enum values
        urg_map = {
            "immediate": Urgency.IMMEDIATE,
            "soon": Urgency.SOON,
            "scheduled": Urgency.SCHEDULED,
            # Common aliases
            "high": Urgency.IMMEDIATE,  # Map "high" to IMMEDIATE
            "normal": Urgency.SOON,  # Map "normal" to SOON
            "low": Urgency.SCHEDULED,  # Map "low" to SCHEDULED
        }
        return urg_map.get(urg_str.lower())

    def __call__(self, prompt: str) -> str:
        """Direct agent invocation."""
        return str(self.agent(prompt))
