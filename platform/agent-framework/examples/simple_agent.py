"""
Example: Simple Agent using the Agent Framework.

Demonstrates:
- AgentBase usage
- Mixin composition
- Local execution with AgentRunner

Run with:
    python examples/simple_agent.py --mode local
    python examples/simple_agent.py --event '{"type": "test"}'
"""

import asyncio
from typing import Any

from agent_framework import AgentBase
from agent_framework.mixins import ObservabilityMixin, SkillLoaderMixin


class SimpleAgent(AgentBase, ObservabilityMixin, SkillLoaderMixin):
    """
    A simple example agent demonstrating the framework.

    This agent:
    - Initializes observability and skills
    - Handles events by logging them
    - Can execute skills on demand
    """

    async def initialize(self) -> None:
        """Initialize the agent."""
        await super().initialize()

        # Initialize mixins
        self.init_observability()
        await self.init_skills()

        self.log.info("SimpleAgent initialized")

    async def run(self) -> None:
        """Main run loop - waits for shutdown."""
        self.log.info("SimpleAgent running, waiting for events...")

        # Simple example: just wait
        # In a real agent, this would poll for events or run workflows
        while self.running:
            await asyncio.sleep(1)

    async def handle_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Handle an incoming event."""
        event_type = event.get("type", "unknown")
        self.log.info("Handling event", event_type=event_type)

        # Example: execute a skill based on event type
        if event_type == "pod_crash":
            pod = event.get("pod", "unknown")
            namespace = event.get("namespace", "default")

            # Check if skill exists, execute if so
            available_skills = await self.list_skills()
            if "k8s/investigate-pod-failure" in available_skills:
                trace = await self.execute_skill(
                    "k8s/investigate-pod-failure",
                    context={"pod": pod, "namespace": namespace},
                )
                return {"handled": True, "trace_id": trace.trace_id}

        return {"handled": True, "event_type": event_type}

    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        self.log.info("SimpleAgent shutting down")
        await super().shutdown()


if __name__ == "__main__":
    from agent_framework.runner import run_agent

    run_agent(
        SimpleAgent,
        name="simple-agent",
        version="0.1.0",
        description="Example agent demonstrating the framework",
    )
