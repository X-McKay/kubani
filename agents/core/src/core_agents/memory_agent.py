"""
MemoryAgent - Generic agent for learning and recall.

Base class for memory-based agents that can be customized with
application-specific memory tools.
"""

from typing import Any

from strands import Agent

from core_agents.base import create_agent


# Generic Memory Agent prompt - application-agnostic
MEMORY_AGENT_PROMPT = """You are the MemoryAgent - responsible for learning from past experiences and sharing knowledge.

## Your Role
Store successful actions for future reference and recall past experiences when similar situations occur. You are the team's institutional memory.

## Decision Process
Think step by step:
1. Is this a request to store or recall?
2. For storage: Extract key details (what happened, root cause, solution, outcome)
3. For recall: Search for similar past experiences
4. Check for patterns and recurrences
5. Recommend improvements if issues are recurring

## Example - Storing

Request: "Store successful resolution - service restart resolved the issue"

Step 1: This is a storage request
Step 2: Key details: Issue type, resource affected, fix applied, outcome
Step 3: Store the memory with relevant details
Step 4: Check if this is a recurring issue
Step 5: If recurring, recommend a permanent solution

## Example - Recalling

Request: "Check memories for similar issues"

Step 1: This is a recall request
Step 2: Search for similar past experiences
Step 3: Found relevant memories
Step 4: Check if there's an established solution
Step 5: Provide context to the requester

## Recurrence Thresholds
- 1-2 occurrences: Normal, just record
- 3+ occurrences: Flag as recurring, recommend permanent fix
- 5+ occurrences: Escalate - needs attention

## Handoff Rules
- After storing with recurrence warning: Consider notifying
- For simple storage: May end the chain
- Always include recurrence context in handoffs

## Output
Confirm storage or provide recall results with pattern insights.
"""


class MemoryAgent:
    """
    Generic memory and learning agent.

    Base class that can be customized with application-specific memory tools.
    Manages institutional knowledge about:
    - Past issues and their resolutions
    - Recurring patterns
    - Recommended solutions

    Subclass this or provide custom tools for application-specific memory.
    """

    NAME = "memory"
    DESCRIPTION = "Store and recall learnings from past experiences"

    def __init__(
        self,
        tools: list,
        system_prompt: str | None = None,
        name: str | None = None,
        description: str | None = None,
        hooks_factory: Any = None,
    ):
        """
        Initialize the Memory agent.

        Args:
            tools: List of memory tools (search, store, etc.)
            system_prompt: Custom system prompt (uses default if not provided)
            name: Custom agent name
            description: Custom agent description
            hooks_factory: Factory function to create hooks
        """
        self._agent: Agent | None = None
        self._tools = tools
        self._system_prompt = system_prompt or MEMORY_AGENT_PROMPT
        self._name = name or self.NAME
        self._description = description or self.DESCRIPTION
        self._hooks_factory = hooks_factory

    @property
    def agent(self) -> Agent:
        """Lazy initialization of the Strands agent."""
        if self._agent is None:
            self._agent = create_agent(
                name=self._name,
                description=self._description,
                system_prompt=self._system_prompt,
                tools=self._tools,
                hooks_factory=self._hooks_factory,
            )
        return self._agent

    def __call__(self, prompt: str) -> str:
        """Execute the agent with a prompt."""
        return str(self.agent(prompt))
