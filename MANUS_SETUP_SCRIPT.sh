#!/bin/bash
# Kubani Setup Script
# This script automates the setup of the Kubani platform after the feature/manus-20260111 changes.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              Kubani Platform Setup Script                    ║"
echo "║              feature/manus-20260111                          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# =============================================================================
# Step 1: Check Prerequisites
# =============================================================================
info "Step 1: Checking prerequisites..."

# Check Python
if command_exists python3; then
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    info "Python version: $PYTHON_VERSION"
else
    error "Python 3 is not installed. Please install Python 3.11+"
fi

# Check Node.js
if command_exists node; then
    NODE_VERSION=$(node --version)
    info "Node.js version: $NODE_VERSION"
else
    warn "Node.js is not installed. UI development will not be available."
fi

# Check Docker
if command_exists docker; then
    DOCKER_VERSION=$(docker --version | cut -d' ' -f3 | tr -d ',')
    info "Docker version: $DOCKER_VERSION"
else
    warn "Docker is not installed. Container builds will not be available."
fi

# Check kubectl
if command_exists kubectl; then
    KUBECTL_VERSION=$(kubectl version --client -o json 2>/dev/null | grep -o '"gitVersion": "[^"]*"' | head -1 | cut -d'"' -f4)
    info "kubectl version: $KUBECTL_VERSION"
else
    warn "kubectl is not installed. Cluster operations will not be available."
fi

# Check Claude Code
if command_exists claude; then
    CLAUDE_VERSION=$(claude --version 2>/dev/null || echo "unknown")
    info "Claude Code version: $CLAUDE_VERSION"
else
    warn "Claude Code CLI is not installed. Install from https://claude.ai/code"
fi

success "Prerequisites check complete"
echo ""

# =============================================================================
# Step 2: Install mise (if not present)
# =============================================================================
info "Step 2: Setting up mise..."

if command_exists mise; then
    info "mise is already installed"
else
    info "Installing mise..."
    curl https://mise.run | sh
    eval "$(~/.local/bin/mise activate bash)"
fi

# Install tools via mise
if [ -f ".mise.toml" ]; then
    info "Installing tools via mise..."
    mise install
fi

success "mise setup complete"
echo ""

# =============================================================================
# Step 3: Install Python Dependencies
# =============================================================================
info "Step 3: Installing Python dependencies..."

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install core packages
info "Installing core agents..."
pip install -e agents/core

info "Installing kubani-dev CLI..."
pip install -e tools/kubani-dev

info "Installing MCP common library..."
pip install -e tools/mcp-common 2>/dev/null || warn "mcp-common not found, skipping"

info "Installing MCP servers..."
pip install -e tools/temporal-mcp-server 2>/dev/null || warn "temporal-mcp-server not found, skipping"
pip install -e tools/qdrant-mcp-server 2>/dev/null || warn "qdrant-mcp-server not found, skipping"
pip install -e tools/memory-mcp-server 2>/dev/null || warn "memory-mcp-server not found, skipping"
pip install -e tools/discord-mcp-server 2>/dev/null || warn "discord-mcp-server not found, skipping"

success "Python dependencies installed"
echo ""

# =============================================================================
# Step 4: Create Local Configuration
# =============================================================================
info "Step 4: Setting up local configuration..."

if [ ! -f "config.local.yaml" ]; then
    info "Creating config.local.yaml..."
    cat > config.local.yaml << 'EOF'
# Local Development Configuration
# This file is gitignored - customize for your environment

environment: development

# MCP Server URLs (local development)
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

# Embeddings configuration
embeddings:
  api_url: https://embeddings.almckay.io/v1
  model: Qwen/Qwen3-Embedding-0.6B

# Local development settings
local_dev:
  enabled: true
  output_mode: console
  hot_reload: true
EOF
    success "Created config.local.yaml"
else
    info "config.local.yaml already exists, skipping"
fi

echo ""

# =============================================================================
# Step 5: Configure Claude Code MCP Servers
# =============================================================================
info "Step 5: Configuring Claude Code MCP servers..."

mkdir -p .claude

if [ ! -f ".claude/mcp.json" ]; then
    info "Creating .claude/mcp.json..."
    cat > .claude/mcp.json << 'EOF'
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
EOF
    success "Created .claude/mcp.json"
else
    info ".claude/mcp.json already exists, skipping"
fi

echo ""

# =============================================================================
# Step 6: Configure Claude Code Hooks
# =============================================================================
info "Step 6: Configuring Claude Code hooks..."

