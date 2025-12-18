# Agent Development Guide

This guide covers creating, testing, and deploying AI agents in the Kubani cluster.

## Architecture Overview

```
agents/
├── core/                         # Reusable agent library (published as wheel)
│   ├── Earthfile                 # Build wheel + push to registry
│   ├── pyproject.toml
│   └── src/core_agents/
│       ├── base.py               # create_model(), create_agent()
│       ├── discord_agent.py      # DiscordAgent + discord_notify tool
│       ├── discord_utils.py      # Discord formatting utilities
│       ├── memory_agent.py       # MemoryAgent base class
│       └── temporal.py           # Temporal workflow utilities
│
├── k8s-monitor/                  # Domain-specific agent (uses core)
│   ├── Earthfile                 # Build Docker image
│   ├── pyproject.toml            # Depends on core-agents
│   └── src/k8s_monitor/
│       ├── agents/               # Specialist agents for swarm
│       │   ├── base.py           # K8s-specific agent utilities
│       │   ├── cluster_triage.py # Entry point agent
│       │   ├── cluster_scout.py  # Cluster scanning
│       │   ├── pod_diagnostician.py
│       │   ├── cluster_remediator.py
│       │   ├── discord_notifier.py  # Wraps core DiscordAgent
│       │   └── remediation_memory.py # Extends core MemoryAgent
│       ├── swarm.py              # Multi-agent orchestration
│       ├── tools.py              # K8s-specific tools
│       ├── prompts.py            # Chain-of-thought prompts
│       ├── hooks.py              # Agent lifecycle hooks
│       ├── models.py             # Pydantic data models
│       ├── memory.py             # mem0 memory integration
│       ├── activities.py         # Temporal activities
│       ├── remediation_activities.py  # Remediation-specific activities
│       ├── workflows.py          # Temporal workflows
│       ├── remediation_workflows.py   # Auto-remediation workflows
│       └── worker.py             # Entry point
│
gitops/apps/ai-agents/            # Kubernetes manifests
└── k8s-monitor/
    ├── deployment.yaml
    ├── rbac.yaml
    └── kustomization.yaml
```

## Core Agents Library

The `agents/core/` package provides reusable agents that can be shared across multiple applications:

### DiscordAgent

Generic Discord notification agent:

```python
from core_agents import DiscordAgent

# Use with default prompt
discord = DiscordAgent()
discord("Send a health check summary to Discord")

# Or customize for your domain
from core_agents import DISCORD_AGENT_PROMPT

custom_prompt = DISCORD_AGENT_PROMPT + "\n\nAdditional context for my domain..."
discord = DiscordAgent(system_prompt=custom_prompt)
```

### MemoryAgent

Base class for agents that need learning/recall capabilities:

```python
from core_agents import MemoryAgent

# Create with your domain-specific tools
memory = MemoryAgent(
    tools=[my_search_tool, my_store_tool],
    system_prompt="Custom prompt for your domain...",
    name="my_memory",
    description="Store and recall learnings",
)
```

### Utilities

```python
from core_agents import create_model, create_agent

# Create LLM model (uses vLLM)
model = create_model(
    base_url="http://llm-api.vllm.svc.cluster.local:8000/v1",
    model_id="Qwen/Qwen3-30B-A3B",
)

# Create agent with hooks
agent = create_agent(
    name="my_agent",
    description="Does something useful",
    system_prompt="You are...",
    tools=[tool1, tool2],
    hooks_factory=my_hooks_factory,  # Optional
)
```

## Multi-Agent Swarm Pattern

For complex tasks, use the Strands Swarm pattern with multiple specialist agents:

```python
from strands.multiagent import Swarm

# Create specialist agents
triage = ClusterTriageAgent()      # Entry point, routes tasks
scout = ClusterScoutAgent()        # Quick scans
diagnostician = PodDiagnosticianAgent()  # Deep analysis
remediator = ClusterRemediatorAgent()    # Applies fixes
memory = RemediationMemoryAgent()  # Learning
notifier = DiscordNotifierAgent()  # Publishing

# Create swarm
swarm = Swarm(
    [
        triage.agent,
        scout.agent,
        diagnostician.agent,
        remediator.agent,
        memory.agent,
        notifier.agent,
    ],
    entry_point=triage.agent,
    max_handoffs=10,           # Prevent runaway handoffs
    max_iterations=20,         # Total execution cap
    execution_timeout=300.0,   # 5 minute timeout
    node_timeout=60.0,         # 1 minute per agent
)

# Run the swarm
result = swarm("Perform a cluster health check")
```

### Agent Handoffs

Each agent can hand off to specialists using the built-in `handoff_to_agent` tool:

```python
# In agent prompt
"""
## Handoff Rules
- For detailed pod analysis: handoff_to_agent("pod_diagnostician", "context...")
- For applying fixes: handoff_to_agent("cluster_remediator", "context...")
- To publish results: handoff_to_agent("discord_notifier", "context...")
"""
```

## Creating a New Agent

### 1. Simple Single-Agent

