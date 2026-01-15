"""
Cluster Swarm - Swarm Intelligence implementation for Kubernetes monitoring.

The swarm consists of specialized agents that collaborate dynamically:
- Triage Agent: Entry point, analyzes and routes to specialists
- Investigator Agent: Diagnostic specialist
- Memory Agent: Learning and pattern specialist
- Remediation Agent: Fix specialist
- Communications Agent: Discord and user interaction specialist

Context Optimization:
- Tool results are filtered to prevent context overflow (see tool_limits.py)
- Uses InvestigationState for compact state passing between agents
- Simple agents (Triage, Memory) use the fast 0.6B model
- Communications uses main model for reliable Discord tool calling
- SlidingWindowConversationManager limits context to 25 messages per agent
- per_turn=True applies context management proactively during execution
"""

import asyncio
import logging
import os
from typing import Any

from strands import Agent

from cluster_swarm.mcp_utils import (
    create_discord_mcp_client,
    create_kubernetes_mcp_client,
    get_discord_tools,
    get_kubernetes_tools,
    get_memory_tools,
)
from cluster_swarm.models import CorrelatedIssue, SwarmContext
from core_agents.events import Event, EventBus, EventType, get_event_bus
from core_agents.factory import AgentConfig, AgentFactory, ModelConfig, SwarmConfig

logger = logging.getLogger(__name__)

# =============================================================================
# Model Configuration
# =============================================================================

# Fast model for simple agents (Triage, Memory)
FAST_MODEL_URL = os.getenv("FAST_MODEL_URL", "http://fast-model-api.vllm.svc.cluster.local:8000/v1")
FAST_MODEL_NAME = os.getenv("FAST_MODEL_NAME", "Qwen/Qwen3-0.6B")

# Main model for complex reasoning (Investigator, Remediation, Communications)
# Uses default from config_unified.py

# =============================================================================
# Context Window Management
# =============================================================================

# ConversationManager configuration for preventing context overflow
# - window_size: Max messages to keep (lower = more aggressive pruning)
# - per_turn: Apply management proactively during execution (True = every call)
# - should_truncate_results: Truncate large tool results before removing messages
CONVERSATION_WINDOW_SIZE = int(os.getenv("SWARM_CONVERSATION_WINDOW_SIZE", "25"))
CONVERSATION_PER_TURN = True  # Proactive management for tool-heavy operations


def create_conversation_manager() -> "SlidingWindowConversationManager":
    """Create a conversation manager for context window management."""
    from strands.agent.conversation_manager import SlidingWindowConversationManager

    return SlidingWindowConversationManager(
        window_size=CONVERSATION_WINDOW_SIZE,
        per_turn=CONVERSATION_PER_TURN,
        should_truncate_results=True,
    )


# =============================================================================
# Swarm Agent Definitions
# =============================================================================


def create_triage_agent(factory: AgentFactory, k8s_tools: list, discord_tools: list) -> Agent:
    """
    Create the Triage Agent - entry point for the swarm.

    The Triage Agent:
    - Receives correlated issues
    - Performs initial analysis
    - Routes to appropriate specialists
    Uses the fast 0.6B model for quick routing decisions.
    """
    return factory.create_agent(
        AgentConfig(
            name="triage",
            description="Triage specialist - analyzes issues and routes to specialists",
            system_prompt="""You are the triage specialist for Kubernetes incident response.

Your role:
1. Receive correlated issues from the monitoring system
2. Perform initial analysis to understand the scope and severity
3. Route to appropriate specialists based on the issue type

When you receive an issue:
- Assess the pattern (timeout, OOM, network, etc.)
- Determine which specialist should handle it
- Hand off with compact context

Available specialists:
- Investigator: For diagnostic work (checking logs, events, resources)
- Memory: For querying past incidents and patterns
- Remediation: For planning and executing fixes
- Communications: For posting updates to Discord

You have access to basic Kubernetes tools for initial assessment.

IMPORTANT WORKFLOW:
1. FIRST: Hand off to Communications to post initial detection to Discord
2. THEN: Hand off to Investigator for detailed diagnostics

STATE PASSING:
When handing off to another agent, pass compact context:
- correlation_id: The issue correlation ID
- pattern_type: The detected pattern (timeout, crash_loop, oom, etc.)
- severity: The severity level
- affected_pods: List of affected pod names (max 5)

Keep handoff messages brief - include only essential information.""",
            tools=k8s_tools[:5],  # Limited tools for triage
            model_config=ModelConfig(
                base_url=FAST_MODEL_URL,
                model_id=FAST_MODEL_NAME,
                max_tokens=512,
            ),
            conversation_manager=create_conversation_manager(),
        )
    )