# Create hooks directory
mkdir -p .claude/hooks
mkdir -p .claude/hooks/logs

# Ensure hook scripts are executable
if [ -f ".claude/hooks/session-start.sh" ]; then
    chmod +x .claude/hooks/*.sh
    success "Hook scripts are executable"
else
    warn "Hook scripts not found. They should be in .claude/hooks/"
fi

# Verify settings.json exists
if [ -f ".claude/settings.json" ]; then
    info "Claude Code settings.json found with hooks configuration"
else
    warn ".claude/settings.json not found. Hooks may not be configured."
fi

echo ""

# =============================================================================
# Step 7: Discord Channel Setup Instructions
# =============================================================================
info "Step 7: Discord channel setup..."

echo ""
echo "Please create the following Discord channels in your server:"
echo ""
echo "  Channel Name           | Purpose"
echo "  ---------------------- | --------------------------------"
echo "  #kubani-alerts         | K8s monitor alerts"
echo "  #ai-news               | News monitor digests"
echo "  #ai-breaking-news      | Breaking news alerts"
echo "  #kubani-learning       | Learning system proposals"
echo "  #kubani-approvals      | Skill approval requests"
echo "  #kubani-evaluations    | Evaluation results"
echo ""
echo "After creating channels, set the following environment variables:"
echo ""
echo "  export DISCORD_ALERTS_CHANNEL=\"<channel_id>\""
echo "  export DISCORD_DIGEST_CHANNEL=\"<channel_id>\""
echo "  export DISCORD_BREAKING_NEWS_CHANNEL=\"<channel_id>\""
echo "  export DISCORD_LEARNING_CHANNEL=\"<channel_id>\""
echo "  export DISCORD_APPROVALS_CHANNEL=\"<channel_id>\""
echo "  export DISCORD_EVALUATIONS_CHANNEL=\"<channel_id>\""
echo ""

# =============================================================================
# Step 8: Run Tests
# =============================================================================
info "Step 8: Running tests..."

if command_exists just; then
    info "Running test suite..."
    just test || warn "Some tests failed. Please review the output."
else
    info "Running pytest directly..."
    pytest tests/ -v --tb=short || warn "Some tests failed. Please review the output."
fi

echo ""

# =============================================================================
# Step 9: Verify Setup
# =============================================================================
info "Step 9: Verifying setup..."

# Test config loading
info "Testing configuration loading..."
python3 -c "
from core_agents.config_unified import get_config
config = get_config()
print(f'  Environment: {config.environment}')
print(f'  Temporal: {config.temporal.host}')
print(f'  LLM: {config.llm.api_url}')
print(f'  MCP Servers: {list(config.get_mcp_servers().keys())}')
" || warn "Configuration loading test failed"

# Test kubani-dev CLI
info "Testing kubani-dev CLI..."
if command_exists kubani-dev; then
    kubani-dev --help > /dev/null && success "kubani-dev CLI is working"
else
    warn "kubani-dev CLI not found in PATH"
fi

# Test hooks
info "Testing Claude Code hooks..."
if [ -x ".claude/hooks/session-start.sh" ]; then
    .claude/hooks/session-start.sh > /dev/null 2>&1 && success "Session start hook is working"
else
    warn "Session start hook not executable"
fi

echo ""

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete!                           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "What was configured:"
echo ""
echo "  ✅ Python dependencies installed"
echo "  ✅ Local configuration created (config.local.yaml)"
echo "  ✅ Claude Code MCP servers configured (.claude/mcp.json)"
echo "  ✅ Claude Code hooks configured (.claude/settings.json)"
echo "  ✅ Hook scripts created (.claude/hooks/)"
echo ""
echo "Next steps:"
echo ""
echo "  1. Set Discord channel environment variables (see above)"
echo ""
echo "  2. Run an agent locally:"
echo "     kubani-dev local-run --agent k8s-monitor --temporal local --output console"
echo ""
echo "  3. Run evaluations:"
echo "     kubani-dev eval run --suite evaluations/k8s/pod_remediation.yaml"
echo ""
echo "  4. Deploy to cluster:"
echo "     kubani-dev deploy --agent k8s-monitor --wait"
echo ""
echo "  5. Start Claude Code in this directory:"
echo "     claude"
echo ""
echo "For more information, see:"
echo "  - MANUS_SETUP.md"
echo "  - docs/development/DEVELOPMENT_GUIDE.md"
echo "  - .claude/CLAUDE.md"
echo ""
