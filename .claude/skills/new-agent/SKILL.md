---
name: new-agent
description: Create a new AI agent from template using kubani-dev CLI. Use when adding a new agent to the cluster, starting a new monitoring or automation project.
---

# Create New AI Agent

Scaffold a new AI agent using kubani-dev CLI or manual setup.

## Quick Start (Recommended)

```bash
# Create agent with default template
kubani-dev new my-agent

# Create with federated template (includes Sentinel, Healer, Explorer)
kubani-dev new my-agent --template federated

# Create minimal agent
kubani-dev new my-agent --template minimal
```

## Arguments

- `agent-name`: Name for the new agent (lowercase, hyphenated)
- `--template`: Template type (default, federated, minimal)

## Templates

### Default Template
Standard agent with:
- Temporal worker setup
- Basic activities and workflows
- Test structure
- GitOps manifests

### Federated Template
Advanced agent with:
- Federated agents (Sentinel, Healer, Explorer)
- Triage Graph workflow
- A2A communication
- Continuous learning integration

### Minimal Template
Lightweight agent with:
- Basic worker
- Single activity
- Minimal dependencies

## Manual Creation

If you need to create an agent manually:

### 1. Create Directory Structure

```bash
cd /home/al/git/kubani
AGENT_NAME="my-agent"

mkdir -p agents/${AGENT_NAME}/{src/${AGENT_NAME//-/_},tests}
```

### 2. Create pyproject.toml

```toml
[project]
name = "${AGENT_NAME}"
version = "0.1.0"
description = "Description of what this agent does"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "strands-agents>=1.20.0",
    "temporalio>=1.7.0",
    "httpx>=0.27.0",
    "pydantic>=2.5.0",
    "openai>=1.0.0",
    "core-agents",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.8.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/${AGENT_NAME//-/_}"]

[tool.uv.sources]
core-agents = { path = "../core", editable = true }
```

### 3. Create Worker with AgentFactory

Create `src/${AGENT_NAME//-/_}/worker.py`:

```python
from strands import AgentConfig, get_agent_factory
from kubani.framework.worker import AgentWorker, AgentWorkerConfig

def create_worker() -> AgentWorker:
    config = AgentWorkerConfig(
        task_queue="my-agent",
        name="my-agent",
        description="My agent description",
        workflows=[MyWorkflow],
        activities=[my_activity],
    )
    return AgentWorker(config)

def main() -> None:
    worker = create_worker()
    worker.run()

if __name__ == "__main__":
    main()
```

### 4. Create agent_info.py

```python
from kubani.framework.communication import AgentCapability, AgentInfo

AGENT_INFO = AgentInfo(
    id="my-agent",
    name="My Agent",
    description="What it does",
    endpoint="my-agent.ai-agents.svc.cluster.local",
    capabilities=[
        AgentCapability(
            name="my-capability",
            description="What it does",
            tags=["my", "tags"],
        ),
    ],
)
```

### 5. Create GitOps Manifests

```bash
mkdir -p gitops/apps/ai-agents/${AGENT_NAME}
```

Create deployment.yaml, service.yaml, kustomization.yaml.

### 6. Register with Flux

Add to `gitops/apps/ai-agents/kustomization.yaml`:
```yaml
resources:
  - ${AGENT_NAME}
```

## Development Workflow

After creating the agent:

```bash
# Run locally with hot-reload
kubani-dev run my-agent --hot-reload

# Run tests
kubani-dev test my-agent

# Run evaluation
kubani-dev eval my-agent

# Build and deploy
kubani-dev build my-agent
kubani-dev deploy my-agent
```

## Reference Agents

- **k8s-monitor**: Full federated agent with Sentinel, Healer, Explorer
- **news-monitor**: Temporal workflows with personalization
- **core**: Shared library with all utilities
