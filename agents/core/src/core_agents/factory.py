"""
Agent Factory for standardized agent, swarm, and graph creation.

Provides unified factory patterns for creating Strands agents, swarms,
and graphs with consistent configuration, observability, and tooling.

Supports the hybrid workflow-agent architecture pattern where deterministic
workflows handle predictable processes while agents handle complex reasoning.

Usage:
    from core_agents.factory import AgentFactory, AgentConfig, SwarmConfig, GraphConfig

    # Create factory with dependency injection
    from core_agents.config import get_config
    config = get_config()
    factory = AgentFactory(config=config)

    # Create a single agent
    agent = factory.create_agent(AgentConfig(
        name="my-agent",
        description="My agent description",
        system_prompt="You are a helpful assistant.",
        tools=[my_tool],
    ))

    # Create a swarm
    swarm = factory.create_swarm(SwarmConfig(
        agents=[agent1, agent2, agent3],
        entry_point=agent1,
        max_handoffs=10,
    ))

    # Create a graph (hybrid workflow)
    graph = factory.create_graph(GraphConfig(
        name="triage-workflow",
        nodes=[diagnostic_node, decision_node, agent_node],
        edges=[("diagnostic", "decision"), ("decision", "agent")],
    ))
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from strands import Agent
from strands.models.openai import OpenAIModel
from strands.multiagent import Swarm

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Protocols for Dependency Injection
# -------------------------------------------------------------------------


@runtime_checkable
class ConfigProtocol(Protocol):
    """Protocol for configuration objects."""

    vllm_api_url: str
    default_model_id: str
    model_temperature: float
    model_max_tokens: int


# -------------------------------------------------------------------------
# Configuration Classes
# -------------------------------------------------------------------------


@dataclass
class ModelConfig:
    """
    Configuration for LLM model creation.

    Attributes:
        base_url: API endpoint URL (defaults to centralized config)
        model_id: Model identifier (defaults to centralized config)
        api_key: API key (defaults to "not-needed" for local vLLM)
        temperature: Sampling temperature (0.0-1.0, lower = more deterministic)
        max_tokens: Maximum tokens to generate
        stream: Whether to stream responses (required True for vLLM + Strands)
    """

    base_url: str | None = None
    model_id: str | None = None
    api_key: str = "not-needed"
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = True

    def resolve_defaults(self, config: ConfigProtocol | None = None) -> "ModelConfig":
        """
        Resolve defaults from configuration.

        Args:
            config: Configuration object to use for defaults

        Returns:
            New ModelConfig with resolved values
        """
        if config is None:
            from core_agents.config import get_config

            config = get_config()

        return ModelConfig(
            base_url=self.base_url if self.base_url is not None else config.vllm_api_url,
            model_id=self.model_id if self.model_id is not None else config.default_model_id,
            api_key=self.api_key,
            temperature=self.temperature if self.temperature is not None else config.model_temperature,
            max_tokens=self.max_tokens if self.max_tokens is not None else config.model_max_tokens,
            stream=self.stream,
        )

    def __post_init__(self):
        """Resolve defaults from centralized configuration if not using DI."""
        # Only auto-resolve if all values are None (backward compatibility)
        if all(
            v is None
            for v in [self.base_url, self.model_id, self.temperature, self.max_tokens]
        ):
            from core_agents.config import get_config

            config = get_config()
            self.base_url = config.vllm_api_url
            self.model_id = config.default_model_id
            self.temperature = config.model_temperature
            self.max_tokens = config.model_max_tokens


@dataclass
class AgentConfig:
    """
    Configuration for single agent creation.

    Attributes:
        name: Agent name (used for identification in swarm)
        description: Brief description of agent's role
        system_prompt: The agent's system prompt
        tools: List of tools available to this agent
        model_config: Model configuration (uses defaults if not provided)
        hooks: Pre-configured hooks list
        hooks_factory: Factory function to create hooks (called if hooks not provided)
        enable_observability: Add observability hooks for metrics (default: True)
        observability_debug: Enable verbose debug logging in observability hooks
        mcp_clients: List of MCP clients to add as tools
        context_manager: Optional ContextManager for context engineering
    """

    name: str
    description: str
    system_prompt: str
    tools: list[Any] = field(default_factory=list)
    model_config: ModelConfig | None = None
    hooks: list[Any] | None = None
    hooks_factory: Callable[[], list[Any]] | None = None
    enable_observability: bool = True
    observability_debug: bool = False
    mcp_clients: list[Any] = field(default_factory=list)
    context_manager: Any | None = None  # ContextManager instance


@dataclass
class SwarmConfig:
    """
    Configuration for swarm creation.

    Attributes:
        agents: List of agents in the swarm
        entry_point: The agent that receives initial requests
        max_handoffs: Maximum number of agent handoffs (default: 10)
        max_iterations: Total execution cap (default: 20)
        execution_timeout: Total timeout in seconds (default: 300)
        node_timeout: Per-agent turn timeout in seconds (default: 120)
        repetitive_handoff_window: Window for detecting repetitive handoffs (default: 8)
        repetitive_handoff_min_unique: Minimum unique agents in window (default: 3)
    """

    agents: list[Agent]
    entry_point: Agent
    max_handoffs: int = 10
    max_iterations: int = 20
    execution_timeout: float = 300.0
    node_timeout: float = 120.0
    repetitive_handoff_window: int = 8
    repetitive_handoff_min_unique: int = 3


class NodeType(Enum):
    """Types of nodes in a graph workflow."""

    FUNCTION = "function"  # Deterministic function node
    AGENT = "agent"  # AI agent node
    CONDITIONAL = "conditional"  # Branching node
    PARALLEL = "parallel"  # Parallel execution node
    SUBGRAPH = "subgraph"  # Nested graph


@dataclass
class GraphNode:
    """
    A node in a graph workflow.

    Attributes:
        name: Unique node identifier
        node_type: Type of node
        handler: Function or agent to execute
        description: Human-readable description
        timeout: Execution timeout in seconds
        retry_count: Number of retries on failure
        metadata: Additional node metadata
    """

    name: str
    node_type: NodeType
    handler: Callable[..., Any] | Agent | None = None
    description: str = ""
    timeout: float = 60.0
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """
    An edge connecting nodes in a graph.

    Attributes:
        source: Source node name
        target: Target node name
        condition: Optional condition function for conditional edges
        label: Human-readable label
    """

    source: str
    target: str
    condition: Callable[[Any], bool] | None = None
    label: str = ""


@dataclass
class GraphConfig:
    """
    Configuration for graph (workflow) creation.

    Attributes:
        name: Graph name
        description: Graph description
        nodes: List of graph nodes
        edges: List of edges (can be tuples or GraphEdge objects)
        entry_point: Name of the entry node
        max_iterations: Maximum iterations for cyclic graphs
        timeout: Total execution timeout
        enable_tracing: Enable execution tracing
    """

    name: str
    description: str = ""
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge | tuple[str, str]] = field(default_factory=list)
    entry_point: str = ""
    max_iterations: int = 100
    timeout: float = 600.0
    enable_tracing: bool = True


# -------------------------------------------------------------------------
# Graph Implementation
# -------------------------------------------------------------------------


class Graph:
    """
    A workflow graph that supports hybrid agent-workflow patterns.

    Combines deterministic workflow steps with AI agent nodes for
    complex reasoning tasks. This pattern has been shown to reduce
    token usage by ~4x compared to pure agent approaches.
    """

    def __init__(self, config: GraphConfig):
        """
        Initialize the graph.

        Args:
            config: Graph configuration
        """
        self.config = config
        self.name = config.name
        self.description = config.description

        # Build node and edge maps
        self._nodes: dict[str, GraphNode] = {node.name: node for node in config.nodes}
        self._edges: dict[str, list[GraphEdge]] = {}
        self._reverse_edges: dict[str, list[str]] = {}

        for edge in config.edges:
            if isinstance(edge, tuple):
                edge = GraphEdge(source=edge[0], target=edge[1])

            if edge.source not in self._edges:
                self._edges[edge.source] = []
            self._edges[edge.source].append(edge)

            if edge.target not in self._reverse_edges:
                self._reverse_edges[edge.target] = []
            self._reverse_edges[edge.target].append(edge.source)

        # Determine entry point
        self._entry_point = config.entry_point
        if not self._entry_point and config.nodes:
            # Find node with no incoming edges
            for node in config.nodes:
                if node.name not in self._reverse_edges:
                    self._entry_point = node.name
                    break

        # Execution state
        self._trace: list[dict[str, Any]] = []

        logger.info(f"Graph '{self.name}' initialized with {len(self._nodes)} nodes")

    async def execute(
        self,
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute the graph workflow.

        Args:
            input_data: Initial input data
            context: Optional execution context

        Returns:
            Execution result with output and trace
        """
        import asyncio

        context = context or {}
        self._trace = []

        current_node = self._entry_point
        current_data = input_data
        iteration = 0

        while current_node and iteration < self.config.max_iterations:
            iteration += 1
            node = self._nodes.get(current_node)

            if not node:
                logger.error(f"Node '{current_node}' not found")
                break

            # Execute node
            try:
                start_time = asyncio.get_event_loop().time()
                result = await self._execute_node(node, current_data, context)
                execution_time = asyncio.get_event_loop().time() - start_time

                # Record trace
                self._trace.append(
                    {
                        "node": node.name,
                        "type": node.node_type.value,
                        "input": str(current_data)[:200],
                        "output": str(result)[:200],
                        "execution_time": execution_time,
                        "iteration": iteration,
                    }
                )

                current_data = result

            except Exception as e:
                logger.error(f"Node '{node.name}' failed: {e}")
                self._trace.append(
                    {
                        "node": node.name,
                        "type": node.node_type.value,
                        "error": str(e),
                        "iteration": iteration,
                    }
                )

                # Retry if configured
                if node.retry_count > 0:
                    node.retry_count -= 1
                    continue

                raise

            # Determine next node
            current_node = self._get_next_node(node.name, current_data)

        return {
            "output": current_data,
            "trace": self._trace,
            "iterations": iteration,
            "completed": current_node is None,
        }

    async def _execute_node(
        self,
        node: GraphNode,
        input_data: Any,
        context: dict[str, Any],
    ) -> Any:
        """Execute a single node."""
        import asyncio

        logger.debug(f"Executing node: {node.name} ({node.node_type.value})")

        if node.handler is None:
            return input_data

        if node.node_type == NodeType.AGENT:
            # Execute agent
            if isinstance(node.handler, Agent):
                # Format input as message
                if isinstance(input_data, str):
                    message = input_data
                else:
                    message = str(input_data)

                result = node.handler(message)
                return result.message if hasattr(result, "message") else str(result)

        elif node.node_type == NodeType.FUNCTION:
            # Execute function
            if asyncio.iscoroutinefunction(node.handler):
                return await node.handler(input_data, context)
            else:
                return node.handler(input_data, context)

        elif node.node_type == NodeType.CONDITIONAL:
            # Conditional just passes through; routing handled by edges
            return input_data

        elif node.node_type == NodeType.PARALLEL:
            # Execute parallel branches
            # This is a simplified implementation
            return input_data

        return input_data

    def _get_next_node(self, current: str, data: Any) -> str | None:
        """Determine the next node based on edges and conditions."""
        edges = self._edges.get(current, [])

        if not edges:
            return None

        # Check conditional edges first
        for edge in edges:
            if edge.condition is not None:
                if edge.condition(data):
                    return edge.target
            else:
                # Non-conditional edge
                return edge.target

        return None

    def get_trace(self) -> list[dict[str, Any]]:
        """Get execution trace."""
        return list(self._trace)

    def visualize(self) -> str:
        """
        Generate a Mermaid diagram of the graph.

        Returns:
            Mermaid diagram string
        """
        lines = ["graph TD"]

        for node in self._nodes.values():
            shape = {
                NodeType.FUNCTION: f"[{node.name}]",
                NodeType.AGENT: f"(({node.name}))",
                NodeType.CONDITIONAL: f"{{{node.name}}}",
                NodeType.PARALLEL: f"[/{node.name}/]",
                NodeType.SUBGRAPH: f"[[{node.name}]]",
            }.get(node.node_type, f"[{node.name}]")

            lines.append(f"    {node.name}{shape}")

        for source, edges in self._edges.items():
            for edge in edges:
                label = f"|{edge.label}|" if edge.label else ""
                lines.append(f"    {source} -->{label} {edge.target}")

        return "\n".join(lines)


