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

from strands import Agent
from strands.tools.mcp import MCPClient

from cluster_monitor.mcp_utils import (
    create_discord_mcp_client,
    create_kubernetes_mcp_client,
    get_discord_tools,
    get_kubernetes_tools,
    get_memory_tools,
)
from cluster_monitor.models import WorkerResult, WorkerTask
from core_agents.factory import AgentConfig, AgentFactory, ModelConfig
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
        self._k8s_client: MCPClient | None = None

    async def _get_agent(self) -> Agent:
        """Get or create the investigator agent."""
        if self._agent is None:
            # Create Kubernetes MCP client
            self._k8s_client = create_kubernetes_mcp_client()

            # Get tools from MCP client
            with self._k8s_client as client:
                k8s_tools = get_kubernetes_tools(client)

            # Create agent with Kubernetes tools
            self._agent = self.factory.create_agent(
                AgentConfig(
                    name="investigator",
                    description="Diagnostic specialist for Kubernetes issues",
                    system_prompt="""You are an expert Kubernetes diagnostic specialist.

Your role:
1. Investigate issues by checking logs, events, and resource states
2. Identify root causes through systematic analysis
3. Provide clear, detailed findings

Available tools:
- pods_get: Get pod details
- pods_log: Get pod logs
- events_list: List recent events
- resources_get: Get resource details

Be thorough but concise. Focus on actionable insights.""",
                    tools=k8s_tools,
                    model_config=ModelConfig(max_tokens=2048),
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
1. Check pod logs for the affected resources
2. Review recent events in the affected namespaces
3. Identify the likely root cause
4. Assess the severity and impact

Provide your findings in a structured format."""

            # Run the agent
            result = agent(prompt, max_turns=6)
            result_str = str(result)

            # Extract findings from agent response
            findings = {
                "investigation_summary": result_str,
                "root_cause": self._extract_root_cause(result_str),
                "affected_resources": [e["resource_name"] for e in events],
                "severity_assessment": task.context.get("severity", "medium"),
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

    def _extract_root_cause(self, result: str) -> str:
        """Extract root cause from agent response."""
        # Simple extraction - look for common patterns
        lines = result.lower().split("\n")
        for line in lines:
            if "root cause" in line or "cause:" in line:
                return line.strip()
        return "See investigation summary"


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
            # Get memory tools
            memory_tools = get_memory_tools()

            self._agent = self.factory.create_agent(
                AgentConfig(
                    name="memory",
                    description="Memory specialist for learning from past incidents",
                    system_prompt="""You are a memory specialist for Kubernetes incident response.

Your role:
1. Query our knowledge base for similar past incidents
2. Identify patterns and recurring issues
3. Provide historical context for investigations

Available tools:
- query_learnings: Search for similar past incidents
- get_agent_learnings: Get recent learnings for an agent
- store_learning: Store new learnings

Focus on finding actionable patterns and successful resolutions.""",
                    tools=memory_tools,
                    model_config=ModelConfig(max_tokens=1024),
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
            agent = await self._get_agent()
            query = task.context.get("query", "")
            pattern = task.context.get("pattern", "unknown")

            prompt = f"""Search for past incidents similar to:

Pattern: {pattern}
Query: {query}

Find incidents with:
- Similar error patterns
- Successful resolutions
- Confidence > 0.7

Return the most relevant incidents and their resolutions."""

            # Run the agent
            result = agent(prompt, max_turns=3)
            result_str = str(result)

            # Parse learnings from result
            past_incidents = self._parse_learnings(result_str)

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
                data={"learnings": []},  # Return empty list on failure
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
            agent = await self._get_agent()
            investigation = task.context.get("investigation", {})
            pattern = task.context.get("pattern", "unknown")
            success = task.context.get("resolution_success", False)

            prompt = f"""Store this investigation as a learning:

Pattern: {pattern}
Resolution Success: {success}
Investigation: {investigation}

Store this learning with appropriate tags and metadata for future retrieval."""

            # Run the agent
            result = agent(prompt, max_turns=2)

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

    def _parse_learnings(self, result: str) -> list[dict[str, Any]]:
        """Parse learnings from agent response."""
        # Simple parsing - in production, this would be more sophisticated
        learnings = []
        if "no similar incidents" in result.lower() or "no past incidents" in result.lower():
            return learnings

        # If we found incidents, create a summary entry
        if "incident" in result.lower() or "resolution" in result.lower():
            learnings.append(
                {
                    "summary": result[:500],  # First 500 chars
                    "confidence": 0.75,
                }
            )

        return learnings


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
        self._k8s_client: MCPClient | None = None

    async def _get_agent(self) -> Agent:
        """Get or create the remediator agent."""
        if self._agent is None:
            # Create Kubernetes MCP client
            self._k8s_client = create_kubernetes_mcp_client()

            # Get tools from MCP client
            with self._k8s_client as client:
                k8s_tools = get_kubernetes_tools(client)

            self._agent = self.factory.create_agent(
                AgentConfig(
                    name="remediator",
                    description="Remediation specialist for Kubernetes issues",
                    system_prompt="""You are a Kubernetes remediation specialist.

Your role:
1. Plan safe remediation actions based on diagnostic findings
2. Execute remediation using available tools
3. Verify that the fix worked

Available tools:
- pods_delete: Delete a pod (triggers restart)
- deployments_scale: Scale a deployment
- resources_create: Create a resource
- resources_delete: Delete a resource

Always:
- Explain what you're about to do and why
- Consider the impact of your actions
- Verify the outcome

Be cautious with destructive operations.""",
                    tools=k8s_tools,
                    model_config=ModelConfig(max_tokens=1536),
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
            agent = await self._get_agent()
            findings = task.context.get("findings", {})
            known_remediation = task.context.get("known_remediation")
            pattern = task.context.get("pattern", "unknown")

            prompt = f"""Plan a remediation for this issue:

Pattern: {pattern}
Findings: {findings}
Known Remediation: {known_remediation or "None"}

Provide:
1. Recommended action
2. Reason for this action
3. Risk level (low/medium/high)
4. Whether approval is needed

Be specific about what you'll do."""

            # Run the agent
            result = agent(prompt, max_turns=3)
            result_str = str(result)

            # Parse plan from result
            plan = {
                "action": self._extract_action(result_str),
                "reason": result_str[:300],  # First 300 chars as reason
                "risk_level": self._extract_risk_level(result_str),
                "requires_approval": "high" in result_str.lower() and "risk" in result_str.lower(),
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
            agent = await self._get_agent()
            action = task.context.get("action", "")
            reason = task.context.get("reason", "")

            prompt = f"""Execute this remediation:

Action: {action}
Reason: {reason}

Use the available tools to execute the action and report the result."""

            # Run the agent
            result = agent(prompt, max_turns=4)
            result_str = str(result)

            # Determine success from result
            success = any(word in result_str.lower() for word in ["success", "completed", "fixed"])

            return WorkerResult(
                task_id=task.task_id,
                success=success,
                data={"action_taken": action, "result": result_str[:500]},
            )

        except Exception as e:
            logger.error(f"Remediation execution failed: {e}", exc_info=True)
            return WorkerResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
            )

    def _extract_action(self, result: str) -> str:
        """Extract action from agent response."""
        lines = result.split("\n")
        for line in lines:
            if "action:" in line.lower() or "recommend" in line.lower():
                return line.strip()
        return "Restart affected pods"

    def _extract_risk_level(self, result: str) -> str:
        """Extract risk level from agent response."""
        result_lower = result.lower()
        if "high risk" in result_lower:
            return "high"
        elif "medium risk" in result_lower:
            return "medium"
        else:
            return "low"


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
        self._discord_client: MCPClient | None = None

    async def _get_agent(self) -> Agent:
        """Get or create the narrator agent."""
        if self._agent is None:
            # Create Discord MCP client
            self._discord_client = create_discord_mcp_client()

            # Get tools from MCP client
            with self._discord_client as client:
                discord_tools = get_discord_tools(client)

            self._agent = self.factory.create_agent(
                AgentConfig(
                    name="narrator",
                    description="Communications specialist for conversational updates",
                    system_prompt="""You are a skilled technical communicator for Kubernetes incident response.

Your role:
1. Transform technical findings into clear, conversational updates
2. Post updates to Discord at key investigation milestones
3. Maintain a coherent narrative throughout the investigation

IMPORTANT: Always post to the "cluster-monitor" channel.

Communication style:
- Write like an experienced engineer talking to a colleague
- Be transparent about your process and reasoning
- Use natural language, not templates
- Be confident but acknowledge uncertainty when it exists
- Use technical terms when appropriate, but explain complex concepts

Available tools:
- send_message_to_channel_name: Send a message to Discord (use channel_name="cluster-monitor")

Always post updates that are:
- Clear and concise
- Informative and actionable
- Conversational and engaging""",
                    tools=discord_tools,
                    model_config=ModelConfig(max_tokens=1024),
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
            context_data = task.context.get("data", {})

            # If we have an agent, use it to craft a better message
            if self._agent is None:
                agent = await self._get_agent()
            else:
                agent = self._agent

            prompt = f"""Create a Discord update for this investigation stage:

Stage: {stage}
Base Message: {message}
Context: {context_data}

Craft a clear, conversational update that explains what's happening.
Use the messages_send tool to post it to Discord."""

            # Run the agent
            result = agent(prompt, max_turns=2)
            result_str = str(result)

            # Check if message was posted
            success = "sent" in result_str.lower() or "posted" in result_str.lower()

            return WorkerResult(
                task_id=task.task_id,
                success=success,
                data={"message_posted": success, "thread_id": "discord-thread"},
            )

        except Exception as e:
            logger.error(f"Narration failed: {e}", exc_info=True)
            # Fallback: try to post via direct integration
            try:
                await send_discord_message(
                    content=task.context.get("message", "Investigation update"),
                    agent_name="cluster-monitor",
                )
                return WorkerResult(
                    task_id=task.task_id,
                    success=True,
                    data={"message_posted": True, "fallback": True},
                )
            except Exception as fallback_error:
                logger.error(f"Fallback narration also failed: {fallback_error}")
                return WorkerResult(
                    task_id=task.task_id,
                    success=False,
                    error=str(e),
                )
