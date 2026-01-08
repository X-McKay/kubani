"""
Base class for diagnosis agents.

Provides shared functionality for all diagnosticians including:
- Context handling
- Evidence collection
- Finding recording
- Handoff logic
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from strands import Agent

from k8s_monitor.agents.base import create_agent
from k8s_monitor.agents.context import HandoffContext, ResourceType, Severity

logger = logging.getLogger(__name__)


class BaseDiagnostician(ABC):
    """
    Base class for all diagnosis agents.

    Provides common functionality for investigating Kubernetes issues
    and recording findings in the handoff context.
    """

    # Subclasses must define these
    NAME: str = ""
    DESCRIPTION: str = ""
    SYSTEM_PROMPT: str = ""
    RESOURCE_TYPES: list[ResourceType] = []  # Which resource types this handles

    def __init__(self):
        self._agent: Agent | None = None

    @property
    def agent(self) -> Agent:
        """Lazy initialization of the Strands agent."""
        if self._agent is None:
            self._agent = create_agent(
                name=self.NAME,
                description=self.DESCRIPTION,
                system_prompt=self.SYSTEM_PROMPT,
                tools=self.get_tools(),
                enable_mcp=True,  # All diagnosticians use MCP for K8s operations
            )
        return self._agent

    def get_tools(self) -> list[Any]:
        """
        Get tools for this diagnostician.

        Override in subclasses to add specific tools.
        Default is empty (relies on MCP tools).
        """
        return []

    def can_handle(self, resource_type: ResourceType | None) -> bool:
        """Check if this diagnostician can handle the given resource type."""
        if not resource_type:
            return False
        return resource_type in self.RESOURCE_TYPES

    def diagnose(self, context: HandoffContext) -> HandoffContext:
        """
        Diagnose the issue and enrich the context.

        Args:
            context: The handoff context with current investigation state

        Returns:
            Enriched context with findings from this agent
        """
        logger.info(f"[{self.NAME}] Starting diagnosis for {context.request_id}")

        # Build investigation prompt
        prompt = self._build_prompt(context)

        # Run the agent
        try:
            result = str(self.agent(prompt))
            self._process_result(context, result)
        except Exception as e:
            logger.error(f"[{self.NAME}] Diagnosis failed: {e}")
            context.add_finding(
                agent=self.NAME,
                description=f"Diagnosis failed: {e}",
                severity=Severity.WARNING,
            )

        return context

    def _build_prompt(self, context: HandoffContext) -> str:
        """Build the investigation prompt from context."""
        parts = [
            f"Investigate this {context.resource_type.value if context.resource_type else 'resource'} issue.",
            "",
            "CONTEXT:",
            context.get_summary(),
            "",
            "ORIGINAL REQUEST:",
            context.original_prompt,
        ]

        if context.evidence:
            parts.extend(
                [
                    "",
                    "COLLECTED EVIDENCE:",
                ]
            )
            for key, value in context.evidence.items():
                if isinstance(value, str) and len(value) > 200:
                    value = value[:200] + "..."
                parts.append(f"  {key}: {value}")

        parts.extend(
            [
                "",
                "INSTRUCTIONS:",
                "1. Investigate using your tools (logs, events, specs)",
                "2. Identify the root cause",
                "3. Determine if it can be remediated automatically",
                "4. Provide your findings in a structured format:",
                "",
                "ROOT_CAUSE: <one line description>",
                "SEVERITY: <critical|warning|info>",
                "EVIDENCE: <key findings that support your conclusion>",
                "REMEDIABLE: <yes|no>",
                "PROPOSED_FIX: <what should be done>",
            ]
        )

        return "\n".join(parts)

    def _process_result(self, context: HandoffContext, result: str) -> None:
        """Process the agent's result and update context."""

        # Extract structured fields
        root_cause = self._extract_field(result, "ROOT_CAUSE") or "Unknown"
        severity_str = self._extract_field(result, "SEVERITY") or "warning"
        evidence = self._extract_field(result, "EVIDENCE") or result[:500]
        remediable = self._extract_field(result, "REMEDIABLE") or "no"
        proposed_fix = self._extract_field(result, "PROPOSED_FIX")

        # Map severity
        severity_map = {
            "critical": Severity.CRITICAL,
            "warning": Severity.WARNING,
            "info": Severity.INFO,
        }
        severity = severity_map.get(severity_str.lower(), Severity.WARNING)

        # Update context
        context.add_finding(
            agent=self.NAME,
            description=root_cause,
            evidence={"raw_evidence": evidence},
            severity=severity,
        )

        # Set overall severity if not already set or if this is worse
        if context.severity is None or (
            severity == Severity.CRITICAL and context.severity != Severity.CRITICAL
        ):
            context.severity = severity

        # Set proposed fix if remediable
        if remediable.lower() in ("yes", "true", "1") and proposed_fix:
            context.proposed_fix = proposed_fix

        # Add raw result to evidence
        context.add_evidence(f"{self.NAME}_raw_result", result)

    def _extract_field(self, text: str, field: str) -> str | None:
        """Extract a field value from the result text."""
        import re

        pattern = rf"{field}:\s*(.+?)(?:\n[A-Z_]+:|$)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def __call__(self, prompt: str) -> str:
        """Direct agent invocation for backward compatibility."""
        return str(self.agent(prompt))

    @abstractmethod
    def get_diagnostic_steps(self) -> list[str]:
        """
        Get the diagnostic steps this agent performs.

        Returns:
            List of diagnostic steps for documentation/logging
        """
        pass
