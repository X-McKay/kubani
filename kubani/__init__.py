"""
Kubani Agent Framework.

This package provides the core framework for building Skills, Agents, and Syndicates:

- **Skills**: Isolated, executable units with clear objectives (AgentSkills.io format)
- **Agents**: Roles/personas that use skills to perform specific work
- **Syndicates**: Missions that orchestrate multiple agents to accomplish objectives

Usage:
    from kubani.framework import get_config
    from kubani.agents import KubaniAgent
    from kubani.syndicates import Syndicate

    # Create an agent
    class MyAgent(KubaniAgent):
        async def on_skill_complete(self, skill_name: str, result: dict):
            await self.record_outcome(skill_name, result)

    # Create a syndicate
    class MySyndicate(Syndicate):
        agents = [MyAgent]

        async def run(self):
            agent = self.get_agent(MyAgent)
            await agent.run("Do something")
"""

__version__ = "0.1.0"


# Lazy imports to avoid loading heavy dependencies (httpx, etc.) when
# only subpackages like kubani.workflows are needed. This is required
# for Temporal workflow sandbox compatibility.
def __getattr__(name: str):
    """Lazy import of main components."""
    if name == "KubaniAgent":
        from .agents import KubaniAgent

        return KubaniAgent
    if name == "get_config":
        from .framework import get_config

        return get_config
    if name == "Syndicate":
        from .syndicates import Syndicate

        return Syndicate
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "__version__",
    # Framework
    "get_config",
    # Agents
    "KubaniAgent",
    # Syndicates
    "Syndicate",
]
