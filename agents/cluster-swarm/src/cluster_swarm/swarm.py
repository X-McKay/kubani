"""
Swarm Agents - Collaborative investigation through specialized agents.

The swarm consists of:
- Triage Agent: Entry point, analyzes issue and routes to specialist
- Investigator Agent: Diagnostic specialist
- Memory Agent: Queries and stores learnings
- Remediation Agent: Plans and executes fixes
- Communications Agent: Manages Discord updates

Agents collaborate through handoffs, with each contributing their expertise.
"""

import asyncio
import logging
import os
from typing import Any

from strands import Agent
from strands.multiagent import Swarm

from cluster_swarm.models import CorrelatedIssue, SwarmContext
from core_agents.events import Event, EventBus, EventType, get_event_bus
from core_agents.factory import AgentConfig, AgentFactory, SwarmConfig

logger = logging.getLogger(__name__)


def create_triage_agent(factory: AgentFactory) -> Agent:
    """
    Create the Triage Agent - entry point for the swarm.
    
    Analyzes the initial issue and hands off to the appropriate specialist.
    """
    return factory.create_agent(
        AgentConfig(
            name="triage",
            description="Initial triage and routing specialist",
            system_prompt="""You are the triage specialist for Kubernetes incident response.

Your role:
1. Analyze the incoming correlated issue
2. Assess severity and urgency
3. Identify which specialist agent(s) should investigate
4. Hand off to the appropriate agent with clear context

Available specialists:
- investigator: For diagnostic work (logs, events, resource checks)
- memory: For querying past incidents and patterns
- remediation: For planning and executing fixes
- communications: For posting updates to Discord

Always start by handing off to the communications agent to post an initial message,
then proceed with investigation.""",
            tools=[],  # TODO: Add MCP tools if needed
        )
    )


def create_investigator_agent(factory: AgentFactory) -> Agent:
    """
    Create the Investigator Agent - diagnostic specialist.
    
    Runs diagnostic skills and gathers information about the issue.
    """
    return factory.create_agent(
        AgentConfig(
            name="investigator",
            description="Diagnostic specialist for Kubernetes issues",
            system_prompt="""You are an expert Kubernetes diagnostic specialist.

Your role:
1. Investigate issues using available tools and skills
2. Check pod logs, events, and resource states
3. Identify root causes
4. Share findings with other agents

When you've gathered diagnostic information:
- Hand off to memory agent to check for similar past incidents
- Or hand off to remediation agent if you've identified a clear fix
- Keep communications agent informed of your findings

Be thorough but efficient. Focus on actionable insights.""",
            tools=[],  # TODO: Add kubernetes-mcp tools
        )
    )


def create_memory_agent(factory: AgentFactory) -> Agent:
    """
    Create the Memory Agent - learning and pattern specialist.
    
    Queries past incidents and stores new learnings.
    """
    return factory.create_agent(
        AgentConfig(
            name="memory",
            description="Memory and learning specialist",
            system_prompt="""You are the memory specialist for incident response.

Your role:
1. Query our knowledge base for similar past incidents
2. Identify patterns and recurring issues
3. Share relevant historical context with other agents
4. Store new learnings after investigations complete

When you find relevant past incidents:
- Share the resolution strategies that worked before
- Hand off to remediation agent if there's a known fix
- Hand off to investigator if more diagnostics are needed

After the investigation completes, store the learnings for future reference.""",
            tools=[],  # TODO: Add memory-mcp tools
        )
    )


def create_remediation_agent(factory: AgentFactory) -> Agent:
    """
    Create the Remediation Agent - fix specialist.
    
    Plans and executes remediation actions.
    """
    return factory.create_agent(
        AgentConfig(
            name="remediation",
            description="Remediation specialist",
            system_prompt="""You are a Kubernetes remediation specialist.

Your role:
1. Plan safe remediation actions based on diagnostic findings
2. Execute remediation using available tools and skills
3. Verify that the fix worked
4. Hand off to communications agent to report results

Before executing high-risk actions:
- Explain what you're about to do and why
- Consider requesting approval for destructive operations

After executing:
- Verify the issue is resolved
- Hand off to memory agent to store the successful resolution""",
            tools=[],  # TODO: Add kubernetes-mcp tools and remediation skills
        )
    )


