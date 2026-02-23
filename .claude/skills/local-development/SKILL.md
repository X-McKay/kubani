---
name: local-development
description: Standard 4-stage development workflow for testing locally, building containers, and deploying with validation.
---

# Local Development Workflow

All code changes follow this 4-stage workflow. Never skip stages.

## Stage 1: Local Development & Testing

Catches 90% of issues before any container is built.

### Syndicate Agents (k8s-monitor, news-digest, learning-system)

```bash
# Setup
cp config/local.yaml.example config/local.yaml  # Edit with your credentials
uv pip install -e .

# Run locally against cluster services
kubani local-run --agent k8s-monitor --temporal cluster --output console

# Run with hot-reload for rapid iteration
kubani local-run --agent k8s-monitor --hot-reload

# Run with mock services (no cluster needed)
kubani local-run --agent k8s-monitor --mock-services
```

### Nexus Agent

```bash
# Setup
cd kubani/nexus/orchestrator
cp ../../nexus/.env.example .env  # Edit with your credentials

# Run orchestrator worker locally
source .env && python -m kubani.nexus.orchestrator.worker

# Run gateway locally (separate terminal)
cd kubani/nexus/gateway
source .env && python -m kubani.nexus.gateway.main
```

### Verify Locally

```bash
# Unit tests
just test-unit
# or: pytest kubani/tests/

# Linting
just lint
```

## Stage 2: Integration Testing

Validates service interactions work end-to-end.

```bash
# Run integration tests
just test-integration

# For Nexus: test tool execution against live services
# For syndicates: test MCP client connections, event handling
# Verify Temporal workflow registration and execution
```

## Stage 3: Container Build & Smoke Test

Validates packaging before pushing.

```bash
# Build container
just build <agent>
# or: earthly +nexus-orchestrator

# Smoke test the built image
docker run --rm --env-file .env <image> python -c "from kubani.nexus.orchestrator.worker import *; print('OK')"

# Run Earthly test target
earthly +test-all

# Push when smoke test passes
just push <agent>
```

## Stage 4: Deploy & Validate

Validates production runtime.

```bash
# Update GitOps manifest with new image tag
# Commit and push (Flux auto-deploys, or: just flux-reconcile)

# Validate
kubectl get pods -n <namespace>           # No CrashLoopBackOff
kubectl logs -n <namespace> deploy/<name> --tail=50  # No errors

# Smoke test: send a test message through the UI
# Monitor for 5 minutes for stability
```

## Configuration

### Config Hierarchy (Syndicate Agents)

```
config/default.yaml    → Base defaults (committed)
config/{env}.yaml      → Environment-specific (committed)
config/local.yaml      → Local overrides (gitignored)
Environment variables  → KUBANI_ prefix with __ nesting
```

See `config/local.yaml.example` for a documented template.

### Environment Variables (Nexus Agent)

Nexus uses direct env vars (not the kubani config system). See `kubani/nexus/.env.example`.

## Troubleshooting

**Temporal Connection Failed**
```bash
curl -s https://temporal.almckay.io/health
# Or start local: temporal server start-dev
```

**MCP Server Not Responding**
```bash
curl -s https://temporal-mcp.almckay.io/health
curl -s https://memory-mcp.almckay.io/health
```

**LLM API Errors**
```bash
curl -s https://llm.almckay.io/v1/models
```
