# Kubani Setup Guide

This guide explains how to set up the Kubani platform after the feature/manus-20260111 changes. It covers local development setup, Claude Code integration, Discord channel configuration, and cluster deployment.

## Prerequisites

Before starting, ensure you have the following installed:

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Agent development |
| Node.js | 22+ | UI development |
| Docker | Latest | Container builds |
| kubectl | Latest | Kubernetes access |
| Temporal CLI | Latest | Workflow debugging |
| mise | Latest | Tool version management |
| Claude Code | 1.0.33+ | AI-assisted development |

## Quick Setup

Run the automated setup script:

```bash
./MANUS_SETUP_SCRIPT.sh
```

This script will install dependencies, configure Claude Code, create Discord channels, and set up the development environment.

## Manual Setup Steps

### 1. Install Python Dependencies

```bash
# Install mise for tool management
curl https://mise.run | sh

# Install project tools
mise install

# Install Python dependencies
pip install -e agents/core
pip install -e tools/kubani-dev
pip install -e tools/temporal-mcp-server
pip install -e tools/qdrant-mcp-server
pip install -e tools/memory-mcp-server
pip install -e tools/discord-mcp-server
pip install -e tools/mcp-common
```

### 2. Configure Local Development

Create `config.local.yaml` in the project root:

```yaml
environment: development

# MCP Server URLs
mcp:
  temporal_url: http://localhost:8081
  qdrant_url: http://localhost:8082
  memory_url: http://localhost:8083
  discord_url: http://localhost:8084

# Temporal configuration
temporal:
  host: localhost:7233
  namespace: default
  enabled: true

# Memory services (via Tailscale)
memory:
  qdrant:
    host: qdrant.almckay.io
    port: 443
  neo4j:
    uri: bolt://neo4j.almckay.io:7687
  redis:
    host: redis.almckay.io
    port: 6379

# LLM configuration
llm:
  api_url: https://llm.almckay.io/v1
  model: nvidia/Qwen3-14B-FP4

# Local development settings
local_dev:
  enabled: true
  output_mode: console
  hot_reload: true
```

### 3. Configure Claude Code MCP Servers

Create or update `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "temporal": {
      "command": "temporal-mcp-server",
      "args": ["--mode", "stdio"],
      "env": {
        "TEMPORAL_HOST": "temporal.almckay.io:7233",
        "TEMPORAL_NAMESPACE": "kubani"
      }
    },
    "qdrant": {
      "command": "qdrant-mcp-server",
      "args": ["--mode", "stdio"],
      "env": {
        "QDRANT_HOST": "qdrant.almckay.io",
        "QDRANT_PORT": "443"
      }
    },
    "memory": {
      "command": "memory-mcp-server",
      "args": ["--mode", "stdio"],
      "env": {
        "QDRANT_HOST": "qdrant.almckay.io",
        "NEO4J_URI": "bolt://neo4j.almckay.io:7687",
        "REDIS_HOST": "redis.almckay.io",
        "EMBEDDINGS_API_URL": "https://embeddings.almckay.io/v1"
      }
    },
    "discord": {
      "command": "discord-mcp-server",
      "args": ["--mode", "stdio"],
      "env": {
        "DISCORD_BOT_TOKEN": "${DISCORD_BOT_TOKEN}",
        "DISCORD_GUILD_ID": "${DISCORD_GUILD_ID}"
      }
    },
    "kubernetes": {
      "command": "kubernetes-mcp-server",
      "args": ["--mode", "stdio"],
      "env": {
        "KUBECONFIG": "${HOME}/.kube/config"
      }
    }
  }
}
```

### 4. Configure Claude Code Hooks

Create `.claude/settings.json` for development automation hooks:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/session-start.sh"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/post-edit.sh",
            "timeout": 30
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Before stopping, verify: 1) All requested changes are complete, 2) Tests pass if code was modified, 3) No uncommitted changes that should be committed. If any issues, explain what needs to be done."
          }
        ]
      }
    ]
  }
}
```

Create the hooks directory and scripts:

```bash
mkdir -p .claude/hooks
```

Create `.claude/hooks/session-start.sh`:

```bash
#!/bin/bash
# Session start hook - runs when Claude Code starts

