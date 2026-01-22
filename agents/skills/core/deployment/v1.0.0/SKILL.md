---
name: deployment
description: Deploy agents and skills with full verification. Single command deployment with rollout monitoring, health checks, and automatic rollback.
---

# Deployment Automation

Deploy agents with confidence using the automated deployment pipeline.

## Quick Start

```bash
# Deploy an agent
kubani-dev deploy k8s-monitor

# Deploy with specific version
kubani-dev deploy k8s-monitor --version v1.2.0

# Deploy with monitoring
kubani-dev deploy k8s-monitor --watch
```

## Deployment Flow

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Build     │───▶│   Push      │───▶│   Deploy    │
│   Image     │    │   Registry  │    │   GitOps    │
└─────────────┘    └─────────────┘    └─────────────┘
                                            │
                                            ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Verify    │◀───│   Health    │◀───│   Rollout   │
│   Complete  │    │   Check     │    │   Monitor   │
└─────────────┘    └─────────────┘    └─────────────┘
```

## Commands

### deploy

Deploy an agent to the cluster:

```bash
kubani-dev deploy <agent> [options]

Options:
  --version, -v       Version to deploy (default: latest)
  --watch, -w         Watch deployment progress
  --timeout           Deployment timeout in seconds (default: 300)
  --dry-run           Show what would be deployed
  --skip-build        Skip image build (use existing)
  --skip-tests        Skip pre-deployment tests
  --force             Force deployment even if checks fail
```

### Examples

```bash
# Standard deployment
kubani-dev deploy k8s-monitor

# Deploy specific version with monitoring
kubani-dev deploy k8s-monitor --version v1.2.0 --watch

# Dry run to see changes
kubani-dev deploy k8s-monitor --dry-run

# Quick deployment (skip build, use existing image)
kubani-dev deploy k8s-monitor --skip-build
```

### status

Check deployment status:

```bash
kubani-dev status <agent>

# Output:
# Agent: k8s-monitor
# Version: v1.2.0
# Status: Running
# Replicas: 2/2
# Last Deploy: 2024-01-11 10:30:00
# Health: Healthy
```

### rollback

Rollback to a previous version:

```bash
kubani-dev rollback <agent> [options]

Options:
  --version, -v       Version to rollback to
  --previous          Rollback to previous version
```

### logs

View deployment logs:

```bash
kubani-dev logs <agent> [options]

Options:
  --follow, -f        Follow logs
  --tail, -n          Number of lines (default: 100)
  --since             Show logs since duration (e.g., 1h, 30m)
```

## Deployment Process

### 1. Pre-Deployment Checks

```bash
# Automatically runs:
# - Unit tests
# - Linting
# - Type checking
# - Evaluation suite (optional)
```

### 2. Build & Push

```bash
# Build container image
docker build -t ghcr.io/x-mckay/kubani/k8s-monitor:v1.2.0 .

# Push to registry
docker push ghcr.io/x-mckay/kubani/k8s-monitor:v1.2.0
```

### 3. GitOps Update

```bash
# Update deployment manifest
# gitops/apps/ai-agents/k8s-monitor/deployment.yaml
# - image: ghcr.io/x-mckay/kubani/k8s-monitor:v1.2.0
```

### 4. Rollout Monitoring

```bash
# Monitor rollout progress
kubectl rollout status deployment/k8s-monitor -n ai-agents

# Check pod status
kubectl get pods -n ai-agents -l app=k8s-monitor
```

### 5. Health Verification

```bash
# Health check endpoints
curl http://k8s-monitor.ai-agents.svc:8000/health
curl http://k8s-monitor.ai-agents.svc:8000/ready

# Registry heartbeat verification
kubani-dev registry check k8s-monitor
```

### 6. Automatic Rollback

If health checks fail:

```bash
# Automatic rollback triggered
kubectl rollout undo deployment/k8s-monitor -n ai-agents

# Notification sent to Discord
# "⚠️ Deployment failed, rolled back to v1.1.0"
```

## Configuration

### Deployment Config

```yaml
# gitops/apps/ai-agents/k8s-monitor/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k8s-monitor
  namespace: ai-agents
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    spec:
      containers:
        - name: k8s-monitor
          image: ghcr.io/x-mckay/kubani/k8s-monitor:v1.2.0
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
```

### CI/CD Integration

The deployment is triggered via GitHub Actions but verification happens cluster-side:

```yaml
# .github/workflows/deploy.yml
- name: Trigger Deployment
  run: |
    kubani-dev deploy ${{ matrix.agent }} --version ${{ github.ref_name }}
    
- name: Wait for Verification
  run: |
    kubani-dev wait-deploy ${{ matrix.agent }} --timeout 300
```

## Cluster-Side Controller

Since GitHub Actions doesn't have cluster access, a cluster-side controller handles:

1. **Watching for image updates** in the registry
2. **Applying GitOps changes** via Flux
3. **Monitoring rollout** progress
4. **Running health checks** against new pods
5. **Triggering rollback** if checks fail
6. **Reporting status** back to the CLI

### Controller Status

```bash
# Check controller status
kubani-dev controller status

# View controller logs
kubani-dev controller logs
```

## Best Practices

1. **Always run tests** before deploying
2. **Use semantic versioning** for releases
3. **Monitor deployments** with `--watch`
4. **Check logs** if deployment fails
5. **Use dry-run** for major changes
6. **Set appropriate timeouts** for slow services
7. **Review rollback history** periodically

## Troubleshooting

### Deployment Stuck

```bash
# Check pod events
kubectl describe pod -n ai-agents -l app=k8s-monitor

# Check deployment events
kubectl describe deployment k8s-monitor -n ai-agents
```

### Health Check Failures

```bash
# Test health endpoint directly
kubectl exec -n ai-agents deploy/k8s-monitor -- curl localhost:8000/health

# Check application logs
kubani-dev logs k8s-monitor --tail 200
```

### Rollback Issues

```bash
# Manual rollback
kubectl rollout undo deployment/k8s-monitor -n ai-agents

# Rollback to specific revision
kubectl rollout undo deployment/k8s-monitor -n ai-agents --to-revision=2
```
