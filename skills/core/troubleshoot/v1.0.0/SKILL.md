---
name: troubleshoot
description: Diagnose and fix cluster issues. Use when pods fail, deployments don't work, or services are unreachable.
---

# Troubleshoot Cluster Issues

Diagnose and resolve common cluster problems.

## Instructions

### 1. Identify Problem Pods

```bash
KUBECONFIG=/home/al/.kube/config

echo "=== Problem Pods ==="
kubectl get pods -A | grep -v Running | grep -v Completed
```

### 2. Check Pod Details

```bash
KUBECONFIG=/home/al/.kube/config
POD_NAME="k8s-monitor-xxx"
NAMESPACE="ai-agents"

# Describe pod
kubectl describe pod $POD_NAME -n $NAMESPACE

# Check logs
kubectl logs $POD_NAME -n $NAMESPACE --tail=50

# Check previous container logs (if crash loop)
kubectl logs $POD_NAME -n $NAMESPACE --previous --tail=50
```

### 3. Common Issues

#### ImagePullBackOff
- Image not pushed to registry
- Wrong image tag
- Registry authentication issue

```bash
# Check if image exists
docker images | grep k8s-monitor

# Push if missing
docker push registry.almckay.io/k8s-monitor:TAG
```

#### CrashLoopBackOff
- Application error on startup
- Missing environment variables
- Failed dependency connections

```bash
# Check logs for error
KUBECONFIG=/home/al/.kube/config kubectl logs $POD_NAME -n $NAMESPACE --tail=100

# Check env vars
kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath='{.spec.containers[0].env}'
```

#### Pending
- Insufficient resources
- Node selector mismatch
- PVC not bound

```bash
# Check events
KUBECONFIG=/home/al/.kube/config kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -20

# Check node resources
kubectl top nodes
```

### 4. Temporal Workflow Issues

```bash
# Check worker connectivity
KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents -l app.kubernetes.io/name=k8s-monitor --tail=50 | grep -i temporal

# List running workflows
# (use tctl or Temporal UI)
```

### 5. Restart Deployment

```bash
KUBECONFIG=/home/al/.kube/config kubectl rollout restart deployment/$DEPLOYMENT -n $NAMESPACE
```

### 6. Force Pod Deletion

```bash
KUBECONFIG=/home/al/.kube/config kubectl delete pod $POD_NAME -n $NAMESPACE --force --grace-period=0
```

## Escalation

If unable to resolve:
1. Check node health: `kubectl get nodes`
2. Check kubelet logs on node
3. Review recent changes in git history
4. Check Flux reconciliation status
