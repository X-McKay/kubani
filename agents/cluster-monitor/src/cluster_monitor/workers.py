"""
Worker Agents - Specialized agents for investigation tasks.

Workers are lightweight agents with specific responsibilities:
- Investigator: Runs diagnostic skills and gathers information
- Memory: Queries and stores learnings
- Remediator: Plans and executes remediation actions
- Narrator: Crafts conversational Discord updates
"""

import logging
from typing import Any

from strands import Agent, tool
from strands.tools.mcp import MCPClient

from cluster_monitor.models import WorkerResult, WorkerTask
from core_agents.factory import AgentConfig, AgentFactory
from core_agents.integrations.discord_mcp import send_discord_message

logger = logging.getLogger(__name__)


# =============================================================================
# Investigator Worker
# =============================================================================


class InvestigatorWorker:
    """
    Investigator Worker - Runs diagnostic skills and gathers information.

    Uses Kubernetes MCP tools to:
    - Check pod logs
    - Examine recent events
    - Analyze resource utilization
    - Run diagnostic skills
    """

    def __init__(self, factory: AgentFactory | None = None):
        self.factory = factory or AgentFactory()
        self._agent: Agent | None = None

    async def _get_agent(self) -> Agent:
        """Get or create the investigator agent."""
        if self._agent is None:
            # TODO: Load kubernetes-mcp-server client
            # For now, create a basic agent
            self._agent = self.factory.create_agent(
                AgentConfig(
                    name="investigator",
                    description="Diagnostic specialist for Kubernetes issues",
                    system_prompt=(
                        "You are an expert Kubernetes diagnostic specialist. "
                        "Your job is to investigate issues by checking logs, events, "
                        "and resource states. Provide clear, detailed findings."
                    ),
                    tools=[],  # TODO: Add kubernetes-mcp tools
                )
            )
        return self._agent

    async def investigate(self, task: WorkerTask) -> WorkerResult:
        """
        Investigate a Kubernetes issue.

        Args:
            task: Task containing events and pattern information

        Returns:
            WorkerResult with diagnostic findings
        """
        logger.info(f"Investigator: Processing task {task.task_id}")

        try:
            agent = await self._get_agent()
            events = task.context.get("events", [])
            pattern = task.context.get("pattern", "unknown")

            # Build investigation prompt
            event_descriptions = "\n".join(
                [
                    f"- {e['resource_kind']}/{e['resource_name']} in {e['namespace']}: "
                    f"{e['reason']} - {e['message']}"
                    for e in events
                ]
            )

            prompt = f"""Investigate the following Kubernetes issue(s):

Pattern: {pattern}
Events:
{event_descriptions}

Please:
1. Identify the likely root cause
2. Check relevant logs and events
3. Assess the severity and impact
4. Provide specific diagnostic findings

Be thorough but concise."""

            # TODO: Actually run the agent with MCP tools
            # For now, return mock findings
            findings = {
                "root_cause": f"Likely {pattern} issue",
                "affected_resources": [e["resource_name"] for e in events],
                "severity_assessment": "medium",
                "recommendations": ["Check network connectivity", "Review recent changes"],
            }

            return WorkerResult(
                task_id=task.task_id,
                success=True,
                data=findings,
            )

        except Exception as e:
            logger.error(f"Investigator failed: {e}", exc_info=True)
            return WorkerResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
            )


# =============================================================================
# Memory Worker
# =============================================================================


class MemoryWorker:
    """
    Memory Worker - Queries and stores learnings.

    Uses Memory MCP server to:
    - Query for similar past incidents
    - Store investigation outcomes
    - Retrieve remediation patterns
    """

    def __init__(self, factory: AgentFactory | None = None):
        self.factory = factory or AgentFactory()
        self._agent: Agent | None = None

    async def _get_agent(self) -> Agent:
        """Get or create the memory agent."""
        if self._agent is None:
            # TODO: Load memory-mcp-server client
            self._agent = self.factory.create_agent(
                AgentConfig(
                    name="memory",
                    description="Memory specialist for learning from past incidents",
                    system_prompt=(
                        "You are a memory specialist. Your job is to query our "
                        "knowledge base for similar past incidents and store new learnings. "
                        "Focus on finding actionable patterns and successful resolutions."
                    ),
                    tools=[],  # TODO: Add memory-mcp tools
                )
            )
        return self._agent

    async def query_memory(self, task: WorkerTask) -> WorkerResult:
        """
        Query memory for similar past incidents.

        Args:
            task: Task containing query parameters

        Returns:
            WorkerResult with past incidents
        """
        logger.info(f"Memory: Querying for task {task.task_id}")

        try:
            query = task.context.get("query", "")
            min_confidence = task.context.get("min_confidence", 0.7)

            # TODO: Actually query memory-mcp-server
            # For now, return mock past incidents
            past_incidents = [
                {
                    "timestamp": "2026-01-10T14:30:00Z",
                    "pattern": "timeout",
                    "resolution_action": "restarted CNI plugin",
                    "resolution_success": True,
                    "confidence": 0.85,
                },
            ]

            return WorkerResult(
                task_id=task.task_id,
                success=True,
                data={"learnings": past_incidents},
            )

        except Exception as e:
            logger.error(f"Memory query failed: {e}", exc_info=True)
            return WorkerResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
            )

    async def store_learning(self, task: WorkerTask) -> WorkerResult:
        """
        Store a learning from an investigation.

        Args:
            task: Task containing investigation outcome

        Returns:
            WorkerResult confirming storage
        """
        logger.info(f"Memory: Storing learning for task {task.task_id}")

        try:
            investigation = task.context.get("investigation", {})
            pattern = task.context.get("pattern", "unknown")
            success = task.context.get("resolution_success", False)

            # TODO: Actually store in memory-mcp-server
            logger.info(f"Stored learning: pattern={pattern}, success={success}")

            return WorkerResult(
                task_id=task.task_id,
                success=True,
                data={"stored": True},
            )

        except Exception as e:
            logger.error(f"Memory storage failed: {e}", exc_info=True)
            return WorkerResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
            )


