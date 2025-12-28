VERSION 0.8

# =============================================================================
# Kubani Agent Build System
# =============================================================================
# Root Earthfile for orchestrating all agent builds
#
# Usage:
#   earthly +all                              # Build all agents
#   earthly +test-all                         # Test all agents
#   earthly +agent --AGENT_NAME=k8s-monitor   # Build specific agent
#   earthly --push +push-all                  # Build and push all images
# =============================================================================

# Global arguments
ARG --global REGISTRY=registry.almckay.io
ARG --global PYTHON_VERSION=3.11
ARG --global VERSION=latest

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
# Dynamic Agent Targets
# =============================================================================
# These targets work with any agent under agents/
# Usage: earthly +agent --AGENT_NAME=k8s-monitor

# Build any agent by name
agent:
    ARG AGENT_NAME
    BUILD ./agents/${AGENT_NAME}+docker

# Push any agent by name
agent-push:
    ARG AGENT_NAME
    BUILD ./agents/${AGENT_NAME}+push

# Test any agent by name
agent-test:
    ARG AGENT_NAME
    BUILD ./agents/${AGENT_NAME}+test

# Lint any agent by name
agent-lint:
    ARG AGENT_NAME
    BUILD ./agents/${AGENT_NAME}+lint

# =============================================================================
# Individual Agent Targets (for convenience)
# =============================================================================

# k8s-monitor
k8s-monitor:
    BUILD ./agents/k8s-monitor+docker

k8s-monitor-push:
    BUILD ./agents/k8s-monitor+push

k8s-monitor-test:
    BUILD ./agents/k8s-monitor+test

k8s-monitor-lint:
    BUILD ./agents/k8s-monitor+lint

# news-monitor
news-monitor:
    BUILD ./agents/news-monitor+docker

news-monitor-push:
    BUILD ./agents/news-monitor+push

news-monitor-test:
    BUILD ./agents/news-monitor+test

news-monitor-lint:
    BUILD ./agents/news-monitor+lint

# =============================================================================
# Orchestration Targets
# =============================================================================

# Build all agents (local only, no push)
all:
    BUILD +core-agents
    BUILD +k8s-monitor
    BUILD +news-monitor

# Push all to registry (core-agents wheel + all agent images)
push-all:
    BUILD +core-agents-push
    BUILD +k8s-monitor-push
    BUILD +news-monitor-push

# Test all
test-all:
    BUILD +core-agents-test
    BUILD +k8s-monitor-test
    BUILD +news-monitor-test

# Lint all
lint-all:
    BUILD +core-agents-lint
    BUILD +k8s-monitor-lint
    BUILD +news-monitor-lint

# Full CI pipeline: lint, test, build
ci:
    BUILD +lint-all
    BUILD +test-all
    BUILD +all
