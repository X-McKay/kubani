"""
Worker Agents - Specialized agents for investigation tasks.

Workers are lightweight agents with specific responsibilities:
- Investigator: Runs diagnostic skills and gathers information
- Memory: Queries and stores learnings
- Remediator: Plans and executes remediation actions
- Narrator: Crafts conversational Discord updates
"""

import json
import logging
from typing import Any

from strands import Agent

from cluster_monitor.mcp_utils import (
    create_kubernetes_mcp_client,
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

    SYSTEM_PROMPT = """You are an expert Kubernetes diagnostic specialist.

Your role:
1. Investigate issues by checking logs, events, and resource states
2. Identify root causes through systematic analysis
3. Provide clear, detailed findings

Available tools:
- pods_get: Get pod details
- pods_log: Get pod logs
- events_list: List recent events
- resources_get: Get resource details

Be thorough but concise. Focus on actionable insights."""

    def __init__(self, factory: AgentFactory | None = None):
        self.factory = factory or AgentFactory()

    async def investigate(self, task: WorkerTask) -> WorkerResult:
        """
        Investigate a Kubernetes issue.

        The MCP client context must remain open during agent execution,
        so we create both the client and agent fresh for each investigation.

        Args:
            task: Task containing events and pattern information

        Returns:
            WorkerResult with diagnostic findings
        """
        logger.info(f"Investigator: Processing task {task.task_id}")

        try:
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

            # Create MCP client and run agent WITHIN the context
            k8s_client = create_kubernetes_mcp_client()

            with k8s_client as client:
                # Get tools while context is open
                k8s_tools = get_kubernetes_tools(client)

                if not k8s_tools:
                    logger.warning("No Kubernetes tools available, investigation limited")

                # Create agent with tools
                agent = self.factory.create_agent(
                    AgentConfig(
                        name="investigator",
                        description="Diagnostic specialist for Kubernetes issues",
                        system_prompt=self.SYSTEM_PROMPT,
                        tools=k8s_tools,
                        model_config=ModelConfig(max_tokens=2048),
                    )
                )

                # Run the agent WITHIN the MCP client context
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

    Uses approved action tools that request human approval before
    executing any destructive operations.
    """

    SYSTEM_PROMPT = """You are a Kubernetes remediation specialist.

Your role:
1. Plan safe remediation actions based on diagnostic findings
2. Execute remediation using APPROVED action tools
3. Verify that the fix worked

IMPORTANT - APPROVED ACTIONS:
All destructive actions require human approval via Discord.
Use these tools which handle the approval flow automatically:

- request_pod_deletion: Delete a pod (requests approval first)
- request_deployment_scale: Scale a deployment (requests approval first)
- request_rollout_restart: Restart a deployment/statefulset gracefully
- escalate_to_human: Escalate when automated remediation fails

Read-only tools (no approval needed):
- pods_get, pods_log: Check pod status
- events_list: View events
- resources_get: View resource details

WORKFLOW:
1. Review the findings and determine the appropriate action
2. Use an approved action tool (it will request approval via Discord)
3. The tool returns the result after human approves/rejects
4. Report the outcome

Always be cautious and prefer escalating to humans if uncertain."""

    def __init__(self, factory: AgentFactory | None = None):
        self.factory = factory or AgentFactory()

    def _run_with_approved_tools(self, prompt: str, max_turns: int = 3) -> str:
        """
        Run an agent with approved action tools.

        Uses read-only K8s MCP tools for investigation and
        approved tools for any destructive operations.
        """
        from cluster_monitor.approved_tools import create_approved_tools

        k8s_client = create_kubernetes_mcp_client()

        with k8s_client as client:
            k8s_tools = get_kubernetes_tools(client)

            # Filter to read-only tools
            read_only_tools = [
                t
                for t in k8s_tools
                if t.name
                in [
                    "pods_get",
                    "pods_log",
                    "pods_list",
                    "events_list",
                    "resources_get",
                    "resources_list",
                ]
            ]

            # Add approved action tools
            approved_tools = create_approved_tools()

            agent = self.factory.create_agent(
                AgentConfig(
                    name="remediator",
                    description="Remediation specialist for Kubernetes issues",
                    system_prompt=self.SYSTEM_PROMPT,
                    tools=read_only_tools + approved_tools,
                    model_config=ModelConfig(max_tokens=1536),
                )
            )

            # Run agent WITHIN the MCP client context
            result = agent(prompt, max_turns=max_turns)
            return str(result)

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

            result_str = self._run_with_approved_tools(prompt, max_turns=3)

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
            action = task.context.get("action", "")
            reason = task.context.get("reason", "")

            prompt = f"""Execute this remediation:

Action: {action}
Reason: {reason}

Use the available tools to execute the action and report the result."""

            result_str = self._run_with_approved_tools(prompt, max_turns=4)

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
    Narrator Worker - Crafts conversational Discord updates using LLM.

    Uses the LLM to transform structured investigation data into natural
    language narratives, then posts directly via Discord integration.
    """

    def __init__(self, factory: AgentFactory | None = None):
        self.factory = factory or AgentFactory()
        self._agent: Agent | None = None

    async def _get_agent(self) -> Agent:
        """Get or create the narrator agent (no tools - just for text generation)."""
        if self._agent is None:
            # Create agent WITHOUT tools - we just need LLM for text generation
            # Discord posting is done directly via send_discord_message
            self._agent = self.factory.create_agent(
                AgentConfig(
                    name="narrator",
                    description="Technical communicator for Kubernetes incident response",
                    system_prompt="""You are a skilled technical communicator for Kubernetes incident response.

Your role is to write clear, informative Discord messages about Kubernetes investigations.

Communication style:
- Write like an experienced engineer talking to a colleague
- Be transparent about the investigation process and findings
- Use natural language, not templates or generic phrases
- Be specific: include actual pod names, namespaces, error messages, and metrics
- Be concise but complete - every word should add value
- Use markdown formatting (bold for emphasis, code blocks for technical details)

CRITICAL: Your output is the EXACT message that will be posted to Discord.
- Do NOT include meta-commentary like "Here's a message:" or "I'll write:"
- Do NOT use placeholder text - include the ACTUAL data provided
- Start directly with the content
- Keep messages under 2000 characters

Example good output for an initial analysis:
🔍 **Detected CrashLoopBackOff in ai-agents namespace**

Affected pod: `news-monitor-7d4f8b9c5-x2k9m`
Pattern: Pod has restarted 5 times in the last 10 minutes
Last error: `OOMKilled - container exceeded memory limit`

Investigating root cause...""",
                    tools=[],  # No tools - just text generation
                    model_config=ModelConfig(max_tokens=1024),
                )
            )
        return self._agent

    async def narrate(self, task: WorkerTask) -> WorkerResult:
        """
        Generate and post a Discord update using LLM.

        Args:
            task: Task containing stage and context information

        Returns:
            WorkerResult with Discord message details
        """
        logger.info(f"Narrator: Creating update for task {task.task_id}")

        try:
            stage = task.context.get("stage", "unknown")

            # Extract all relevant context data
            context_data = {k: v for k, v in task.context.items() if k not in ("stage", "message")}

            # Get the narrator agent
            agent = await self._get_agent()

            # Build a prompt that gives the LLM all the context
            prompt = self._build_generation_prompt(stage, context_data)

            # Generate the message content using LLM
            logger.info(f"Narrator: Generating message for stage={stage}")
            result = agent(prompt, max_turns=1)  # Single turn - just generate text
            message_content = str(result).strip()

            # Validate we got real content, not placeholder
            if not message_content or len(message_content) < 20:
                logger.error(
                    f"Narrator: LLM returned empty or too-short message: {message_content!r}"
                )
                return WorkerResult(
                    task_id=task.task_id,
                    success=False,
                    error="LLM generated empty or insufficient content",
                )

            # Check for placeholder patterns that indicate failure
            placeholder_patterns = [
                "here's a message",
                "here is a message",
                "i'll write",
                "i will write",
                "let me write",
                "[insert",
                "{insert",
                "context keys:",
                "investigation update:",
            ]
            message_lower = message_content.lower()
            for pattern in placeholder_patterns:
                if pattern in message_lower:
                    logger.error(
                        f"Narrator: LLM returned placeholder content: {message_content[:100]!r}"
                    )
                    return WorkerResult(
                        task_id=task.task_id,
                        success=False,
                        error=f"LLM generated placeholder content (found: {pattern})",
                    )

            # Post the LLM-generated content directly to Discord
            logger.info(f"Narrator: Posting message ({len(message_content)} chars)")
            await send_discord_message(
                content=message_content,
                agent_name="cluster-monitor",
            )

            return WorkerResult(
                task_id=task.task_id,
                success=True,
                data={"message_posted": True, "message_length": len(message_content)},
            )

        except Exception as e:
            logger.error(f"Narration failed: {e}", exc_info=True)
            # Do NOT post fallback/placeholder messages - just fail
            return WorkerResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
            )

    def _build_generation_prompt(self, stage: str, context_data: dict) -> str:
        """Build a prompt for the LLM to generate the Discord message."""
        # Format the context data nicely
        context_json = json.dumps(context_data, indent=2, default=str)

        # Stage-specific instructions
        stage_guidance = {
            "initial_analysis": """Write a message announcing that issues were detected.
Include: number of issues, affected namespace(s), pod names, the pattern type (e.g. CrashLoopBackOff, OOMKilled), and that investigation is starting.""",
            "memory_findings": """Write a message about what was found in historical memory.
Include: whether similar incidents were found, what patterns matched, and any relevant past resolutions.""",
            "investigation_findings": """Write a message summarizing the investigation findings.
Include: root cause analysis, specific error messages found, resource metrics, and key observations.""",
            "remediation_plan": """Write a message about the planned remediation.
Include: what action will be taken, why this approach was chosen, and risk level.""",
            "action_result": """Write a message about the remediation result.
Include: whether it succeeded, what was done, and any relevant output.""",
            "verification": """Write a message about verification of the fix.
Include: whether the issue is resolved, current status of affected resources.""",
            "final_summary": """Write a final summary message for the investigation.
Include: what was detected, what was done, and the final outcome.""",
        }

        guidance = stage_guidance.get(
            stage,
            "Write a clear status update message with the relevant details from the data.",
        )

        return f"""Write a Discord message for this Kubernetes investigation update.

**Stage:** {stage}
**Guidance:** {guidance}

**Investigation Data:**
```json
{context_json}
```

Write the Discord message now. Remember:
- Start directly with the content (no preamble)
- Include ACTUAL data from above (pod names, namespaces, errors, etc.)
- Use markdown formatting
- Keep it under 2000 characters"""