# =============================================================================
# Remediator Worker
# =============================================================================


class RemediatorWorker:
    """
    Remediator Worker - Plans and executes remediation actions.

    Uses Kubernetes MCP tools and remediation skills to:
    - Plan remediation based on findings
    - Execute remediation actions
    - Verify results
    """

    def __init__(self, factory: AgentFactory | None = None):
        self.factory = factory or AgentFactory()
        self._agent: Agent | None = None

    async def _get_agent(self) -> Agent:
        """Get or create the remediator agent."""
        if self._agent is None:
            # TODO: Load kubernetes-mcp-server client and remediation skills
            self._agent = self.factory.create_agent(
                AgentConfig(
                    name="remediator",
                    description="Remediation specialist for Kubernetes issues",
                    system_prompt=(
                        "You are a Kubernetes remediation specialist. Your job is to "
                        "plan and execute safe remediation actions based on diagnostic "
                        "findings. Always explain what you're doing and why."
                    ),
                    tools=[],  # TODO: Add kubernetes-mcp tools and skills
                )
            )
        return self._agent

    async def plan_remediation(self, task: WorkerTask) -> WorkerResult:
        """
        Plan a remediation action.

        Args:
            task: Task containing findings and known remediations

        Returns:
            WorkerResult with remediation plan
        """
        logger.info(f"Remediator: Planning for task {task.task_id}")

        try:
            findings = task.context.get("findings", {})
            known_remediation = task.context.get("known_remediation")
            pattern = task.context.get("pattern", "unknown")

            # TODO: Use agent to plan remediation
            # For now, return mock plan
            plan = {
                "action": known_remediation or f"restart affected pods",
                "reason": f"Based on {pattern} pattern and diagnostic findings",
                "risk_level": "low",
                "requires_approval": False,
            }

            return WorkerResult(
                task_id=task.task_id,
                success=True,
                data=plan,
            )

        except Exception as e:
            logger.error(f"Remediation planning failed: {e}", exc_info=True)
            return WorkerResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
            )

    async def execute_remediation(self, task: WorkerTask) -> WorkerResult:
        """
        Execute a remediation action.

        Args:
            task: Task containing remediation plan

        Returns:
            WorkerResult with execution outcome
        """
        logger.info(f"Remediator: Executing for task {task.task_id}")

        try:
            action = task.context.get("action", "")
            
            # TODO: Actually execute remediation
            # For now, return mock success
            logger.info(f"Executed remediation: {action}")

            return WorkerResult(
                task_id=task.task_id,
                success=True,
                data={"action_taken": action, "result": "success"},
            )

        except Exception as e:
            logger.error(f"Remediation execution failed: {e}", exc_info=True)
            return WorkerResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
            )


# =============================================================================
# Narrator Worker
# =============================================================================


class NarratorWorker:
    """
    Narrator Worker - Crafts conversational Discord updates.

    Transforms structured information into natural language narratives
    that feel like an engineer explaining their thought process.
    """

    def __init__(self, factory: AgentFactory | None = None):
        self.factory = factory or AgentFactory()
        self._agent: Agent | None = None

    async def _get_agent(self) -> Agent:
        """Get or create the narrator agent."""
        if self._agent is None:
            self._agent = self.factory.create_agent(
                AgentConfig(
                    name="narrator",
                    description="Communications specialist for conversational updates",
                    system_prompt=(
                        "You are a skilled technical communicator. Your job is to explain "
                        "complex Kubernetes investigations in a clear, conversational way. "
                        "Write like an experienced engineer talking to a colleague - be "
                        "informative, transparent about your process, and avoid jargon where "
                        "possible. Use natural language, not templates."
                    ),
                    tools=[],
                )
            )
        return self._agent

    async def narrate(self, task: WorkerTask) -> WorkerResult:
        """
        Create a conversational Discord update.

        Args:
            task: Task containing stage and context information

        Returns:
            WorkerResult with Discord message details
        """
        logger.info(f"Narrator: Creating update for task {task.task_id}")

        try:
            stage = task.context.get("stage", "unknown")
            message = task.context.get("message", "")

            # TODO: Use agent to craft better narrative
            # For now, use the provided message
            
            # Post to Discord
            # TODO: Get actual thread ID and post to thread
            logger.info(f"[{stage}] {message}")

            return WorkerResult(
                task_id=task.task_id,
                success=True,
                data={"message_posted": True, "thread_id": "mock-thread-id"},
            )

        except Exception as e:
            logger.error(f"Narration failed: {e}", exc_info=True)
            return WorkerResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
            )