def create_investigator_agent(factory: AgentFactory, k8s_tools: list) -> Agent:
    """
    Create the Investigator Agent - diagnostic specialist.

    The Investigator Agent:
    - Runs detailed diagnostics
    - Checks logs, events, and resource states
    - Identifies root causes
    - Hands off to Memory or Remediation
    Uses the main 14B model for complex diagnostic reasoning.
    """
    return factory.create_agent(
        AgentConfig(
            name="investigator",
            description="Diagnostic specialist for Kubernetes issues",
            system_prompt="""You are an expert Kubernetes diagnostic specialist.

Your role:
1. Perform detailed investigation of issues
2. Check pod logs, events, and resource states
3. Identify root causes through systematic analysis
4. Provide clear, compact findings

Available tools:
- pods_get: Get pod details
- pods_log: Get pod logs (limited to 50 lines)
- events_list: List recent events (limited to 20)
- resources_get: Get resource details
- resources_list: List resources

Investigation approach:
1. Check the affected pods/resources
2. Review recent logs (last 50 lines)
3. Look at events in the namespace
4. Identify patterns and root cause

After investigation, ALWAYS do these steps in order:
1. FIRST: Hand off to Communications agent to post your findings to Discord
2. THEN: Hand off to Memory agent to check for similar past incidents
3. FINALLY: Hand off to Remediation if a fix is needed

STATE PASSING - CRITICAL:
When handing off, pass ONLY compact structured state:
- root_cause: Single sentence explaining the issue
- key_findings: Max 3 bullet points
- error_snippets: Max 2 relevant log lines (truncated)
- remediation_needed: true/false

DO NOT include raw tool output in handoff messages. Summarize findings into
the structured format above. This keeps context size manageable.

Example handoff to Communications:
"Post investigation findings: OOM issue detected"
Context: {
  "correlation_id": "abc123",
  "root_cause": "Container exceeded memory limit of 256Mi",
  "key_findings": ["Memory at 280Mi before kill", "No memory requests set"],
  "error_snippets": ["OOMKilled: container exceeded limit"],
  "remediation_needed": true
}""",
            tools=k8s_tools,
            model_config=ModelConfig(max_tokens=2048),
            conversation_manager=create_conversation_manager(),
        )
    )


def create_memory_agent(factory: AgentFactory, memory_tools: list) -> Agent:
    """
    Create the Memory Agent - learning and pattern specialist.

    The Memory Agent:
    - Queries for similar past incidents
    - Identifies patterns and recurring issues
    - Stores new learnings
    - Provides historical context
    Uses the fast 0.6B model for pattern matching queries.
    """
    return factory.create_agent(
        AgentConfig(
            name="memory",
            description="Memory specialist for learning from past incidents",
            system_prompt="""You are the memory specialist for Kubernetes incident response.

Your role:
1. Query our knowledge base for similar past incidents
2. Identify patterns and recurring issues
3. Provide historical context for investigations
4. Store new learnings from resolved incidents

Available tools:
- query_learnings: Search for similar past incidents
- get_agent_learnings: Get recent learnings for an agent
- store_learning: Store new learnings

When querying:
- Use the issue pattern and key symptoms
- Look for incidents with confidence > 0.7
- Focus on successful resolutions

After finding relevant history:
- Hand off to Remediation with the historical context
- Or hand off to Communications to share findings

When storing learnings:
- Include the pattern, investigation, and resolution
- Tag appropriately for future retrieval

STATE PASSING:
Receive structured context from other agents. Pass compact findings:
- past_incidents: List of relevant past incidents (max 3)
- suggested_fix: Brief suggestion based on history (if applicable)
- confidence: How confident the match is (0.0-1.0)

Keep responses brief and focused.""",
            tools=memory_tools,
            model_config=ModelConfig(
                base_url=FAST_MODEL_URL,
                model_id=FAST_MODEL_NAME,
                max_tokens=512,
            ),
            conversation_manager=create_conversation_manager(),
        )
    )


