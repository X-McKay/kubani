# Agent Development Guide

This guide covers creating, testing, and deploying AI agents in the Kubani cluster.

## Quick Start

Create a new agent using the template:

```bash
# Interactive mode
mise run new-agent

# Or with Copier directly
copier copy templates/agent agents/
```

Or use Claude Code:
```
/new-agent
```

## Architecture Overview

```
agents/
├── k8s-monitor/              # Example agent
│   ├── pyproject.toml        # Dependencies
│   ├── Earthfile             # Build configuration
│   ├── src/k8s_monitor/      # Source code
│   │   ├── agent.py          # Agent configuration
│   │   ├── worker.py         # Entry point
│   │   ├── tools.py          # AI tools (functions)
│   │   ├── activities.py     # Temporal activities
│   │   ├── workflows.py      # Temporal workflows
│   │   └── models.py         # Pydantic models
│   └── tests/                # Test suite

agent_platform/               # Shared utilities
├── llm_client.py             # vLLM integration
├── temporal_helpers.py       # Temporal setup helpers
└── discord.py                # Discord notifications

gitops/apps/ai-agents/        # Kubernetes manifests
└── k8s-monitor/
    ├── deployment.yaml
    ├── rbac.yaml
    ├── secret.enc.yaml
    └── kustomization.yaml
```

## Core Components

### 1. Tools (tools.py)

Tools are functions that the AI agent can call. They use the Strands Agents SDK:

```python
from strands import tool

@tool
def get_pod_status(namespace: str = "default") -> str:
    """Get the status of all pods in a namespace.

    Args:
        namespace: The Kubernetes namespace to query

    Returns:
        A formatted string with pod status information
    """
    from kubernetes import client

    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(namespace)

    results = []
    for pod in pods.items:
        results.append(f"{pod.metadata.name}: {pod.status.phase}")

    return "\n".join(results)
```

### 2. Agent (agent.py)

The agent combines tools with an LLM:

```python
from strands import Agent
from agent_platform import get_llm_client
from .tools import get_pod_status, describe_pod, get_logs

def create_agent() -> Agent:
    """Create the agent with configured tools."""
    return Agent(
        model=get_llm_client(),
        tools=[get_pod_status, describe_pod, get_logs],
        system_prompt="""You are a Kubernetes operations agent.
        Analyze cluster health and provide actionable insights."""
    )
```

### 3. Workflows (workflows.py)

Temporal workflows orchestrate long-running operations:

```python
from temporalio import workflow
from datetime import timedelta

@workflow.defn
class MonitorWorkflow:
    @workflow.run
    async def run(self) -> str:
        # Run analysis activity
        result = await workflow.execute_activity(
            analyze_cluster,
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Send notification if issues found
        if result.status != "healthy":
            await workflow.execute_activity(
                send_notification,
                args=[result],
                start_to_close_timeout=timedelta(seconds=30),
            )

        return result.summary
```

### 4. Activities (activities.py)

Activities wrap side effects (API calls, I/O):

```python
from temporalio import activity

@activity.defn
async def analyze_cluster() -> AnalysisResult:
    """Run the AI agent to analyze cluster health."""
    from .agent import create_agent

    agent = create_agent()
    response = agent("Analyze the current cluster health")

    return AnalysisResult(
        summary=response,
        status=determine_status(response),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
```

### 5. Worker (worker.py)

The worker is the entry point:

```python
import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from agent_platform import create_temporal_client

from .workflows import MonitorWorkflow
from .activities import analyze_cluster, send_notification

async def run_worker():
    client = await create_temporal_client()

    worker = Worker(
        client,
        task_queue="k8s-monitor-tasks",
        workflows=[MonitorWorkflow],
        activities=[analyze_cluster, send_notification],
    )

    await worker.run()

if __name__ == "__main__":
    asyncio.run(run_worker())
```

## Building and Testing

### Local Development

```bash
cd agents/my-agent

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run linting
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

### Earthly Builds

```bash
# Build Docker image
earthly ./agents/my-agent+docker

# Run tests in container
earthly ./agents/my-agent+test

# Run linting in container
earthly ./agents/my-agent+lint

# Push to registry
earthly --push ./agents/my-agent+push
```

### Using mise Tasks

```bash
# Build all agents
mise run build-all

# Test all agents
mise run test-agents