# -------------------------------------------------------------------------
# Factory Class
# -------------------------------------------------------------------------


class AgentFactory:
    """
    Factory for creating standardized Strands agents, swarms, and graphs.

    Provides consistent creation with:
    - Dependency injection for configuration
    - Automatic observability hooks
    - Standard model configuration
    - MCP client integration
    - Swarm guardrails
    - Hybrid workflow support via graphs

    Can be used directly or subclassed for domain-specific factories.
    """

    def __init__(
        self,
        config: ConfigProtocol | None = None,
        default_model_config: ModelConfig | None = None,
        default_observability: bool = True,
    ):
        """
        Initialize the factory.

        Args:
            config: Configuration object (dependency injection)
            default_model_config: Default model config for all agents
            default_observability: Whether to enable observability by default
        """
        self._config = config
        self._default_observability = default_observability
        self._model_cache: dict[str, OpenAIModel] = {}

        # Resolve model config with injected config
        if default_model_config:
            self._default_model_config = default_model_config.resolve_defaults(config)
        else:
            self._default_model_config = ModelConfig().resolve_defaults(config)

    @property
    def config(self) -> ConfigProtocol:
        """Get the configuration object."""
        if self._config is None:
            from core_agents.config import get_config

            self._config = get_config()
        return self._config

    def create_model(self, config: ModelConfig | None = None) -> OpenAIModel:
        """
        Create an LLM model provider.

        Args:
            config: Model configuration (uses defaults if not provided)

        Returns:
            Configured OpenAIModel instance
        """
        cfg = config.resolve_defaults(self._config) if config else self._default_model_config

        # Create cache key
        cache_key = f"{cfg.base_url}:{cfg.model_id}:{cfg.temperature}:{cfg.max_tokens}"

        # Return cached model if available
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]

        logger.info(f"Creating model provider: {cfg.model_id} at {cfg.base_url}")

        model = OpenAIModel(
            client_args={
                "base_url": cfg.base_url,
                "api_key": cfg.api_key,
            },
            model_id=cfg.model_id,
            params={
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens,
                "stream": cfg.stream,
            },
        )

        self._model_cache[cache_key] = model
        return model

    def create_agent(self, config: AgentConfig) -> Agent:
        """
        Create a Strands agent with standard configuration.

        Args:
            config: Agent configuration

        Returns:
            Configured Strands Agent
        """
        # Create or use provided model
        model = self.create_model(config.model_config)

        # Build tools list (include MCP clients)
        agent_tools = list(config.tools)
        for mcp_client in config.mcp_clients:
            agent_tools.append(mcp_client)

        # Get hooks from factory if not provided directly
        agent_hooks = config.hooks
        if agent_hooks is None and config.hooks_factory is not None:
            agent_hooks = config.hooks_factory()

        # Add observability hooks if enabled
        enable_obs = config.enable_observability and self._default_observability
        if enable_obs:
            from core_agents.observability import create_observability_hooks

            obs_hooks = create_observability_hooks(
                enable_debug_logging=config.observability_debug,
            )
            agent_hooks = [obs_hooks] if agent_hooks is None else list(agent_hooks) + [obs_hooks]

        # Enhance system prompt with context if context manager provided
        system_prompt = config.system_prompt
        if config.context_manager is not None:
            context_addition = config.context_manager.get_system_prompt_addition()
            system_prompt = system_prompt + context_addition

        logger.debug(f"Creating agent: {config.name}")

        return Agent(
            model=model,
            name=config.name,
            description=config.description,
            system_prompt=system_prompt,
            tools=agent_tools,
            hooks=agent_hooks,
        )

    def create_swarm(self, config: SwarmConfig) -> Swarm:
        """
        Create a Strands swarm with standard guardrails.

        Args:
            config: Swarm configuration

        Returns:
            Configured Strands Swarm
        """
        logger.info(
            f"Creating swarm with {len(config.agents)} agents, "
            f"entry_point={config.entry_point.name}"
        )

        return Swarm(
            config.agents,
            entry_point=config.entry_point,
            max_handoffs=config.max_handoffs,
            max_iterations=config.max_iterations,
            execution_timeout=config.execution_timeout,
            node_timeout=config.node_timeout,
            repetitive_handoff_detection_window=config.repetitive_handoff_window,
            repetitive_handoff_min_unique_agents=config.repetitive_handoff_min_unique,
        )

    def create_graph(self, config: GraphConfig) -> Graph:
        """
        Create a workflow graph for hybrid agent-workflow patterns.

        Graphs combine deterministic workflow steps with AI agents,
        providing reliability of workflows with flexibility of agents.

        Args:
            config: Graph configuration

        Returns:
            Configured Graph instance
        """
        logger.info(f"Creating graph: {config.name} with {len(config.nodes)} nodes")
        return Graph(config)

    def create_hybrid_workflow(
        self,
        name: str,
        diagnostic_fn: Callable[..., Any],
        agent: Agent,
        post_process_fn: Callable[..., Any] | None = None,
    ) -> Graph:
        """
        Create a common hybrid workflow pattern.

        This pattern runs deterministic diagnostics first, then invokes
        an agent for complex reasoning, and optionally post-processes.

        Args:
            name: Workflow name
            diagnostic_fn: Function to run diagnostics
            agent: Agent for complex reasoning
            post_process_fn: Optional post-processing function

        Returns:
            Configured Graph
        """
        nodes = [
            GraphNode(
                name="diagnostic",
                node_type=NodeType.FUNCTION,
                handler=diagnostic_fn,
                description="Run initial diagnostics",
            ),
            GraphNode(
                name="agent",
                node_type=NodeType.AGENT,
                handler=agent,
                description="AI agent for reasoning",
            ),
        ]

        edges = [("diagnostic", "agent")]

        if post_process_fn:
            nodes.append(
                GraphNode(
                    name="post_process",
                    node_type=NodeType.FUNCTION,
                    handler=post_process_fn,
                    description="Post-process results",
                )
            )
            edges.append(("agent", "post_process"))

        config = GraphConfig(
            name=name,
            description=f"Hybrid workflow: {name}",
            nodes=nodes,
            edges=edges,
            entry_point="diagnostic",
        )

        return self.create_graph(config)


