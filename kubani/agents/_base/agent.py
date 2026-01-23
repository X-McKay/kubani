"""
Base class for Kubani Agents.

Agents are roles/personas that use skills to perform specific work. They load
their configuration from a standardized directory structure:

    kubani/agents/sentinel/
    ├── agent.py           # Agent class (extends KubaniAgent)
    ├── prompt.md          # System prompt
    ├── config.yaml        # Skills manifest and configuration
    └── tests/             # Agent tests

Usage:
    from kubani.agents._base import KubaniAgent

    class SentinelAgent(KubaniAgent):
        '''Detects and classifies Kubernetes cluster events.'''

        async def on_skill_complete(self, skill_name: str, result: dict):
            await self.record_outcome(skill_name, result)

    agent = SentinelAgent()
"""

import logging
from abc import ABC
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from kubani.framework.config import get_config
from kubani.framework.mcp.skills import get_filtered_skills

if TYPE_CHECKING:
    from strands import Agent

logger = logging.getLogger(__name__)


class KubaniAgent(ABC):
    """
    Base class for Kubani agents.

    Agents load their configuration from:
    - config.yaml: Skills manifest, capabilities, and settings
    - prompt.md: System prompt for the agent

    Subclasses can override:
    - on_skill_complete(): Called after each skill execution
    - on_error(): Called when an error occurs
    - get_additional_tools(): Return additional tools for the agent
    """

    # Override in subclass to specify agent directory
    # If not set, uses the directory containing the subclass
    AGENT_DIR: Path | None = None

    def __init__(self, agent_dir: Path | None = None):
        """
        Initialize the agent.

        Args:
            agent_dir: Override the agent directory. If not provided,
                      uses AGENT_DIR or auto-detects from subclass location.
        """
        self._agent_dir = self._resolve_agent_dir(agent_dir)
        self._config: dict[str, Any] | None = None
        self._prompt: str | None = None
        self._agent: Agent | None = None
        self._tools: list[Any] | None = None

    def _resolve_agent_dir(self, agent_dir: Path | None) -> Path:
        """Resolve the agent directory."""
        if agent_dir:
            return agent_dir
        if self.AGENT_DIR:
            return self.AGENT_DIR

        # Auto-detect from subclass location
        import inspect

        subclass_file = inspect.getfile(self.__class__)
        return Path(subclass_file).parent

    @property
    def config(self) -> dict[str, Any]:
        """Get agent configuration from config.yaml."""
        if self._config is None:
            self._config = self._load_config()
        return self._config

    @property
    def prompt(self) -> str:
        """Get system prompt from prompt.md."""
        if self._prompt is None:
            self._prompt = self._load_prompt()
        return self._prompt

    @property
    def name(self) -> str:
        """Get agent name from config."""
        return self.config.get("name", self.__class__.__name__)

    @property
    def description(self) -> str:
        """Get agent description from config."""
        return self.config.get("description", "")

    @property
    def version(self) -> str:
        """Get agent version from config."""
        return self.config.get("version", "1.0.0")

    @property
    def skills_config(self) -> dict[str, Any]:
        """Get skills configuration (allowed/denied patterns)."""
        return self.config.get("skills", {})

    @property
    def capabilities(self) -> list[dict[str, Any]]:
        """Get agent capabilities from config."""
        return self.config.get("capabilities", [])

    @property
    def limits(self) -> dict[str, Any]:
        """Get agent limits from config."""
        return self.config.get("limits", {})

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from config.yaml."""
        config_path = self._agent_dir / "config.yaml"

        if not config_path.exists():
            logger.warning(f"No config.yaml found at {config_path}")
            return {}

        try:
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load config.yaml: {e}")
            return {}

    def _load_prompt(self) -> str:
        """Load system prompt from prompt.md."""
        prompt_path = self._agent_dir / "prompt.md"

        if not prompt_path.exists():
            logger.warning(f"No prompt.md found at {prompt_path}")
            return f"You are {self.name}. {self.description}"

        try:
            return prompt_path.read_text()
        except Exception as e:
            logger.error(f"Failed to load prompt.md: {e}")
            return f"You are {self.name}. {self.description}"

    async def get_tools(self) -> list[Any]:
        """
        Get tools (skills) for the agent based on config.yaml.

        Returns filtered skills plus any additional tools from get_additional_tools().
        """
        if self._tools is not None:
            return self._tools

        # Get filtered skills based on allowed/denied patterns
        skills = await get_filtered_skills(
            allowed=self.skills_config.get("allowed"),
            denied=self.skills_config.get("denied"),
        )

        # Convert skills to tools
        tools = [await self._skill_to_tool(s) for s in skills]

        # Add any additional tools from subclass
        additional = self.get_additional_tools()
        if additional:
            tools.extend(additional)

        self._tools = tools
        return tools

    async def _skill_to_tool(self, skill: Any) -> Any:
        """Convert a skill to a tool for the agent."""
        # Import here to avoid circular dependency
        from kubani.framework.mcp.skills import get_skill_as_tool

        return await get_skill_as_tool(skill)

    def get_additional_tools(self) -> list[Any]:
        """
        Override to provide additional tools for the agent.

        Returns:
            List of additional tools to add to the agent's toolkit.
        """
        return []

    @property
    def agent(self) -> "Agent":
        """
        Get the Strands Agent instance.

        Creates the agent on first access with the configured prompt and tools.
        """
        if self._agent is None:
            self._agent = self._create_agent()
        return self._agent

    def _create_agent(self) -> "Agent":
        """Create the Strands Agent instance."""
        from strands import Agent

        config = get_config()

        return Agent(
            name=self.name,
            description=self.description,
            system_prompt=self.prompt,
            model_id=config.llm.model,
            max_tokens=self.limits.get("max_tokens", config.llm.max_tokens),
        )

    async def run(self, input_text: str) -> str:
        """
        Run the agent with the given input.

        Args:
            input_text: User input to process

        Returns:
            Agent response
        """
        return await self.agent.run(input_text)

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """
        Called after a skill is executed.

        Override in subclass to implement custom behavior, such as:
        - Recording outcomes for learning
        - Publishing events
        - Triggering follow-up actions

        Args:
            skill_name: Name of the skill that was executed
            result: Result of the skill execution
        """
        pass

    async def on_error(self, error: Exception, context: dict[str, Any] | None = None) -> None:
        """
        Called when an error occurs.

        Override in subclass to implement custom error handling.

        Args:
            error: The exception that occurred
            context: Optional context about what was happening
        """
        logger.error(f"Agent {self.name} error: {error}", exc_info=error)

    async def record_outcome(
        self,
        skill_name: str,
        result: dict[str, Any],
        success: bool = True,
    ) -> None:
        """
        Record a skill outcome for learning.

        Args:
            skill_name: Name of the skill
            result: Result of the skill execution
            success: Whether the skill succeeded
        """
        from kubani.framework.mcp import get_mcp_client

        try:
            client = get_mcp_client()
            await client.memory.store_learning(
                agent_id=self.name,
                learning_type="skill_outcome",
                content=f"Skill {skill_name}: {'success' if success else 'failure'}",
                confidence=0.8 if success else 0.3,
                context={
                    "skill": skill_name,
                    "result": result,
                    "success": success,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to record outcome: {e}")

    def to_agent_info(self) -> "AgentInfo":
        """Convert to AgentInfo for A2A registration."""
        from kubani.framework.a2a import AgentCapability, AgentInfo

        capabilities = [
            AgentCapability(
                name=cap.get("name", ""),
                description=cap.get("description", ""),
            )
            for cap in self.capabilities
        ]

        return AgentInfo(
            id=self.name,
            name=self.name,
            description=self.description,
            capabilities=capabilities,
            endpoint=self.name,  # Kubernetes service name
            version=self.version,
        )
