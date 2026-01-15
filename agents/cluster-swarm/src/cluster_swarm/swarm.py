"""
Cluster Swarm - Swarm Intelligence implementation for Kubernetes monitoring.

The swarm consists of specialized agents that collaborate dynamically:
- Triage Agent: Entry point, analyzes and routes to specialists
- Investigator Agent: Diagnostic specialist
- Memory Agent: Learning and pattern specialist
- Remediation Agent: Fix specialist
- Communications Agent: Discord and user interaction specialist
"""

import asyncio
import logging
from typing import Any

from strands import Agent
from strands.multiagent import Swarm
from strands.tools.mcp import MCPClient

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
# Swarm Agent Definitions
# =============================================================================


def create_triage_agent(factory: AgentFactory, k8s_tools: list, discord_tools: list) -> Agent:
    """
    Create the Triage Agent - entry point for the swarm.

    The Triage Agent:
    - Receives correlated issues
    - Performs initial analysis
    - Routes to appropriate specialists
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
- Hand off with clear context

Available specialists:
- Investigator: For diagnostic work (checking logs, events, resources)
- Memory: For querying past incidents and patterns
- Remediation: For planning and executing fixes
- Communications: For posting updates to Discord

You have access to basic Kubernetes tools for initial assessment.
After initial analysis, hand off to the Investigator for detailed diagnostics.

Use natural, conversational language when handing off.""",
            tools=k8s_tools[:5],  # Limited tools for triage
            model_config=ModelConfig(max_tokens=1024),
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
4. Provide clear findings

Available tools:
- pods_get: Get pod details
- pods_log: Get pod logs (use tail parameter to limit output)
- events_list: List recent events
- resources_get: Get resource details
- resources_list: List resources

Investigation approach:
1. Check the affected pods/resources
2. Review recent logs (last 50 lines)
3. Look at events in the namespace
4. Identify patterns and root cause

After investigation:
- Hand off to Memory agent to check for similar past incidents
- Or hand off to Remediation if you've identified a clear fix
- Or hand off to Communications to post findings

Be thorough but concise. Focus on actionable insights.
Use conversational language when explaining findings.""",
            tools=k8s_tools,
            model_config=ModelConfig(max_tokens=2048),
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

Use conversational language when sharing findings.""",
            tools=memory_tools,
            model_config=ModelConfig(max_tokens=1024),
        )
    )


def create_remediation_agent(factory: AgentFactory, k8s_tools: list) -> Agent:
    """
    Create the Remediation Agent - fix specialist.

    The Remediation Agent:
    - Plans remediation based on findings
    - Executes remediation actions
    - Verifies results
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
- deployments_scale: Scale a deployment
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

After remediation:
- Hand off to Communications to post the action and result
- Or hand off to Investigator to verify the fix

Be cautious with destructive operations.
Always explain your reasoning.
Use conversational language.""",
            tools=k8s_tools,
            model_config=ModelConfig(max_tokens=1536),
        )
    )


def create_communications_agent(factory: AgentFactory, discord_tools: list) -> Agent:
    """
    Create the Communications Agent - Discord and user interaction specialist.

    The Communications Agent:
    - Posts updates to Discord
    - Maintains narrative coherence
    - Keeps stakeholders informed
    """
    return factory.create_agent(
        AgentConfig(
            name="communications",
            description="Communications specialist for stakeholder updates",
            system_prompt="""You are a skilled technical communicator for Kubernetes incident response.

Your role:
1. Transform technical findings into clear, conversational updates
2. Post updates to Discord at key investigation milestones
3. Maintain a coherent narrative throughout the investigation

IMPORTANT: Always post to the "cluster-swarm" channel.

Communication style:
- Write like an experienced engineer talking to a colleague
- Be transparent about your process and reasoning
- Use natural language, not templates
- Be confident but acknowledge uncertainty when it exists
- Use technical terms when appropriate, but explain complex concepts

Available tools:
- send_message_to_channel_name: Send a message to Discord (use channel_name="cluster-swarm")

When to post updates:
- Initial issue detection and analysis
- Key investigation findings
- Before taking remediation actions
- After remediation (success or failure)
- Final summary

After posting:
- Hand back to the agent that requested the update
- Or conclude if this is the final summary

Always post updates that are:
- Clear and concise
- Informative and actionable
- Conversational and engaging""",
            tools=discord_tools,
            model_config=ModelConfig(max_tokens=1024),
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
        self._swarm: Swarm | None = None
        self._k8s_client: MCPClient | None = None
        self._discord_client: MCPClient | None = None
        self._event_bus: EventBus | None = None

    def _create_swarm(self) -> Swarm:
        """Create the swarm with all agents."""
        # Create MCP clients
        self._k8s_client = create_kubernetes_mcp_client()
        self._discord_client = create_discord_mcp_client()

        # Get tools from MCP clients
        with self._k8s_client as k8s_client:
            k8s_tools = get_kubernetes_tools(k8s_client)

        with self._discord_client as discord_client:
            discord_tools = get_discord_tools(discord_client)

        # Get memory tools
        memory_tools = get_memory_tools()

        # Create agents
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
                max_handoffs=15,  # Allow more handoffs for dynamic collaboration
                max_iterations=25,
                execution_timeout=600.0,  # 10 minutes
                node_timeout=120.0,
            )
        )

        logger.info("Created swarm with 5 agents")
        return swarm

    async def investigate(self, correlated_issue: CorrelatedIssue) -> dict[str, Any]:
        """
        Investigate a correlated issue using the swarm.

        Args:
            correlated_issue: The correlated issue to investigate

        Returns:
            Investigation result dictionary
        """
        logger.info(
            f"Starting swarm investigation for correlation {correlated_issue.correlation_id}"
        )

        # Create swarm if not already created
        if self._swarm is None:
            self._swarm = self._create_swarm()

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
            # Run the swarm
            result = self._swarm.run(
                initial_prompt,
                context=context.model_dump(),
            )

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
            EventType.INVESTIGATION_REQUESTED,
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