For straightforward tasks, create a single agent:

```python
# agents/my-agent/src/my_agent/agent.py
from strands import Agent, tool
from core_agents import create_model

@tool
def my_tool(query: str) -> str:
    """Do something useful."""
    return f"Result for: {query}"

def create_agent() -> Agent:
    return Agent(
        model=create_model(),
        tools=[my_tool],
        system_prompt="You are a helpful agent...",
    )
```

### 2. Domain Agent Using Core

To create an agent that uses core agents:

```python
# agents/my-agent/src/my_agent/agents/notifier.py
from core_agents import DiscordAgent
from my_agent.prompts import MY_DISCORD_PROMPT

class MyNotifierAgent:
    """Domain-specific Discord notifier."""

    def __init__(self):
        self._discord = DiscordAgent(
            system_prompt=MY_DISCORD_PROMPT,
            hooks_factory=my_hooks_factory,
        )

    @property
    def agent(self):
        return self._discord.agent

    def __call__(self, prompt: str) -> str:
        return self._discord(prompt)
```

### 3. Multi-Agent Swarm

For complex tasks requiring multiple specialists:

```bash
# Create directory structure
mkdir -p agents/my-agent/src/my_agent/agents
```

Create specialist agents in `agents/my_agent/agents/`:
- `base.py` - Shared utilities
- `coordinator.py` - Entry point agent
- `specialist1.py` - First specialist
- `specialist2.py` - Second specialist
- etc.

Create swarm orchestration in `swarm.py`:

```python
from strands.multiagent import Swarm
from my_agent.agents.coordinator import CoordinatorAgent
from my_agent.agents.specialist1 import Specialist1Agent

def create_swarm() -> Swarm:
    coordinator = CoordinatorAgent()
    specialist1 = Specialist1Agent()

    return Swarm(
        [coordinator.agent, specialist1.agent],
        entry_point=coordinator.agent,
    )
```

## Project Structure

### pyproject.toml

```toml
[project]
name = "my-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "strands-agents>=1.20.0",
    "temporalio>=1.7.0",
    "core-agents",  # Installed from wheel
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.8.0",
]

[tool.uv.sources]
# For local development
core-agents = { path = "../core", editable = true }
```

### Earthfile

```earthly
VERSION 0.8

IMPORT ../.. AS root
IMPORT ../core AS core

ARG --global REGISTRY=registry.almckay.io
ARG --global IMAGE_NAME=my-agent
ARG --global VERSION=latest

deps:
    FROM root+python-base

    # Install core-agents from wheel
    COPY core+wheel/wheel/*.whl /tmp/wheels/
    RUN pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels

    COPY pyproject.toml README.md /app/
    RUN pip install --no-cache-dir -e ".[dev]"

    SAVE IMAGE --cache-hint

src:
    FROM +deps
    COPY src/ /app/src/
    ENV PYTHONPATH=/app/src:/app
    SAVE IMAGE --cache-hint

test:
    FROM +src
    COPY tests/ /app/tests/
    RUN pytest -v

docker:
    FROM root+python-base

    COPY core+wheel/wheel/*.whl /tmp/wheels/
    RUN pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels

    COPY pyproject.toml README.md /app/
    COPY src/ /app/src/
    RUN pip install --no-cache-dir .

    ENV PYTHONPATH=/app/src:/app
    USER agent
    ENTRYPOINT ["python", "-m", "my_agent.worker"]

    SAVE IMAGE ${REGISTRY}/${IMAGE_NAME}:${VERSION}

push:
    FROM +docker
    SAVE IMAGE --push ${REGISTRY}/${IMAGE_NAME}:${VERSION}
```

## Building and Testing

### Build Core Agents

```bash
# Build core-agents wheel
earthly +core-agents

# The wheel is saved to agents/core/dist/

# Push to registry (OCI artifact)
earthly --push +core-agents-push
```

### Build Your Agent

```bash
# Build Docker image (automatically builds core-agents wheel)
earthly ./agents/my-agent+docker

# Run tests
earthly ./agents/my-agent+test

# Push to registry
earthly --push ./agents/my-agent+push
```

### Local Development

```bash
cd agents/my-agent

# Install dependencies (including core-agents from local path)
uv sync

# Run tests
uv run pytest

# Run linting
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Run agent locally
VLLM_API_URL=http://localhost:8000/v1 uv run python -m my_agent.worker
```

### Testing Multi-Agent Swarms

```python
import pytest
from unittest.mock import patch, MagicMock

class TestMySwarm:
    """Test swarm orchestration."""

    def test_swarm_creation(self):
        """Test swarm can be created."""
        from my_agent.swarm import create_swarm

        swarm = create_swarm()
        assert swarm is not None

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check flow."""
        with patch("my_agent.swarm.create_swarm") as mock_create:
            mock_swarm = MagicMock()
            mock_swarm.return_value = {"status": "healthy"}
            mock_create.return_value = mock_swarm

            from my_agent.swarm import run_health_check
            result = await run_health_check()

            assert result["status"] == "healthy"
```

### Testing Individual Agents

