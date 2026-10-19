"""Construct a standard ADK agent using the SDK context."""

from google.adk.agents import LlmAgent
from zetra.agent import AgentContext

from .toolset import tools


def create_agent(ctx: AgentContext) -> LlmAgent:
    return LlmAgent(
        name="investigator",
        model=ctx.model,
        tools=tools(ctx),
        instruction=ctx.instruction,
    )
