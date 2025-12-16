# Kubernetes Monitoring Agent

An AI-powered agent that monitors cluster health and posts summaries to Discord.

## Overview

This agent uses:
- **Strands Agents SDK** for LLM-powered analysis
- **Temporal** for durable workflow execution
- **vLLM** for local LLM inference
- **Kubernetes Python client** for cluster inspection

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Temporal Server                          │
│  ┌─────────────────────────────────────────────────────────┐│
│  │           ScheduledHealthCheckWorkflow                  ││
│  │                      │                                   ││
│  │                      ▼                                   ││
│  │          ClusterHealthCheckWorkflow                      ││
│  │            │                    │                        ││
│  │            ▼                    ▼                        ││
│  │  collect_and_analyze()   post_to_discord()              ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                    │                    │
                    ▼                    ▼
            ┌───────────────┐    ┌───────────────┐
            │ Strands Agent │    │   Discord     │
            │   + Tools     │    │   Webhook     │
            └───────────────┘    └───────────────┘
                    │
                    ▼
            ┌───────────────┐
            │    vLLM       │
            │   (local)     │
            └───────────────┘
```

## Components

### Tools (`tools.py`)
Kubernetes inspection tools decorated with `@tool`:
- `get_node_status()` - Node health and capacity
- `get_pod_status_summary()` - Pod phases by namespace
- `get_recent_events()` - Cluster warnings and errors
- `get_deployment_status()` - Deployment health
- `get_resource_usage()` - CPU/memory requests
- `get_pvc_status()` - Storage status

### Agent (`agent.py`)
Strands agent configured with the K8s tools and a system prompt
that instructs it to analyze cluster health and generate summaries.

### Activities (`activities.py`)
Temporal activities that wrap the agent and Discord posting:
- `collect_and_analyze_cluster()` - Run the Strands agent
- `post_to_discord()` - Post results via webhook

### Workflows (`workflows.py`)
Temporal workflows for orchestration:
- `ClusterHealthCheckWorkflow` - Single health check
- `ScheduledHealthCheckWorkflow` - Hourly recurring checks

### Worker (`worker.py`)
Entry point that runs the Temporal worker:
```bash
# Run as worker (polls for tasks)
k8s-monitor-worker worker

# Start scheduled workflow
k8s-monitor-worker schedule

# Run single check (testing)
k8s-monitor-worker check
```

## Local Development

```bash
# Install dependencies
cd agents/k8s-monitor
pip install -e .

# Port-forward Temporal and vLLM
kubectl port-forward -n temporal svc/temporal-frontend 7233:7233 &
kubectl port-forward -n vllm svc/llm-api 8000:8000 &

# Set environment
export TEMPORAL_HOST=localhost:7233
export VLLM_API_URL=http://localhost:8000/v1
export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Run a single check
python -m k8s_monitor.worker check
```

## Deployment

The agent is deployed via GitOps (Flux). Manifests in:
- `gitops/apps/ai-agents/k8s-monitor/`

Key resources:
- **Deployment**: Runs the Temporal worker
- **Job**: Starts the scheduled workflow on deployment
- **RBAC**: ClusterRole with read-only K8s access
- **Secret**: Discord webhook URL (encrypted with SOPS)

## Building the Image

```bash
# From repo root
docker build -f agents/k8s-monitor/Dockerfile -t k8s-monitor .

# Push to registry
docker tag k8s-monitor ghcr.io/almckay/kubani/k8s-monitor:latest
docker push ghcr.io/almckay/kubani/k8s-monitor:latest
```

## Configuration

Environment variables:
| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPORAL_HOST` | `temporal-frontend.temporal.svc.cluster.local:7233` | Temporal server address |
| `TEMPORAL_NAMESPACE` | `default` | Temporal namespace |
| `VLLM_API_URL` | `http://llm-api.vllm.svc.cluster.local:8000/v1` | vLLM API endpoint |
| `VLLM_MODEL` | `openai/gpt-oss-20b` | Model to use |
| `DISCORD_WEBHOOK_URL` | (required) | Discord webhook for notifications |
| `HEALTH_CHECK_INTERVAL_HOURS` | `1` | Hours between health checks |
