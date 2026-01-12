# Kubani Development Guide

This guide covers the enhanced development workflow for Kubani agents, including local development, evaluation, continuous learning, and deployment.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Configuration Management](#configuration-management)
3. [Local Development](#local-development)
4. [Agent Evaluation](#agent-evaluation)
5. [Continuous Learning](#continuous-learning)
6. [Registry Synchronization](#registry-synchronization)
7. [Deployment](#deployment)
8. [News Monitor Features](#news-monitor-features)

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (for local services)
- kubectl (configured for cluster access)
- Access to the kubani cluster (optional, for cluster connectivity)

### Installation

```bash
# Clone the repository
git clone https://github.com/X-McKay/kubani.git
cd kubani

# Install kubani-dev CLI
cd tools/kubani-dev
pip install -e .

# Initialize configuration
kubani-dev init
```

### Running an Agent Locally

```bash
# Simple local run with mocked services
kubani-dev run k8s-monitor --mock-mcp --mock-redis

# Local run with cluster connectivity
kubani-dev local-run k8s-monitor --tunnel --temporal=cluster --output=both
```

---

## Configuration Management

### Unified Configuration System

Kubani uses a hierarchical configuration system that supports multiple environments:

```
config.default.yaml    # Base configuration (committed)
config.production.yaml # Production overrides (committed)
config.local.yaml      # Local overrides (gitignored)
```

### Configuration Hierarchy

1. **Environment Variables** (highest priority)
2. **config.local.yaml** (local overrides)
3. **config.{environment}.yaml** (environment-specific)
4. **config.default.yaml** (base defaults)

### Example Configuration

```yaml
# config.local.yaml
environment: development

services:
  redis:
    host: localhost
    port: 6379
  
  qdrant:
    host: localhost
    port: 6333
  
  neo4j:
    uri: bolt://localhost:7687

temporal:
  host: localhost
  port: 7233
  namespace: kubani-dev

llm:
  provider: vllm
  api_url: http://localhost:8000/v1
  model: nvidia/Qwen3-14B-FP4

discord:
  enabled: false  # Disable for local development
```

### Using Configuration in Code

```python
from core_agents.config_unified import get_config

config = get_config()

# Access nested configuration
redis_host = config.services.redis.host
llm_model = config.llm.model
```

---

## Local Development

### The `local-run` Command

The `kubani-dev local-run` command provides seamless local development with cluster connectivity:

```bash
kubani-dev local-run <agent> [OPTIONS]

Options:
  --temporal [local|cluster]    Where to run Temporal (default: local)
  --output [console|discord|both]  Where to route output (default: console)
  --tunnel/--no-tunnel          Enable tunnel to cluster services
  --tunnel-method [telepresence|kubectl-forward]  Tunneling method
```

### Examples

```bash
# Pure local development (no cluster)
kubani-dev local-run k8s-monitor

# Local with cluster services (memory, cache)
kubani-dev local-run k8s-monitor --tunnel

# Full cluster integration with Discord output
kubani-dev local-run k8s-monitor --tunnel --temporal=cluster --output=both
```

### How Tunneling Works

When `--tunnel` is enabled:

1. **kubectl-forward** (default): Creates port forwards for each service
   - Redis: localhost:6379 → redis.kubani.svc:6379
   - Qdrant: localhost:6333 → qdrant.kubani.svc:6333
   - Neo4j: localhost:7687 → neo4j.kubani.svc:7687

2. **telepresence**: Full network integration with the cluster
   - Requires Telepresence to be installed
   - Provides full DNS resolution for cluster services

---

## Agent Evaluation

### Evaluation Framework

Kubani includes a comprehensive evaluation framework based on [Anthropic's best practices](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).

### Evaluation Suites

Evaluations are defined in YAML files under `evaluations/`:

```yaml
# evaluations/k8s/pod_remediation.yaml
name: K8s Pod Remediation
description: Evaluate k8s-monitor's ability to diagnose and remediate pod failures
version: "1.0"
agent: k8s-monitor

test_cases:
  - id: crashloopbackoff_oom
    name: CrashLoopBackOff - OOM Kill
    description: Pod crashing due to memory limits
    input:
      scenario: crashloopbackoff
      pod_name: test-app
      namespace: default
      events:
        - type: Warning
          reason: OOMKilled
          message: Container killed due to OOM
    expected:
      diagnosis_contains:
        - "memory"
        - "OOM"
      action_type: increase_memory_limit
    scoring:
      diagnosis_accuracy:
        weight: 0.4
        type: llm_judge
      action_appropriateness:
        weight: 0.3
        type: llm_judge
      response_time:
        weight: 0.2
        type: threshold
        threshold_ms: 5000
      safety:
        weight: 0.1
        type: automated
```

### Running Evaluations

```bash
# Run all evaluations for an agent
kubani-dev eval k8s-monitor

# Run a specific suite
kubani-dev eval k8s-monitor --suite pod_remediation

# Run with parallel jobs
kubani-dev eval k8s-monitor --parallel 4

# Output to specific directory
kubani-dev eval k8s-monitor --output ./my-results
```

### Evaluation Types

1. **Automated Checks**: Syntax validation, type checking, safety rules
2. **LLM-as-Judge**: Uses an LLM to evaluate quality of responses
3. **Threshold-based**: Performance metrics against defined thresholds
4. **Human Review**: Generates reports for manual review

### Viewing Results

Results are saved to `eval-results/<agent>/` with:
- `summary.json`: Overall scores and metrics
- `detailed.json`: Per-test-case results
- `report.md`: Human-readable report

---

## Continuous Learning

### Voyager-Inspired Learning System

Kubani implements an advanced continuous learning system inspired by [Voyager](https://github.com/MineDojo/Voyager):

```
┌─────────────────────────────────────────────────────────────────┐
│                    Learning System Architecture                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Critic     │───▶│  Reflection  │───▶│ Synthesizer  │      │
│  │   Agent      │    │    Agent     │    │              │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                   │                   │               │
│         ▼                   ▼                   ▼               │
│  ┌──────────────────────────────────────────────────────┐      │
│  │              Shared Memory System                     │      │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐              │      │
│  │  │ Qdrant  │  │  Neo4j  │  │  Redis  │              │      │
│  │  │ Vector  │  │  Graph  │  │  Cache  │              │      │
│  │  └─────────┘  └─────────┘  └─────────┘              │      │
│  └──────────────────────────────────────────────────────┘      │
│                            │                                    │
│                            ▼                                    │
│  ┌──────────────────────────────────────────────────────┐      │
│  │              Discord Approval Workflow                │      │
│  │  📝 Proposed Skill → 👍 Approve → 🚀 Deploy          │      │
│  └──────────────────────────────────────────────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Components

#### Critic Agent
Evaluates agent execution quality:
- Analyzes task completion success/failure
- Identifies improvement opportunities
- Provides structured feedback

#### Reflection Agent
Synthesizes learnings across agents:
- Monitors interaction logs
- Identifies patterns and insights
- Stores knowledge in shared memory

#### Skill Synthesizer
Proposes new skills:
- Analyzes successful patterns
- Generates skill definitions
- Posts proposals to Discord for approval

### Discord Approval Workflow

1. Learning system identifies improvement opportunity
2. Skill Synthesizer generates proposed skill
3. Proposal posted to `#skill-proposals` channel
4. Team reviews and reacts:
   - ✅ Approve: Skill is deployed
   - ❌ Reject: Skill is discarded
   - 🔄 Revise: Feedback provided for iteration

### Shared Memory System

All agents share a common memory system:

```python
from core_agents.memory.shared import SharedMemorySystem

memory = SharedMemorySystem()

# Store a learning
await memory.store_learning(
    agent_id="k8s-monitor",
    learning_type="pattern",
    content="OOM kills often indicate need for vertical scaling",
    context={"namespace": "production", "frequency": "high"},
    confidence=0.85,
)

# Query learnings
learnings = await memory.query_learnings(
    query="memory issues kubernetes",
    agent_id=None,  # All agents
    min_confidence=0.7,
)

# Store cross-agent knowledge
await memory.store_knowledge(
    topic="kubernetes/memory-management",
    content="Best practices for K8s memory limits...",
    source="reflection-agent",
    related_topics=["kubernetes/resources", "kubernetes/oom"],
)
```

---

## Registry Synchronization

### Automatic Sync

The registry automatically syncs with:
- Git repository (skills/, agents/)
- Deployed agents (heartbeats)
- vLLM model endpoints

### Manual Sync

```bash
# Sync skills from Git to registry
kubani-dev skills sync

# Full bidirectional sync
kubani-dev registry sync --bidirectional
```

### Bidirectional Sync

When skills are approved via the UI, they can be synced back to Git:

1. Skill approved in UI
2. Registry marks skill as `pending_git_sync`
3. Sync process creates PR with new skill
4. PR merged after review

---

## Deployment

### The `deploy` Command

```bash
kubani-dev deploy <target> [OPTIONS]

Targets:
  k8s-monitor    Deploy k8s-monitor agent
  news-monitor   Deploy news-monitor agent
  registry       Deploy registry service
  ui             Deploy UI
  all            Deploy everything

Options:
  --version, -v TEXT      Version/tag to deploy
  --force, -f             Force deployment
  --skip-verification     Skip health checks
  --dry-run              Show what would be deployed
```

### Deployment Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      Deployment Pipeline                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. kubani-dev deploy k8s-monitor                               │
│         │                                                        │
│         ▼                                                        │
│  2. Trigger GitHub Actions                                       │
│     ┌─────────────────────────────────────┐                     │
│     │ 📦 Build → 🧪 Test → 📤 Push Image │                     │
│     └─────────────────────────────────────┘                     │
│         │                                                        │
│         ▼                                                        │
│  3. Request Deployment from Cluster Controller                   │
│     ┌─────────────────────────────────────┐                     │
│     │ 🔄 Apply → 🚀 Rollout → 🔍 Verify  │                     │
│     └─────────────────────────────────────┘                     │
│         │                                                        │
│         ▼                                                        │
│  4. Health Verification                                          │
│     ┌─────────────────────────────────────┐                     │
│     │ ✅ Success  OR  ⏪ Auto-Rollback    │                     │
│     └─────────────────────────────────────┘                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Example Deployment

```bash
$ kubani-dev deploy k8s-monitor

🚀 Starting deployment of k8s-monitor...
📦 Triggering build workflow...
   Build workflow started: 12345678
   ✅ Build completed successfully
🔄 Requesting deployment from cluster...
   ⏳ Pending
   🔄 Triggering
   🚀 Deploying
   🔍 Verifying
✅ Deployment completed successfully!
```

### CI/CD Architecture

Since GitHub Actions doesn't have cluster access, we use a cluster-side controller:

1. **GitHub Actions**: Builds and pushes images
2. **Cluster Controller**: Handles deployment, monitoring, verification
3. **Registry**: Coordinates between CLI and controller

---

## News Monitor Features

### Executive Brief Format

The news-monitor now produces executive-style digests:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📰 AI/ML EXECUTIVE BRIEF
January 11, 2026 | 5-Minute Read
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 MARKET PULSE
• AI infrastructure spending up 23% YoY
• Inference costs down 40% with new quantization
• Enterprise adoption accelerating in healthcare

🔬 DEEP DIVES

1️⃣ Anthropic Releases Claude 4
   Impact: Major advancement in reasoning capabilities
   Action: Evaluate for production workloads
   [Read more](https://...)

2️⃣ vLLM 0.8 Performance Improvements
   Impact: 2x throughput on multi-GPU setups
   Action: Plan upgrade for inference cluster
   [Read more](https://...)

React: 👍 Valuable | 📖 Learn more | 🎯 Actionable | 👎 Not relevant
```

### Breaking News Channel

Urgent news is posted immediately to a dedicated channel:

```
🚨 BREAKING: Critical Vulnerability in LangChain

*Remote code execution vulnerability discovered in document loaders*

**Source:** GitHub Security Advisory
**Urgency:** Affects all versions < 0.1.0

⚡ **Action Required:** Upgrade immediately or disable document loaders

[Read more](https://...)

React: 🔥 Important | 👀 Following | ❓ Need more info
```

### Emoji Feedback Learning

The news-monitor learns from emoji reactions:

| Emoji | Meaning | Learning Signal |
|-------|---------|-----------------|
| 👍 🔥 | Valuable | Boost similar topics |
| 📖 💡 | Want to learn more | Request deep dives |
| 🎯 ✅ | Actionable | Prioritize practical content |
| 🤔 ❓ | Confusing | Improve explanations |
| 👎 | Not relevant | Filter similar content |

---

## Best Practices

### Local Development

1. **Start with mocked services** for rapid iteration
2. **Enable tunneling** only when testing integration
3. **Use console output** for debugging, Discord for demos
4. **Run evaluations** before pushing changes

### Evaluation

1. **Write test cases** for new skills
2. **Include edge cases** in evaluation suites
3. **Review LLM-judge feedback** for insights
4. **Track metrics over time** to detect regressions

### Deployment

1. **Always use `--dry-run`** first
2. **Deploy to staging** before production
3. **Monitor logs** during rollout
4. **Have rollback plan** ready

---

## Troubleshooting

### Common Issues

**Tunnel connection failed**
```bash
# Check kubectl context
kubectl config current-context

# Verify cluster access
kubectl get pods -n kubani
```

**Temporal connection refused**
```bash
# Start local Temporal
docker-compose up -d temporal

# Or use cluster Temporal
kubani-dev local-run <agent> --temporal=cluster --tunnel
```

**Registry sync failed**
```bash
# Check registry health
curl http://localhost:8000/health

# Manual sync
kubani-dev skills sync --force
```

---

## Further Reading

- [Anthropic: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [Voyager: An Open-Ended Embodied Agent](https://github.com/MineDojo/Voyager)
- [Kubani Architecture Documentation](./ARCHITECTURE.md)
