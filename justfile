# Kubani - Kubernetes Cluster Automation
# Modern command runner using Just (https://github.com/casey/just)
#
# Usage:
#   just              - Show all available commands
#   just setup        - One-time project setup
#   just test         - Run all tests
#   just build agent  - Build a specific agent

# Default recipe: show help
default:
    @just --list --unsorted

# =============================================================================
# Setup & Bootstrap
# =============================================================================

# One-time project setup (installs tools and dependencies)
setup:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Kubani Setup ==="
    echo ""

    # Check for mise
    if ! command -v mise &> /dev/null; then
        echo "Mise is not installed."
        echo "Install it with: curl https://mise.run | sh"
        echo "Then add it to your PATH and run 'just setup' again."
        exit 1
    fi
    echo "✓ Mise is installed"

    # Install mise tools (including just, uv, Python, kubectl)
    echo ""
    echo "Installing mise tools..."
    mise install

    # Install Python dependencies
    echo ""
    echo "Installing Python dependencies..."
    uv sync

    # Install pre-commit hooks
    echo ""
    echo "Installing pre-commit hooks..."
    uv run pre-commit install

    echo ""
    echo "=== Setup Complete! ==="
    echo ""
    echo "Available commands:"
    echo "  just              - Show all commands"
    echo "  just test         - Run tests"
    echo "  just lint         - Run linting"
    echo "  just tui          - Launch cluster TUI"
    echo "  just provision    - Provision cluster"
    echo ""
    echo "Next steps:"
    echo "  1. Copy ansible/inventory/hosts.yml.example to ansible/inventory/hosts.yml"
    echo "  2. Edit hosts.yml with your node information"
    echo "  3. Run 'just provision' to provision your cluster"

# Install dependencies only (skip pre-commit)
install:
    uv sync

# Install with dev dependencies
install-dev:
    uv sync --extra dev

# =============================================================================
# Testing
# =============================================================================

# Run all tests (root + agents)
test: test-root test-agents

# Run root project tests
test-root:
    uv run pytest

# Run unit tests only
test-unit:
    uv run pytest tests/unit

# Run property-based tests only
test-props:
    uv run pytest tests/properties

# Run all agent tests via Earthly
test-agents:
    earthly +test-all

# Run tests for a specific agent
test-agent agent:
    earthly ./agents/{{agent}}+test

# Run tests with coverage report
coverage:
    uv run pytest --cov=cluster_manager --cov-report=html --cov-report=term

# =============================================================================
# Code Quality
# =============================================================================

# Run all linting checks
lint:
    uv run ruff check .

# Lint all agents via Earthly
lint-agents:
    earthly +lint-all

# Format code
fmt:
    uv run ruff format .

# Check formatting without changes
fmt-check:
    uv run ruff format --check .

# Type check with mypy
check:
    uv run mypy cluster_manager

# Type check with ty (experimental)
check-ty:
    uv run ty check cluster_manager

# Run all checks (lint, format, type)
check-all: lint fmt-check check
    @echo "✓ All checks passed!"

# Quick CI check before pushing
ci: lint test check
    @echo "✓ All CI checks passed!"

# Full CI pipeline via Earthly
ci-full:
    earthly +ci

# =============================================================================
# Agent Builds (Earthly)
# =============================================================================

# Build a specific agent Docker image
build agent:
    earthly ./agents/{{agent}}+docker

# Build agent with specific version
build-version agent version:
    earthly ./agents/{{agent}}+docker --VERSION={{version}}

# Build all agent Docker images
build-all:
    earthly +all

# Build core-agents wheel
build-core:
    earthly +core-agents

# Push a specific agent to registry
push agent version="latest":
    earthly --push ./agents/{{agent}}+push --VERSION={{version}}

# Push all agents to registry
push-all:
    earthly --push +push-all

# Push core-agents wheel to registry
push-core:
    earthly --push +core-agents-push

# =============================================================================
# Agent Development
# =============================================================================

# Create a new agent from template
new-agent name:
    pipx run copier copy templates/agent agents/ --data agent_name={{name}}

# Local dev mode for an agent (syncs deps and runs worker)
dev agent:
    #!/usr/bin/env bash
    set -euo pipefail
    cd agents/{{agent}}
    echo "Syncing dependencies for {{agent}}..."
    uv sync
    echo "Starting {{agent}} worker..."
    export VLLM_API_URL="${VLLM_API_URL:-http://localhost:8000/v1}"
    export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
    package_name=$(echo "{{agent}}" | tr '-' '_')
    uv run python -m ${package_name}.worker

# Sync dependencies for an agent
sync-agent agent:
    cd agents/{{agent}} && uv sync

# Run agent tests locally (not via Earthly)
test-agent-local agent:
    cd agents/{{agent}} && uv run pytest -v

# Lint agent locally
lint-agent agent:
    cd agents/{{agent}} && uv run ruff check src/ tests/

# Interactive shell in agent Earthly environment
shell-agent agent:
    earthly -i ./agents/{{agent}}+dev

# =============================================================================
# Cluster Operations
# =============================================================================

# Provision the cluster (runs Ansible playbook)
provision *args:
    cluster-mgr provision {{args}}

# Show cluster status
status:
    cluster-mgr status

# Discover Tailscale nodes
discover *args:
    cluster-mgr discover {{args}}

# Add a node to inventory
add-node hostname ip *args:
    cluster-mgr add-node {{hostname}} {{ip}} {{args}}

# Remove a node from inventory
remove-node hostname *args:
    cluster-mgr remove-node {{hostname}} {{args}}

# Launch the cluster TUI
tui:
    cluster-tui

# =============================================================================
# Kubernetes Shortcuts
# =============================================================================

# Get pods in ai-agents namespace
pods:
    kubectl get pods -n ai-agents

# Get all pods across namespaces
pods-all:
    kubectl get pods -A

# Watch k8s-monitor logs
logs-monitor:
    kubectl logs -n ai-agents -l app.kubernetes.io/name=k8s-monitor -f

# Restart k8s-monitor deployment
restart-monitor:
    kubectl rollout restart deployment/k8s-monitor -n ai-agents

# Deploy k8s-monitor with specific version
deploy-monitor version="latest":
    kubectl set image deployment/k8s-monitor \
        worker=registry.almckay.io/k8s-monitor:{{version}} \
        start-scheduler=registry.almckay.io/k8s-monitor:{{version}} \
        -n ai-agents

# =============================================================================
# Utilities
# =============================================================================

# Clean build artifacts
clean:
    rm -rf build/ dist/ *.egg-info
    rm -rf .pytest_cache .mypy_cache .ruff_cache .hypothesis
    rm -rf htmlcov/ .coverage coverage.xml
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    @echo "✓ Cleaned build artifacts"

# Show project version
version:
    @cluster-mgr version

# Validate Ansible inventory
validate-inventory:
    ansible-inventory -i ansible/inventory/hosts.yml --list > /dev/null && echo "✓ Inventory is valid"

# Show environment info
info:
    @echo "=== Environment Info ==="
    @echo "Python: $(python --version)"
    @echo "UV: $(uv --version)"
    @echo "Earthly: $(earthly --version 2>&1 | head -1)"
    @echo "Kubectl: $(kubectl version --client -o yaml | grep gitVersion | awk '{print $2}')"
    @echo "Helm: $(helm version --short)"
    @echo "Just: $(just --version)"
