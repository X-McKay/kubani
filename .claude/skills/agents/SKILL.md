---
name: agents
description: Manage and develop AI agents using kubani-dev CLI. Use for checking agent health, versions, deployment status, running tests, and evaluations.
---

# AI Agents Management

Manage AI agents using the kubani-dev CLI and cluster tools.

## Quick Commands

```bash
# Create a new agent automatically (NEW!)
kubani-dev agent draft --name my-agent --description "..."

# Check agent creation status
kubani-dev agent status my-agent

# List all agents with status
kubani-dev agents list

# Run agent locally with hot-reload
kubani-dev run k8s-monitor --hot-reload

# Run agent tests
kubani-dev test k8s-monitor

# Run evaluation suite
kubani-dev eval k8s-monitor

# View execution traces
kubani-dev trace k8s-monitor

# Start observability dashboard
kubani-dev dashboard
```

## Arguments

- `agent-name`: Optional specific agent name for detailed info

## Instructions

### List All Agents

```bash
cd /home/al/git/kubani
echo "=== AI Agents ==="
echo ""

for earthfile in agents/*/Earthfile; do
    agent_dir=$(dirname "$earthfile")
    agent_name=$(basename "$agent_dir")
    [ "$agent_name" = "core" ] && continue

    # Get version from pyproject.toml
    version=$(grep '^version = ' "$agent_dir/pyproject.toml" | sed 's/version = "\(.*\)"/\1/')

    # Get deployed image
    deployed=$(KUBECONFIG=/home/al/.kube/config kubectl get deploy $agent_name -n ai-agents -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "not deployed")

    # Get pod status
    status=$(KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app.kubernetes.io/name=$agent_name -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "unknown")

    echo "$agent_name"
    echo "  Source version: $version"
    echo "  Deployed image: $deployed"
    echo "  Pod status: $status"
    echo ""
done
```

### Development Workflow

Use kubani-dev for agent development:

```bash
# Initialize configuration (one-time)
kubani-dev init

# Run agent with hot-reload
kubani-dev run k8s-monitor --hot-reload

# Run with mock services (for offline development)
kubani-dev run k8s-monitor --mock-mcp --mock-redis

# Run tests
kubani-dev test k8s-monitor --coverage

# Run evaluation suite
kubani-dev eval k8s-monitor

# Run specific evaluation layer
kubani-dev eval k8s-monitor --layer llm
```

### Detailed Agent Info

For a specific agent, show detailed information:

```bash
AGENT_NAME="k8s-monitor"

# Pod details
KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app.kubernetes.io/name=$AGENT_NAME -o wide

# Recent logs
KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents -l app.kubernetes.io/name=$AGENT_NAME --tail=20

# Recent deployment history
git log --oneline -5 gitops/apps/ai-agents/$AGENT_NAME/deployment.yaml

# View traces
kubani-dev trace $AGENT_NAME --last 10

# View metrics
kubani-dev metrics $AGENT_NAME
```

### Build and Deploy

```bash
# Build agent container
kubani-dev build k8s-monitor

# Deploy to cluster
kubani-dev deploy k8s-monitor

# Rollback deployment
kubani-dev deploy k8s-monitor --rollback
```

### Create New Agent

```bash
# Create from default template
kubani-dev new my-agent

# Create with federated template
kubani-dev new my-agent --template federated
```

## Framework

The `kubani/framework/` package provides shared functionality:

```bash
# Key modules:
# - config.py: Unified configuration system
# - events/: Event bus with hybrid event types
# - mcp/: MCP client
# - llm.py: LLM integration
# - registry/: Service registry
```

## Architecture

```
kubani/
├── framework/                # Core framework
│   ├── config.py            # Unified configuration
│   ├── events/              # Event bus (hybrid types)
│   ├── mcp/                 # MCP client
│   └── registry/            # Service registry
├── agents/                   # Reusable agent implementations
│   ├── _base/               # Base agent class (KubaniAgent)
│   ├── critic/              # Execution evaluation (learning)
│   ├── reflection/          # Cross-agent insights (learning)
│   ├── skill_synthesizer/   # Skill proposal (learning)
│   ├── event_classifier/    # Event classification
│   ├── remediator/          # Remediation actions
│   └── ...                  # Other specialized agents
├── syndicates/               # Multi-agent orchestration
│   ├── _base/               # Base syndicate class
│   ├── k8s_monitor/         # Kubernetes monitoring
│   ├── news_digest/         # News aggregation
│   └── learning_system/     # Continuous learning (Critic + Reflection + Synthesizer)
└── mcp/servers/              # MCP server implementations
```

## Learning System

The continuous learning system runs as a syndicate (`kubani/syndicates/learning_system/`):

```python
from kubani.syndicates.learning_system import LearningSystemSyndicate
from kubani.agents.critic import CriticAgent
from kubani.agents.reflection import ReflectionAgent
from kubani.agents.skill_synthesizer import SkillSynthesizerAgent

# Run the full learning system
syndicate = LearningSystemSyndicate()
await syndicate.start()
```
