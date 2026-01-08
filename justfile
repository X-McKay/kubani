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

# Type check with ty (fast type checker from Astral)
check:
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
# Flux CD / GitOps
# =============================================================================

# Show status of all Flux resources
flux-status:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Flux Kustomizations ==="
    kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A
    echo ""
    echo "=== Flux HelmReleases ==="
    kubectl get helmreleases.helm.toolkit.fluxcd.io -A
    echo ""
    echo "=== Flux Sources ==="
    kubectl get gitrepositories.source.toolkit.fluxcd.io -A
    kubectl get helmrepositories.source.toolkit.fluxcd.io -A 2>/dev/null || true

# Reconcile Flux resources (all or specific kustomization)
flux-reconcile target="all":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ "{{target}}" == "all" ]]; then
        echo "=== Reconciling all Flux kustomizations ==="
        for ks in flux-system infrastructure databases apps; do
            echo "Reconciling $ks..."
            kubectl annotate --overwrite kustomization/$ks -n flux-system reconcile.fluxcd.io/requestedAt="$(date +%s)"
        done
    else
        echo "=== Reconciling {{target}} ==="
        kubectl annotate --overwrite kustomization/{{target}} -n flux-system reconcile.fluxcd.io/requestedAt="$(date +%s)"
    fi
    echo ""
    echo "Waiting for reconciliation..."
    sleep 2
    kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A

# Suspend Flux reconciliation for a kustomization
flux-suspend target:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Suspending {{target}} ==="
    kubectl patch kustomization/{{target}} -n flux-system -p '{"spec":{"suspend":true}}' --type=merge
    echo "Suspended. Resume with: just flux-resume {{target}}"

# Resume Flux reconciliation for a kustomization
flux-resume target:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Resuming {{target}} ==="
    kubectl patch kustomization/{{target}} -n flux-system -p '{"spec":{"suspend":false}}' --type=merge
    kubectl annotate --overwrite kustomization/{{target}} -n flux-system reconcile.fluxcd.io/requestedAt="$(date +%s)"
    echo "Resumed and triggered reconciliation"

# Watch Flux controller logs
flux-logs controller="kustomize-controller":
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Flux {{controller}} logs ==="
    echo "(Press Ctrl+C to exit)"
    kubectl logs -n flux-system -l app={{controller}} -f --tail=100

# Show Flux events (recent reconciliation activity)
flux-events:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Recent Flux Events ==="
    kubectl get events -n flux-system --sort-by='.lastTimestamp' | tail -30

# =============================================================================
# Secrets Management (SOPS)
# =============================================================================

# List all encrypted secrets in gitops/
secrets-list:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Encrypted Secrets ==="
    echo ""
    find gitops -name "*.enc.yaml" -type f | sort | while read -r file; do
        # Extract the relative path for cleaner display
        echo "  $file"
    done
    echo ""
    echo "Use 'just secrets-view <file>' to decrypt and view"

# Decrypt and view an encrypted secret (requires SOPS)
secrets-view file:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ ! -f "{{file}}" ]]; then
        echo "Error: File not found: {{file}}"
        exit 1
    fi
    if ! command -v sops &> /dev/null; then
        echo "Error: sops is not installed"
        echo "Install with: brew install sops (macOS) or see https://github.com/getsops/sops"
        exit 1
    fi
    echo "=== Decrypted: {{file}} ==="
    echo ""
    sops -d "{{file}}"

# Edit an encrypted secret in place (requires SOPS)
secrets-edit file:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ ! -f "{{file}}" ]]; then
        echo "Error: File not found: {{file}}"
        exit 1
    fi
    if ! command -v sops &> /dev/null; then
        echo "Error: sops is not installed"
        exit 1
    fi
    sops "{{file}}"

# =============================================================================
# Model Management
# =============================================================================

# Configuration for model management
model_node := "sparky"
model_pvc_path := "/var/lib/rancher/k3s/storage/pvc-bd501d51-09cf-44a8-85a9-6299c6a6f980_vllm_model-storage"

# Show current model configuration from ConfigMaps
model-current:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== vLLM Model Configuration ==="
    echo ""
    echo "Main LLM:"
    kubectl get configmap model-config -n vllm -o jsonpath='{.data.LLM_MODEL_NAME}' 2>/dev/null || echo "(not deployed)"
    echo ""
    echo "Model Path:"
    kubectl get configmap model-config -n vllm -o jsonpath='{.data.LLM_MODEL_PATH}' 2>/dev/null || echo "(not deployed)"
    echo ""
    echo ""
    echo "Embeddings:"
    kubectl get configmap model-config -n vllm -o jsonpath='{.data.EMBEDDINGS_MODEL_NAME}' 2>/dev/null || echo "(not deployed)"
    echo ""

# List models available on the cluster PVC
model-list:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Models on cluster ({{model_node}}:{{model_pvc_path}}) ==="
    ssh {{model_node}} "sudo ls -la {{model_pvc_path}}/ 2>/dev/null" || echo "Cannot access PVC path"

# Download a model from HuggingFace (run locally)
model-download model:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Downloading {{model}} ==="
    echo ""
    # Use huggingface-hub CLI for robust downloads (handles shards, resume, etc.)
    if ! command -v huggingface-cli &> /dev/null; then
        echo "Installing huggingface-hub CLI..."
        pip install -q huggingface-hub[cli]
    fi
    # Download to ~/models/<model-name>
    model_dir=~/models/$(basename "{{model}}")
    echo "Downloading to: $model_dir"
    huggingface-cli download "{{model}}" --local-dir "$model_dir"
    echo ""
    echo "Download complete! Model saved to: $model_dir"
    echo "Next step: just model-copy $(basename {{model}})"