def create_remediation_agent(factory: AgentFactory, k8s_tools: list) -> Agent:
    """
    Create the Remediation Agent - fix specialist.

    The Remediation Agent:
    - Plans remediation based on findings
    - Executes remediation actions
    - Verifies results
    Uses the main 14B model for critical fix decisions.
    """
    return factory.create_agent(
        AgentConfig(
            name="remediation",
            description="Remediation specialist for Kubernetes issues",
            system_prompt="""You are a Kubernetes remediation specialist.

Your role:
1. Plan safe remediation actions based on diagnostic findings
2. Execute remediation using available tools
3. Verify that the fix worked

Available tools:
- pods_delete: Delete a pod (triggers restart)
- resources_scale: Scale a deployment
- resources_create: Create a resource
- resources_delete: Delete a resource

Remediation approach:
1. Explain what you're about to do and why
2. Consider the impact of your actions
3. Execute the remediation
4. Verify the outcome

Risk assessment:
- Low risk: Pod restarts, scaling up
- Medium risk: Scaling down, resource modifications
- High risk: Deletions, cluster-wide changes

IMPORTANT WORKFLOW:
1. BEFORE taking action: Hand off to Communications to post your remediation plan
2. Execute the remediation
3. AFTER action: Hand off to Communications to post the result (success or failure)

STATE PASSING:
Receive structured context with root_cause and key_findings. Pass back:
- action_taken: What remediation was performed
- result: "success" or "failure"
- verification: Brief verification status

Keep context compact - don't repeat the full investigation.""",
            tools=k8s_tools,
            model_config=ModelConfig(max_tokens=1536),
            conversation_manager=create_conversation_manager(),
        )
    )


def create_communications_agent(factory: AgentFactory, discord_tools: list) -> Agent:
    """
    Create the Communications Agent - Discord and user interaction specialist.

    The Communications Agent:
    - Posts updates to Discord
    - Maintains narrative coherence
    - Keeps stakeholders informed
    Uses the main 14B model for reliable Discord tool calling.
    """
    return factory.create_agent(
        AgentConfig(
            name="communications",
            description="Communications specialist for stakeholder updates",
            system_prompt="""You are a skilled technical communicator for Kubernetes incident response.

Your role is to transform technical findings into well-formatted Discord messages.

CRITICAL INSTRUCTIONS:
1. Extract key details from the structured context passed to you
2. Create a NEW formatted Discord message (not the raw handoff)
3. MUST call send_message_to_channel_name tool with channel_name="cluster-swarm"

FORMATTING:
- Start with emoji: 🔍 detection, 📌 plan, ✅ success, ⚠️ warning
- Use **bold** for headers
- Use `backticks` for pod names, namespaces
- Keep under 500 characters

TEMPLATES:

Detection:
🔍 **Issue Detected: {pattern_type}**
**Affected:** `{pod}` in `{namespace}`
**Severity:** {severity}
Investigating...

Investigation:
🔍 **Investigation: {root_cause}**
**Findings:**
- {finding1}
- {finding2}
**Next:** {next_step}

Remediation:
📌 **Remediation: {action}**
**Risk:** {risk_level}
**Result:** {result}

STATE PASSING:
You receive structured context with:
- correlation_id, pattern_type, severity
- root_cause, key_findings, error_snippets
- action_taken, result

Use these fields to fill the templates above.

IMPORTANT: Always use the send_message_to_channel_name tool to post messages.""",
            tools=discord_tools,
            model_config=ModelConfig(max_tokens=1024),
            conversation_manager=create_conversation_manager(),
        )
    )


# =============================================================================
# Cluster Swarm
# =============================================================================


