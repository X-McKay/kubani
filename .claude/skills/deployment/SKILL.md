---
name: deployment
description: Deploy agents and skills with full verification. Single command deployment with rollout monitoring, health checks, and automatic rollback.
---

# Deployment Automation

Deploy agents with confidence using the automated deployment pipeline. Builds locally with Earthly and pushes to the local registry (registry.almckay.io).

## Quick Start

```bash
# Deploy an agent (builds, pushes, and deploys)
kubani deploy k8s-monitor

# Deploy with specific version
kubani deploy k8s-monitor --version 1.2.0

# Deploy without rebuilding (use existing image)
kubani deploy k8s-monitor --skip-build

# Preview what would happen
kubani deploy k8s-monitor --dry-run
```

## Deployment Flow

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Build     │───▶│   Push      │───▶│   Update    │
│   (Earthly) │    │   Registry  │    │   GitOps    │
└─────────────┘    └─────────────┘    └─────────────┘
                                            │
                                            ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Verify    │◀───│   Health    │◀───│   Rollout   │
│   Complete  │    │   Check     │    │   Restart   │
└─────────────┘    └─────────────┘    └─────────────┘
```

## Commands

### deploy

Deploy an agent to the cluster:

```bash
kubani deploy <target> [options]

Arguments:
  target                Target to deploy (k8s-monitor, news-monitor, all)

Options:
  --version, -v         Version tag (auto-generated if not provided)
  --skip-build          Skip build, use existing images
  --skip-verification   Skip health verification after deploy
  --force, -f           Force deployment even on errors
  --dry-run             Show what would be deployed
```

### Examples

```bash
# Standard deployment (build + push + deploy)
kubani deploy k8s-monitor

# Deploy specific version
kubani deploy k8s-monitor --version 1.2.0

# Deploy all agents
kubani deploy all

# Dry run to see changes
kubani deploy k8s-monitor --dry-run

# Quick deployment (skip build, use existing image)
kubani deploy k8s-monitor --skip-build

# Deploy without waiting for health checks
kubani deploy k8s-monitor --skip-verification
```

## Deployment Process

### 1. Build with Earthly

```bash
# Automatically runs:
earthly --push +k8s-monitor-push --VERSION=1.2.0-abc1234
```

The version tag is auto-generated from:
- Version in pyproject.toml (if available)
- Git short SHA

### 2. Push to Local Registry

Images are pushed to `registry.almckay.io`:

```bash
# Image tag format:
registry.almckay.io/k8s-monitor:1.2.0-abc1234
```

### 3. GitOps Manifest Update

The deployment manifest is updated automatically:

```yaml
# infrastructure/gitops/apps/ai-agents/k8s-monitor/deployment.yaml
spec:
  template:
    spec:
      containers:
        - name: worker
          image: registry.almckay.io/k8s-monitor:1.2.0-abc1234
          env:
            - name: AGENT_VERSION
              value: "1.2.0-abc1234"
            - name: AGENT_IMAGE_TAG
              value: "1.2.0-abc1234"
            - name: AGENT_GIT_SHA
              value: "abc1234"
```

### 4. Kubernetes Rollout

```bash
# Deployment is restarted to pick up new image
kubectl rollout restart deployment/k8s-monitor -n ai-agents

# Rollout status is monitored
kubectl rollout status deployment/k8s-monitor -n ai-agents --timeout=300s
```

### 5. Health Verification

After rollout completes:

```bash
# Verify all pods are Running
kubectl get pods -n ai-agents -l app.kubernetes.io/name=k8s-monitor
```

### 6. Automatic Rollback

If health checks fail:

```bash
# Automatic rollback triggered
kubectl rollout undo deployment/k8s-monitor -n ai-agents
```

## Configuration

### Deployment Manifest

```yaml
# infrastructure/gitops/apps/ai-agents/k8s-monitor/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k8s-monitor
  namespace: ai-agents
spec:
  replicas: 1
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    spec:
      containers:
        - name: worker
          image: registry.almckay.io/k8s-monitor:0.5.0
          imagePullPolicy: Always
```

### Earthfile Targets

```bash
# Available build targets
earthly +k8s-monitor       # Build k8s-monitor image
earthly +k8s-monitor-push  # Build and push k8s-monitor
earthly +news-monitor      # Build news-monitor image
earthly +news-monitor-push # Build and push news-monitor
earthly +all               # Build all agents
earthly +push-all          # Build and push all agents
```

## Best Practices

1. **Use dry-run first** for major changes
2. **Check logs** if deployment fails
3. **Use semantic versioning** for releases
4. **Skip build** when deploying known-good images
5. **Review GitOps changes** before committing

## Troubleshooting

### Build Failures

```bash
# Check Earthly is installed
earthly --version

# Run build manually with verbose output
earthly --verbose +k8s-monitor-push --VERSION=test
```

### Deployment Stuck

```bash
# Check pod events
kubectl describe pod -n ai-agents -l app.kubernetes.io/name=k8s-monitor

# Check deployment events
kubectl describe deployment k8s-monitor -n ai-agents

# Check rollout status
kubectl rollout status deployment/k8s-monitor -n ai-agents
```

### Health Check Failures

```bash
# Check pod logs
kubectl logs -n ai-agents -l app.kubernetes.io/name=k8s-monitor --tail=100

# Describe pod for events
kubectl describe pod -n ai-agents -l app.kubernetes.io/name=k8s-monitor
```

### Rollback Issues

```bash
# Manual rollback
kubectl rollout undo deployment/k8s-monitor -n ai-agents

# Rollback to specific revision
kubectl rollout history deployment/k8s-monitor -n ai-agents
kubectl rollout undo deployment/k8s-monitor -n ai-agents --to-revision=2
```

### Registry Access

```bash
# Test registry access
docker pull registry.almckay.io/k8s-monitor:latest

# Check registry health
curl -s https://registry.almckay.io/v2/_catalog
```