def create_communications_agent(factory: AgentFactory) -> Agent:
    """
    Create the Communications Agent - Discord specialist.
    
    Manages all communication with users via Discord.
    """
    return factory.create_agent(
        AgentConfig(
            name="communications",
            description="Communications and user interaction specialist",
            system_prompt="""You are the communications specialist for incident response.

Your role:
1. Post clear, conversational updates to Discord
2. Maintain a coherent narrative throughout the investigation
3. Translate technical findings into understandable language
4. Keep stakeholders informed at key milestones

Communication style:
- Write like an experienced engineer explaining to a colleague
- Be transparent about what's happening and why
- Avoid jargon where possible, but use technical terms when appropriate
- Be confident but acknowledge uncertainty when it exists

Post updates when:
- Investigation starts (initial message)
- Key findings are discovered
- Remediation is planned or executed
- Investigation completes (final summary)

After posting, hand off back to the agent that needs to continue work.""",
            tools=[],  # TODO: Add discord-mcp tools
        )
    )


class ClusterSwarm:
    """
    Manages the cluster monitoring swarm.
    
    Activates the swarm for each correlated issue and coordinates
    the collaborative investigation.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        factory: AgentFactory | None = None,
    ):
        self.event_bus = event_bus or get_event_bus()
        self.factory = factory or AgentFactory()
        self._swarm: Swarm | None = None

    def _create_swarm(self) -> Swarm:
        """Create the agent swarm."""
        # Create all agents
        triage = create_triage_agent(self.factory)
        investigator = create_investigator_agent(self.factory)
        memory = create_memory_agent(self.factory)
        remediation = create_remediation_agent(self.factory)
        communications = create_communications_agent(self.factory)

        # Create swarm with triage as entry point
        swarm = self.factory.create_swarm(
            SwarmConfig(
                agents=[triage, investigator, memory, remediation, communications],
                entry_point=triage,
                max_handoffs=20,  # Allow more handoffs for complex investigations
                max_iterations=30,
            )
        )

        return swarm

    async def investigate(self, correlated_issue: CorrelatedIssue) -> dict[str, Any]:
        """
        Conduct an investigation using the swarm.
        
        Args:
            correlated_issue: The correlated issue to investigate
            
        Returns:
            Investigation results
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

        # Get or create swarm
        if self._swarm is None:
            self._swarm = self._create_swarm()

        # Build initial prompt for triage agent
        event_descriptions = "\n".join(
            [
                f"- {e.resource_kind}/{e.resource_name} in {e.namespace}: "
                f"{e.reason} - {e.message}"
                for e in correlated_issue.events
            ]
        )

        initial_prompt = f"""New correlated issue detected:

Correlation ID: {correlated_issue.correlation_id}
Pattern: {correlated_issue.pattern_type}
Severity: {correlated_issue.severity.value}
Affected Namespaces: {', '.join(correlated_issue.affected_namespaces)}

Events:
{event_descriptions}

Please triage this issue and coordinate the investigation."""

        try:
            # Run the swarm
            # TODO: Actually run the swarm with proper context passing
            # For now, log the investigation
            logger.info(f"Swarm investigating: {correlated_issue.pattern_type}")
            
            # Mock result
            result = {
                "correlation_id": correlated_issue.correlation_id,
                "investigation_complete": True,
                "findings": {"mock": "swarm investigation result"},
            }

            return result

        except Exception as e:
            logger.error(f"Swarm investigation failed: {e}", exc_info=True)
            return {
                "correlation_id": correlated_issue.correlation_id,
                "investigation_complete": False,
                "error": str(e),
            }

    async def process_investigation_request(self, event: Event) -> None:
        """Process an INVESTIGATION_REQUESTED event."""
        try:
            # Note: cluster-swarm uses the same correlator as cluster-monitor
            # Both subscribe to INVESTIGATION_REQUESTED events
            correlated_issue = CorrelatedIssue(**event.payload)
            await self.investigate(correlated_issue)
        except Exception as e:
            logger.error(f"Failed to process investigation request: {e}", exc_info=True)

    async def run(self) -> None:
        """
        Run the cluster swarm service.
        
        Subscribes to INVESTIGATION_REQUESTED events and conducts investigations.
        """
        logger.info("Starting Cluster Swarm service")

        async for event in self.event_bus.subscribe(
            EventType.INVESTIGATION_REQUESTED,
            consumer_group="cluster-swarm",
            consumer_name="swarm-1",
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
