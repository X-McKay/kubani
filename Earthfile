VERSION 0.8

# =============================================================================
# Kubani Agent Build System
# =============================================================================
# Root Earthfile for orchestrating all agent builds
#
# Usage:
#   earthly +all              # Build all agents
#   earthly +test-all         # Test all agents
#   earthly +k8s-monitor      # Build specific agent
#   earthly --push +all       # Build and push all images
# =============================================================================

# Global arguments
ARG --global REGISTRY=registry.almckay.io
ARG --global PYTHON_VERSION=3.11

# =============================================================================
# Shared Base Images
# =============================================================================

# Base Python image with common dependencies
python-base:
    FROM python:${PYTHON_VERSION}-slim
    WORKDIR /app

    # Install common system dependencies
    RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        curl \
        && rm -rf /var/lib/apt/lists/*

    # Create non-root user
    RUN useradd -m -u 1000 agent

    SAVE IMAGE --cache-hint

# Base image with kubectl for K8s-interacting agents
python-k8s-base:
    FROM +python-base

    # Install kubectl (architecture-aware)
    ARG TARGETARCH
    RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/${TARGETARCH}/kubectl" \
        && chmod +x kubectl \
        && mv kubectl /usr/local/bin/

    SAVE IMAGE --cache-hint

# =============================================================================
# Core Agents Library
# =============================================================================

# Build core-agents wheel
core-agents:
    BUILD ./agents/core+build

# Push core-agents wheel to registry as OCI artifact
core-agents-push:
    BUILD ./agents/core+push

# Test core-agents
core-agents-test:
    BUILD ./agents/core+test

# Lint core-agents
core-agents-lint:
    BUILD ./agents/core+lint

# =============================================================================
# Agent Builds
# =============================================================================

# Build k8s-monitor agent (depends on core-agents)
k8s-monitor:
    BUILD ./agents/k8s-monitor+docker

# Push k8s-monitor to registry
k8s-monitor-push:
    BUILD ./agents/k8s-monitor+push

# Test k8s-monitor
k8s-monitor-test:
    BUILD ./agents/k8s-monitor+test

# Lint k8s-monitor
k8s-monitor-lint:
    BUILD ./agents/k8s-monitor+lint

# =============================================================================
# Orchestration Targets
# =============================================================================

# Build all agents (multi-platform)
all:
    BUILD +core-agents
    BUILD --platform=linux/amd64 --platform=linux/arm64 +k8s-monitor

# Push all to registry (core-agents wheel + k8s-monitor image)
push-all:
    BUILD +core-agents-push
    BUILD +k8s-monitor-push

# Test all
test-all:
    BUILD +core-agents-test
    BUILD +k8s-monitor-test

# Lint all
lint-all:
    BUILD +core-agents-lint
    BUILD +k8s-monitor-lint

# Full CI pipeline: lint, test, build
ci:
    BUILD +lint-all
    BUILD +test-all
    BUILD +all