```python
class TestCoordinatorAgent:
    """Test coordinator agent."""

    def test_agent_creation(self):
        """Test agent can be created."""
        from my_agent.agents.coordinator import CoordinatorAgent

        agent = CoordinatorAgent()
        assert agent.NAME == "coordinator"
        assert agent.agent is not None

    def test_agent_has_tools(self):
        """Test agent has expected tools."""
        from my_agent.agents.coordinator import CoordinatorAgent

        agent = CoordinatorAgent()
        tool_names = [t.name for t in agent.TOOLS]
        assert "my_tool" in tool_names
```

## Prompt Engineering

### Chain-of-Thought Prompts

Each agent should have a structured prompt in `prompts.py`:

```python
COORDINATOR_PROMPT = """You are the CoordinatorAgent - the entry point for all requests.

## Your Role
Quickly assess incoming requests and route to the appropriate specialist.

## Available Tools
- tool1: Description of tool1
- tool2: Description of tool2

## Decision Process
Think step by step:
1. What is being requested?
2. Quick assessment: Are there obvious issues?
3. Which specialist should handle this?

## Example

Request: "Check system health"

Step 1: This is a health check request
Step 2: Let me scan for issues... Found 2 problems
Step 3: Need Specialist1 for detailed analysis

Action: handoff_to_agent("specialist1", "Found 2 problems, need analysis")

## Available Specialists
- specialist1: Handles X type tasks
- specialist2: Handles Y type tasks

## Output Format
Always respond with JSON:
{
    "assessment": "brief summary",
    "severity": "low|medium|high",
    "delegate_to": "agent_name or null",
    "context": "information for next agent"
}
"""
```

## Deployment

### GitOps Structure

Create manifests in `gitops/apps/ai-agents/<agent-name>/`:

```yaml
# kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - rbac.yaml
```

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-agent
  namespace: ai-agents
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: my-agent
  template:
    metadata:
      labels:
        app.kubernetes.io/name: my-agent
    spec:
      serviceAccountName: my-agent
      containers:
        - name: worker
          image: registry.almckay.io/my-agent:latest
          env:
            - name: TEMPORAL_HOST
              value: temporal-frontend.temporal.svc.cluster.local:7233
            - name: VLLM_API_URL
              value: http://llm-api.vllm.svc.cluster.local:8000/v1
            - name: DISCORD_WEBHOOK_URL
              valueFrom:
                secretKeyRef:
                  name: my-agent-secrets
                  key: discord-webhook-url
```

### Add to Flux

Edit `gitops/apps/ai-agents/kustomization.yaml`:

```yaml
resources:
  - ./k8s-monitor
  - ./my-agent  # Add your agent
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TEMPORAL_HOST` | Temporal server | `temporal-frontend.temporal.svc.cluster.local:7233` |
| `VLLM_API_URL` | vLLM API endpoint | `http://llm-api.vllm.svc.cluster.local:8000/v1` |
| `VLLM_MODEL` | Model to use | `Qwen/Qwen3-30B-A3B` |
| `DISCORD_WEBHOOK_URL` | Discord webhook | (from secret) |
| `KUBERNETES_MCP_SERVER_URL` | MCP server for K8s | `http://kubernetes-mcp-server.ai-agents.svc.cluster.local:8080/sse` |

## Best Practices

### Agent Design

1. **Single responsibility**: Each agent should have one clear purpose
2. **Clear handoff rules**: Define when to delegate vs handle locally
3. **Structured outputs**: Use JSON for predictable parsing
4. **Chain-of-thought**: Guide reasoning with step-by-step prompts

### Tools

1. **Idempotent**: Same inputs = same outputs
2. **Well-documented**: Docstrings are shown to the LLM
3. **Error handling**: Return useful error messages
4. **Typed**: Use type hints for parameters

### Testing

1. **Unit test tools**: Test tools in isolation
2. **Mock external services**: K8s, LLM, Discord
3. **Test agent creation**: Ensure agents instantiate correctly
4. **Integration tests**: Test swarm flows with mocks

### Swarm Design

1. **Clear entry point**: One agent receives all requests
2. **Guardrails**: Set max_handoffs, timeouts
3. **Avoid loops**: Use repetitive_handoff_detection
4. **End conditions**: Ensure swarms terminate

## Troubleshooting

### Build Issues

```bash
# Core-agents wheel not found
earthly +core-agents  # Build it first

# Import errors
uv sync  # Reinstall dependencies
```

### Runtime Issues

```bash
# Check pod status
kubectl get pods -n ai-agents -l app.kubernetes.io/name=my-agent

# Check logs
kubectl logs -n ai-agents -l app.kubernetes.io/name=my-agent

# Debug in pod
kubectl exec -it -n ai-agents deploy/my-agent -- /bin/bash
```

### Swarm Issues

```bash
# Swarm timing out
# - Check node_timeout and execution_timeout
# - Look for infinite handoff loops in logs

# Agent not receiving handoffs
# - Verify agent name matches exactly
# - Check agent is in swarm agent list
```