# Full CI pipeline
mise run ci
```

## Testing Patterns

### Mocking Kubernetes Client

```python
from unittest.mock import patch, MagicMock

def test_get_pod_status():
    with patch("my_agent.tools.client") as mock_client:
        # Setup mock
        mock_pod = MagicMock()
        mock_pod.metadata.name = "test-pod"
        mock_pod.status.phase = "Running"

        mock_api = MagicMock()
        mock_api.list_namespaced_pod.return_value.items = [mock_pod]
        mock_client.CoreV1Api.return_value = mock_api

        # Test
        result = get_pod_status("default")

        assert "test-pod: Running" in result
```

### Testing Temporal Workflows

```python
import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

@pytest.mark.asyncio
async def test_workflow():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[MonitorWorkflow],
            activities=[analyze_cluster, send_notification],
        ):
            result = await env.client.execute_workflow(
                MonitorWorkflow.run,
                id="test-workflow",
                task_queue="test-queue",
            )

            assert result is not None
```

## Deployment

### GitOps Structure

Each agent needs these files in `gitops/apps/ai-agents/<agent-name>/`:

1. **kustomization.yaml**: Lists resources
2. **deployment.yaml**: Kubernetes Deployment
3. **rbac.yaml**: ServiceAccount and RBAC rules
4. **secret.enc.yaml**: SOPS-encrypted secrets (optional)

### Adding to Flux

Edit `gitops/apps/ai-agents/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ./k8s-monitor
  - ./my-new-agent  # Add your agent
```

### Encrypting Secrets

```bash
cd gitops/apps/ai-agents/my-agent

# Create secret YAML
cat > secret.yaml << EOF
apiVersion: v1
kind: Secret
metadata:
  name: my-agent-secrets
  namespace: ai-agents
type: Opaque
stringData:
  discord-webhook-url: "https://discord.com/api/webhooks/..."
EOF

# Encrypt with SOPS
sops --encrypt --age $(cat /home/al/git/kubani/age.pub) secret.yaml > secret.enc.yaml

# Remove unencrypted file
rm secret.yaml
```

### Verifying Deployment

```bash
# Check pod status
KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents

# Check logs
KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents -l app.kubernetes.io/name=my-agent

# Check Temporal workflows
# Open Temporal UI at http://temporal.almckay.io
```

## CI/CD

GitHub Actions automatically:

1. **On Pull Request**: Runs tests and linting
2. **On Push to Main**: Builds and pushes Docker images
3. **On Tag**: Creates release and updates GitOps manifests

See `.github/workflows/test.yml` and `.github/workflows/build.yml`.

## Environment Variables

Common environment variables for agents:

| Variable | Description | Example |
|----------|-------------|---------|
| `TEMPORAL_HOST` | Temporal server address | `temporal-frontend.temporal.svc.cluster.local:7233` |
| `TEMPORAL_NAMESPACE` | Temporal namespace | `default` |
| `VLLM_API_URL` | vLLM API endpoint | `http://llm-api.vllm.svc.cluster.local:8000/v1` |
| `VLLM_MODEL` | Model to use | `openai/gpt-oss-20b` |
| `DISCORD_WEBHOOK_URL` | Discord webhook for notifications | (from secret) |

## Best Practices

1. **Tools should be idempotent**: Same inputs = same outputs
2. **Use activities for side effects**: External APIs, I/O, state changes
3. **Keep workflows deterministic**: No random, no time, no external calls
4. **Test with mocks**: Mock K8s client, LLM, external services
5. **Log appropriately**: Use structured logging for debugging
6. **Handle errors gracefully**: Activities should catch and report errors
7. **Set appropriate timeouts**: Prevent hung workflows

## Troubleshooting

### Agent not starting

```bash
# Check pod events
kubectl describe pod -n ai-agents -l app.kubernetes.io/name=my-agent

# Check container logs
kubectl logs -n ai-agents -l app.kubernetes.io/name=my-agent --previous
```

### Workflow not executing

```bash
# Check Temporal worker is connected
# Open Temporal UI and check task queue workers

# Check workflow history
# Use Temporal UI or tctl
```

### Permission denied errors

```bash
# Verify RBAC
kubectl auth can-i list pods --as=system:serviceaccount:ai-agents:my-agent

# Check ClusterRoleBinding
kubectl get clusterrolebinding my-agent-role-binding -o yaml
```