# -------------------------------------------------------------------------
# Singleton and Convenience Functions
# -------------------------------------------------------------------------


_default_factory: AgentFactory | None = None


def get_agent_factory(config: ConfigProtocol | None = None) -> AgentFactory:
    """
    Get the default agent factory singleton.

    Args:
        config: Optional configuration for dependency injection

    Returns:
        AgentFactory singleton instance
    """
    global _default_factory
    if _default_factory is None or config is not None:
        _default_factory = AgentFactory(config=config)
    return _default_factory


def create_model(config: ModelConfig | None = None) -> OpenAIModel:
    """
    Convenience function to create a model using the default factory.

    Args:
        config: Model configuration (uses defaults if not provided)

    Returns:
        Configured OpenAIModel instance
    """
    return get_agent_factory().create_model(config)


def create_agent(config: AgentConfig) -> Agent:
    """
    Convenience function to create an agent using the default factory.

    Args:
        config: Agent configuration

    Returns:
        Configured Strands Agent
    """
    return get_agent_factory().create_agent(config)


def create_swarm(config: SwarmConfig) -> Swarm:
    """
    Convenience function to create a swarm using the default factory.

    Args:
        config: Swarm configuration

    Returns:
        Configured Strands Swarm
    """
    return get_agent_factory().create_swarm(config)


def create_graph(config: GraphConfig) -> Graph:
    """
    Convenience function to create a graph using the default factory.

    Args:
        config: Graph configuration

    Returns:
        Configured Graph instance
    """
    return get_agent_factory().create_graph(config)


# Quick agent creation for simple cases (backward compatible API)
def quick_agent(
    name: str,
    description: str,
    system_prompt: str,
    tools: list[Any],
    **kwargs,
) -> Agent:
    """
    Quick agent creation with minimal configuration.

    This provides a simpler API for creating agents without needing
    to construct an AgentConfig explicitly.

    Args:
        name: Agent name
        description: Agent description
        system_prompt: System prompt
        tools: List of tools
        **kwargs: Additional AgentConfig fields

    Returns:
        Configured Strands Agent
    """
    config = AgentConfig(
        name=name,
        description=description,
        system_prompt=system_prompt,
        tools=tools,
        **kwargs,
    )
    return get_agent_factory().create_agent(config)
