"""
Remediator Agent - Issue investigation and remediation.

Investigates issues and performs autonomous remediation using MCP tools.
Can be used for any remediation workflow (K8s, infrastructure, etc.)

Usage:
    from agents.remediator import RemediatorAgent

    agent = RemediatorAgent()
    success, summary = await agent.handle_issue(issue)
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents._base import KubaniAgent

logger = logging.getLogger(__name__)


@dataclass
class IssueContext:
    """Context for an issue to investigate."""

    event_id: str
    pod_name: str
    namespace: str
    kind: str
    reason: str
    message: str
    severity: str
    event_type: str  # "Warning" or "Error"
    posted_stages: set = field(default_factory=set)


class RemediatorAgent(KubaniAgent):
    """
    Investigates and remediates issues.

    Uses MCP tools to diagnose problems and take corrective action.
    Posts updates to Discord at each investigation stage.
    """

    AGENT_DIR = Path(__file__).parent

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Remediator agent."""
        super().__init__(agent_dir)

        # Load skip patterns from config
        self._skip_reasons = set(self.config.get("skip_reasons", []))
        self._skip_patterns = self.config.get("skip_resource_patterns", [])

        # Remediator-specific limits
        remediator_config = self.config.get("remediator", {})
        self._max_log_lines = remediator_config.get("max_log_lines", 50)
        self._max_events = remediator_config.get("max_events", 20)
        self._max_result_chars = remediator_config.get("max_result_chars", 8000)

    def should_skip_issue(self, reason: str, resource_name: str) -> tuple[bool, str]:
        """
        Check if an issue should be skipped.

        Returns:
            Tuple of (should_skip, skip_reason)
        """
        # Check benign warning patterns
        if reason in self._skip_reasons:
            return True, f"benign warning pattern: {reason}"

        # Check resource name patterns
        for pattern in self._skip_patterns:
            if re.search(pattern, resource_name):
                return True, f"ignored resource pattern: {pattern}"

        return False, ""

    async def handle_issue(self, context: IssueContext) -> tuple[bool, str]:
        """
        Handle an issue by investigating and remediating.

        Args:
            context: Issue context with pod name, namespace, reason, etc.

        Returns:
            Tuple of (success, summary)
        """
        # Check if we should skip this issue
        should_skip, skip_reason = self.should_skip_issue(context.reason, context.pod_name)
        if should_skip:
            logger.info(f"Skipping issue: {skip_reason}")
            return True, f"Skipped: {skip_reason}"

        # Build the investigation prompt
        prompt = self._build_prompt(context)

        try:
            # Run the agent
            result = await self.run(prompt)
            return self._parse_result(result)
        except Exception as e:
            logger.error(f"Agent failed: {e}")
            return False, str(e)

    def _build_prompt(self, context: IssueContext) -> str:
        """Build the investigation prompt for the agent."""
        return f"""Issue: {context.reason} on {context.kind}/{context.pod_name} (ns: {context.namespace})
Message: {context.message}
Severity: {context.severity}

Investigate briefly, take action if possible, then conclude with one of:
- REMEDIATION_SUCCESS: <summary>
- REMEDIATION_FAILED: <why>
- CONFIG_CHANGE_NEEDED: <what>"""

    def _parse_result(self, result: str) -> tuple[bool, str]:
        """Parse the agent result into success status and summary."""
        result_upper = result.upper()

        if "REMEDIATION_SUCCESS" in result_upper:
            summary = self._extract_field(result, "REMEDIATION_SUCCESS")
            return True, summary
        elif "CONFIG_CHANGE_NEEDED" in result_upper:
            summary = self._extract_field(result, "CONFIG_CHANGE_NEEDED")
            return False, f"Config change needed: {summary}"
        else:
            summary = self._extract_field(result, "REMEDIATION_FAILED")
            return False, summary

    def _extract_field(self, text: str, field: str) -> str:
        """Extract field value from agent response."""
        pattern = rf"{field}:\s*(.+?)(?:\n[A-Z_]+:|$)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else "Unknown"

    def get_additional_tools(self) -> list[Any]:
        """
        Provide additional tools for the Remediator agent.

        Returns the discord_update tool for posting investigation updates.
        """
        from agents.remediator.tools import discord_update

        return [discord_update]

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("success", True)
        await self.record_outcome(skill_name, result, success=success)