# Copy a downloaded model to the cluster
model-copy model:
    #!/usr/bin/env bash
    set -euo pipefail
    model_dir=~/models/{{model}}
    if [[ ! -d "$model_dir" ]]; then
        echo "Error: Model directory not found: $model_dir"
        echo "Did you run: just model-download <model-name> ?"
        exit 1
    fi
    echo "=== Copying {{model}} to {{model_node}} ==="
    echo "Source: $model_dir"
    echo "Destination: {{model_node}}:{{model_pvc_path}}/{{model}}"
    echo ""
    # Use rsync for efficient transfer with progress
    rsync -avP --delete "$model_dir/" "{{model_node}}:/tmp/{{model}}/"
    echo ""
    echo "Moving to PVC path (requires sudo)..."
    ssh {{model_node}} "sudo mv /tmp/{{model}} {{model_pvc_path}}/"
    echo ""
    echo "Copy complete! Model available at: {{model_pvc_path}}/{{model}}"
    echo "Next step: just model-switch {{model}}"

# Switch to a different model (updates ConfigMaps)
model-switch model:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Switching to model: {{model}} ==="
    echo ""
    # Update vllm ConfigMap
    echo "Updating gitops/apps/vllm/model-config.yaml..."
    # Extract model name from path (e.g., Qwen3-14B-FP8 -> Qwen/Qwen3-14B-FP8)
    # Assume model format: Owner/ModelName or just ModelName
    if [[ "{{model}}" == *"/"* ]]; then
        model_name="{{model}}"
        model_path="/models/$(basename {{model}})"
    else
        model_name="{{model}}"
        model_path="/models/{{model}}"
    fi
    # Update vllm model-config.yaml
    sed -i "s|LLM_MODEL_NAME:.*|LLM_MODEL_NAME: \"$model_name\"|" gitops/apps/vllm/model-config.yaml
    sed -i "s|LLM_MODEL_PATH:.*|LLM_MODEL_PATH: \"$model_path\"|" gitops/apps/vllm/model-config.yaml
    # Update ai-agents model-config.yaml
    echo "Updating gitops/apps/ai-agents/k8s-monitor/model-config.yaml..."
    sed -i "s|LLM_MODEL_NAME:.*|LLM_MODEL_NAME: \"$model_name\"|" gitops/apps/ai-agents/k8s-monitor/model-config.yaml
    echo ""
    echo "ConfigMaps updated. Changes:"
    echo "  LLM_MODEL_NAME: $model_name"
    echo "  LLM_MODEL_PATH: $model_path"
    echo ""
    echo "Next step: just model-deploy"

# Apply ConfigMap changes and restart deployments
model-deploy:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Deploying model configuration ==="
    echo ""
    echo "Applying ConfigMap changes..."
    kubectl apply -f gitops/apps/vllm/model-config.yaml
    kubectl apply -f gitops/apps/ai-agents/k8s-monitor/model-config.yaml
    echo ""
    echo "Restarting vLLM deployment..."
    kubectl rollout restart deployment/vllm -n vllm
    echo ""
    echo "Restarting embeddings deployment..."
    kubectl rollout restart deployment/vllm-embeddings -n vllm
    echo ""
    echo "Restarting k8s-monitor..."
    kubectl rollout restart deployment/k8s-monitor -n ai-agents
    echo ""
    echo "Waiting for rollouts to complete..."
    kubectl rollout status deployment/vllm -n vllm --timeout=15m || true
    kubectl rollout status deployment/k8s-monitor -n ai-agents --timeout=2m || true
    echo ""
    echo "Model deployment complete!"

# Check copy progress (watch rsync output)
model-progress:
    #!/usr/bin/env bash
    echo "=== Model Transfer Progress ==="
    echo "Checking disk usage on {{model_node}}..."
    ssh {{model_node}} "df -h {{model_pvc_path}}"
    echo ""
    echo "Current contents:"
    ssh {{model_node}} "sudo ls -lah {{model_pvc_path}}/ 2>/dev/null" || echo "Cannot access path"

# Full model workflow: download -> copy -> switch -> deploy
model-install model:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Full model installation: {{model}} ==="
    just model-download "{{model}}"
    model_basename=$(basename "{{model}}")
    just model-copy "$model_basename"
    just model-switch "{{model}}"
    just model-deploy

# =============================================================================
# Utilities
# =============================================================================

# Clean build artifacts
clean:
    rm -rf build/ dist/ *.egg-info
    rm -rf .pytest_cache .ruff_cache .hypothesis
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

# =============================================================================
# Version Management
# =============================================================================

# List agent versions
agent-versions:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Agent Versions ==="
    python scripts/bump-version.py --list

# Bump agent version (type: patch, minor, major)
bump agent bump_type="patch":
    #!/usr/bin/env bash
    set -euo pipefail
    python scripts/bump-version.py {{agent}} --type {{bump_type}}

# Bump agent version based on conventional commits
bump-auto agent:
    #!/usr/bin/env bash
    set -euo pipefail
    python scripts/bump-version.py {{agent}} --from-commits

# Bump all changed agent versions based on conventional commits
bump-all:
    #!/usr/bin/env bash
    set -euo pipefail
    python scripts/bump-version.py all --from-commits

# Show what version bump would occur (dry run)
bump-preview agent:
    #!/usr/bin/env bash
    set -euo pipefail
    python scripts/bump-version.py {{agent}} --from-commits --dry-run

# Generate changelog from conventional commits
changelog *args:
    #!/usr/bin/env bash
    set -euo pipefail
    python scripts/generate-changelog.py {{args}}

# Generate changelog preview (dry run)
changelog-preview:
    #!/usr/bin/env bash
    set -euo pipefail
    python scripts/generate-changelog.py --dry-run