# Display project status
echo "=== Kubani Development Session ==="
echo "Environment: $(grep environment config.local.yaml 2>/dev/null | cut -d: -f2 | tr -d ' ')"
echo "Branch: $(git branch --show-current)"
echo "Last commit: $(git log -1 --oneline)"
echo ""

# Check for uncommitted changes
if [ -n "$(git status --porcelain)" ]; then
    echo "⚠️  Uncommitted changes detected"
    git status --short
fi
```

Create `.claude/hooks/post-edit.sh`:

```bash
#!/bin/bash
# Post-edit hook - runs after Write/Edit operations

FILE="$1"

# Run ruff on Python files
if [[ "$FILE" == *.py ]]; then
    ruff check --fix "$FILE" 2>/dev/null || true
    ruff format "$FILE" 2>/dev/null || true
fi

# Run type checking on modified Python files
if [[ "$FILE" == *.py ]]; then
    pyright "$FILE" 2>/dev/null || true
fi
```

Make hooks executable:

```bash
chmod +x .claude/hooks/*.sh
```

### 5. Set Up Discord Channels

Create the following Discord channels in your server:

| Channel | Purpose | Category |
|---------|---------|----------|
| `#kubani-alerts` | K8s monitor alerts and notifications | Kubani |
| `#ai-news` | News monitor digests | Kubani |
| `#ai-breaking-news` | Breaking news alerts | Kubani |
| `#kubani-learning` | Learning system proposals | Kubani |
| `#kubani-approvals` | Skill and modification approvals | Kubani |
| `#kubani-evaluations` | Evaluation results | Kubani |

After creating channels, update your environment or `config.local.yaml` with the channel IDs:

```bash
export DISCORD_ALERTS_CHANNEL="1234567890"
export DISCORD_DIGEST_CHANNEL="1234567891"
export DISCORD_BREAKING_NEWS_CHANNEL="1234567892"
export DISCORD_LEARNING_CHANNEL="1234567893"
export DISCORD_APPROVALS_CHANNEL="1234567894"
export DISCORD_EVALUATIONS_CHANNEL="1234567895"
```

### 6. Install VS Code Extensions (Optional)

The following extensions enhance the development experience:

```bash
# Python development
code --install-extension ms-python.python
code --install-extension ms-python.vscode-pylance
code --install-extension charliermarsh.ruff

# Configuration files
code --install-extension tamasfe.even-better-toml
code --install-extension redhat.vscode-yaml

# Kubernetes
code --install-extension ms-kubernetes-tools.vscode-kubernetes-tools
```

### 7. Verify Setup

Run the verification commands:

```bash
# Check tool versions
mise doctor

# Verify Python packages
python -c "from core_agents.config_unified import get_config; print(get_config())"

# Test MCP server connectivity
kubani-dev status

# Run tests
just test
```

## New Features Overview

### Unified Configuration System

Configuration now uses a hierarchical YAML system with pydantic-settings:

```
config.default.yaml    → Base defaults (committed)
config.production.yaml → Production overrides (committed)
config.local.yaml      → Local overrides (gitignored)
```

Environment variables override YAML with `KUBANI_` prefix:

```bash
export KUBANI_LLM__API_URL=http://localhost:8000/v1
export KUBANI_TEMPORAL__HOST=localhost:7233
```

### MCP Client Integration

Agents now use a unified MCP client:

```python
from core_agents.mcp import get_mcp_client

client = get_mcp_client()

# Temporal operations
await client.temporal.list_workflows()

# Memory operations
await client.memory.store_learning(...)

# Qdrant operations
await client.qdrant.search_vectors(...)

# Discord operations
await client.discord.send_message(...)
```

### Local Development Workflow

```bash
# Run agent locally with cluster services
kubani-dev local-run --agent k8s-monitor --temporal cluster --output console

# Run evaluations
kubani-dev eval run --suite evaluations/k8s/pod_remediation.yaml

# Deploy to cluster
kubani-dev deploy --agent k8s-monitor --wait
```

### Continuous Learning System

The Voyager-inspired learning system includes:

| Component | Purpose |
|-----------|---------|
| **Critic Agent** | Evaluates execution quality |
| **Reflection Agent** | Synthesizes cross-agent learnings |
| **Skill Synthesizer** | Proposes new skills |

Approval workflow uses Discord reactions:
- ✅ Approve
- ❌ Reject
- 🔄 Request revision

### News Monitor Enhancements

| Feature | Description |
|---------|-------------|
| **Executive Brief** | Structured 5-minute digest format |
| **Breaking News** | Urgent news to separate channel |
| **Emoji Feedback** | Learn from reactions (👍📖🎯👎) |

### Claude Code Hooks

The following hooks automate development tasks:

| Hook Event | Purpose |
|------------|---------|
| **SessionStart** | Display project status, check for uncommitted changes |
| **PostToolUse** | Auto-format Python code, run linting |
| **Stop** | Verify task completion before stopping |

## Cluster Deployment

### Deploy MCP Servers

```bash
# Apply MCP server manifests
kubectl apply -k gitops/apps/ai-agents/temporal-mcp-server/
kubectl apply -k gitops/apps/ai-agents/qdrant-mcp-server/
kubectl apply -k gitops/apps/ai-agents/memory-mcp-server/
```

### Deploy Learning Agent

```bash
# Create secrets first
kubectl create secret generic learning-agent-secrets \
  --from-literal=DISCORD_LEARNING_CHANNEL=$DISCORD_LEARNING_CHANNEL \
  --from-literal=DISCORD_APPROVALS_CHANNEL=$DISCORD_APPROVALS_CHANNEL \
  -n ai-agents

# Deploy
kubectl apply -k gitops/apps/ai-agents/learning-agent/
```

### Deploy All Components

```bash
# Deploy everything via Flux
kubectl apply -k gitops/apps/ai-agents/

# Or use kubani-dev
kubani-dev deploy --all --wait
```

## Troubleshooting

### MCP Server Connection Issues

```bash
# Check MCP server health
curl http://localhost:8081/health  # Temporal
curl http://localhost:8082/health  # Qdrant
curl http://localhost:8083/health  # Memory

# Check logs
kubani-dev logs temporal-mcp-server
```

### Configuration Issues

```bash
# Verify config loading
python -c "
from core_agents.config_unified import get_config
config = get_config()
print(f'Environment: {config.environment}')
print(f'Temporal: {config.temporal.host}')
print(f'LLM: {config.llm.api_url}')
"
```

### Claude Code Hook Issues

```bash
# Debug hooks by checking output
CLAUDE_DEBUG=1 claude

# Check hook script permissions
ls -la .claude/hooks/

# Test hook scripts manually
.claude/hooks/session-start.sh
```

### Test Failures


```bash
# Run tests with verbose output
just test -v

# Run specific test
pytest tests/test_config.py -v
```

## Architecture Decision Records

Key architectural decisions are documented in `docs/adr/`:

| ADR | Decision |
|-----|----------|
| [ADR-001](docs/adr/001-unified-configuration.md) | Unified Configuration System |
| [ADR-002](docs/adr/002-mcp-first-integration.md) | MCP-First Tool Integration |
| [ADR-003](docs/adr/003-voyager-learning-system.md) | Voyager-Inspired Learning System |
| [ADR-004](docs/adr/004-federated-agent-pattern.md) | Federated Agent Pattern |
| [ADR-005](docs/adr/005-registry-centric-architecture.md) | Registry-Centric Architecture |

## Next Steps

After setup is complete:

1. **Run local development**: `kubani-dev local-run --agent k8s-monitor`
2. **Run evaluations**: `kubani-dev eval run --suite evaluations/k8s/pod_remediation.yaml`
3. **Review learning proposals**: Check `#kubani-learning` channel
4. **Deploy changes**: `kubani-dev deploy --agent k8s-monitor --wait`

For more information, see:
- `docs/development/DEVELOPMENT_GUIDE.md` - Development workflow
- `docs/architecture/LEARNING_SYSTEM.md` - Learning system architecture
- `.claude/CLAUDE.md` - Claude Code guidance
- `docs/adr/` - Architecture decision records