class ClusterSwarm:
    """
    Cluster Swarm - manages the swarm of agents for Kubernetes monitoring.

    The swarm operates through dynamic agent collaboration:
    1. Triage receives the issue and performs initial analysis
    2. Agents hand off to each other based on what they discover
    3. Communications agent posts updates throughout
    4. Investigation concludes when issue is resolved or escalated
    """

    def __init__(self, factory: AgentFactory | None = None):
        self.factory = factory or AgentFactory()
        self._event_bus: EventBus | None = None

    async def investigate(self, correlated_issue: CorrelatedIssue) -> dict[str, Any]:
        """
        Investigate a correlated issue using the swarm.

        MCP clients must stay open during swarm execution, so we create
        the swarm fresh for each investigation inside the client contexts.

        Args:
            correlated_issue: The correlated issue to investigate

        Returns:
            Investigation result dictionary
        """
        logger.info(
            f"Starting swarm investigation for correlation {correlated_issue.correlation_id}"
        )

        # Create swarm context
        context = SwarmContext(
            correlation_id=correlated_issue.correlation_id,
            events=correlated_issue.events,
            pattern_type=correlated_issue.pattern_type,
            severity=correlated_issue.severity,
        )

        # Build initial prompt for triage agent
        event_descriptions = "\n".join(
            [
                f"- {e.resource_kind}/{e.resource_name} in {e.namespace}: {e.reason} - {e.message}"
                for e in correlated_issue.events
            ]
        )

        initial_prompt = f"""I've detected a correlated Kubernetes issue that needs investigation:

Pattern: {correlated_issue.pattern_type}
Severity: {correlated_issue.severity.value}
Affected Resources: {len(correlated_issue.events)} resources
Namespaces: {", ".join(correlated_issue.affected_namespaces)}

Events:
{event_descriptions}

Please:
1. Perform initial triage and analysis
2. Route to appropriate specialists for detailed investigation
3. Work with the team to identify root cause and remediation
4. Keep stakeholders informed via Communications agent
5. Conclude with a summary of findings and actions taken

Let's investigate this issue together."""

        try:
            # Create MCP clients - must stay open during swarm execution
            k8s_client = create_kubernetes_mcp_client()
            discord_client = create_discord_mcp_client()

            # Run swarm inside MCP client contexts so tools remain connected
            # MCPClient uses sync context manager, but we can await inside
            with k8s_client as k8s_ctx, discord_client as discord_ctx:
                # Get tools from active MCP clients
                k8s_tools = get_kubernetes_tools(k8s_ctx)
                discord_tools = get_discord_tools(discord_ctx)
                memory_tools = get_memory_tools()

                # Create agents with active tool connections
                triage = create_triage_agent(self.factory, k8s_tools, discord_tools)
                investigator = create_investigator_agent(self.factory, k8s_tools)
                memory = create_memory_agent(self.factory, memory_tools)
                remediation = create_remediation_agent(self.factory, k8s_tools)
                communications = create_communications_agent(self.factory, discord_tools)

                # Create swarm
                swarm = self.factory.create_swarm(
                    SwarmConfig(
                        agents=[triage, investigator, memory, remediation, communications],
                        entry_point=triage,
                        max_handoffs=15,
                        max_iterations=25,
                        execution_timeout=600.0,
                        node_timeout=120.0,
                    )
                )
                logger.info("Created swarm with 5 agents")

                # Run the swarm (invoke_async is the correct method)
                result = await swarm.invoke_async(initial_prompt)

            logger.info(f"Swarm investigation completed for {correlated_issue.correlation_id}")

            return {
                "correlation_id": correlated_issue.correlation_id,
                "investigation_complete": True,
                "result": str(result),
                "context": context.model_dump(),
            }

        except Exception as e:
            logger.error(f"Swarm investigation failed: {e}", exc_info=True)
            return {
                "correlation_id": correlated_issue.correlation_id,
                "investigation_complete": False,
                "error": str(e),
                "context": context.model_dump(),
            }

    async def process_investigation_request(self, event: Event) -> None:
        """Process an INVESTIGATION_REQUESTED event."""
        try:
            correlated_issue = CorrelatedIssue(**event.payload)
            result = await self.investigate(correlated_issue)

            # Publish completion event
            if self._event_bus is None:
                self._event_bus = await get_event_bus()

            event_type = (
                EventType.K8S_REMEDIATION_COMPLETED
                if result.get("investigation_complete")
                else EventType.K8S_REMEDIATION_FAILED
            )

            await self._event_bus.publish(
                event_type=event_type,
                payload=result,
                source="cluster-swarm",
            )

        except Exception as e:
            logger.error(f"Failed to process investigation request: {e}", exc_info=True)

    async def run(self) -> None:
        """
        Run the swarm service.

        Subscribes to INVESTIGATION_REQUESTED events and conducts investigations.
        """
        logger.info("Starting Cluster Swarm service")

        if self._event_bus is None:
            self._event_bus = await get_event_bus()

        async for event in self._event_bus.subscribe(
            EventType.K8S_INVESTIGATION_REQUESTED,
            consumer_group="cluster-swarm",
            consumer_name="cluster-swarm-1",
        ):
            try:
                # Process each investigation in a separate task
                asyncio.create_task(self.process_investigation_request(event))
            except Exception as e:
                logger.error(f"Error processing investigation request: {e}", exc_info=True)


async def main():
    """Main entry point for the cluster swarm service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    swarm = ClusterSwarm()
    await swarm.run()


if __name__ == "__main__":
    asyncio.run(main())
