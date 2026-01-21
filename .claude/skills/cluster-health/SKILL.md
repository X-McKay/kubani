---
name: cluster-health
description: Check, validate, and troubleshoot Kubernetes cluster health. Use for quick status checks, pre-deployment validation, or debugging issues.
---

# Cluster Health

Unified skill for cluster status, validation, and troubleshooting. Choose the appropriate mode based on your need.

## Modes

| Mode | Use When |
|------|----------|
| **Quick** | Need a fast overview of cluster state |
| **Validate** | Before deployments or checking configuration |
| **Troubleshoot** | Pods failing, services unreachable, investigating issues |

---

## Quick Status Check

Fast overview of cluster health - nodes, pods, and recent events.

### Overview

```bash
KUBECONFIG=/home/al/.kube/config

echo "=== Nodes ==="
kubectl get nodes -o wide

echo ""
echo "=== AI Agents Namespace ==="
kubectl get pods -n ai-agents

echo ""
echo "=== vLLM Namespace ==="
kubectl get pods -n vllm

echo ""
echo "=== Temporal Namespace ==="
kubectl get pods -n temporal
```

### Node Resources

```bash
KUBECONFIG=/home/al/.kube/config

# Resource usage
kubectl top nodes

# Node conditions
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.conditions[-1].type}={.status.conditions[-1].status}{"\n"}{end}'
```

### GitOps Status

```bash
KUBECONFIG=/home/al/.kube/config flux get all -A
```

### Problem Pods

```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -A | grep -v Running | grep -v Completed
```

### Recent Events

```bash
KUBECONFIG=/home/al/.kube/config kubectl get events --sort-by='.lastTimestamp' -A | tail -20
```

---

## Validation Mode

Comprehensive pre-deployment validation checklist.

### 1. Node Connectivity

```bash
KUBECONFIG=/home/al/.kube/config

echo "=== Node Connectivity ==="
for node in $(kubectl get nodes -o jsonpath='{.items[*].metadata.name}'); do
    status=$(kubectl get node $node -o jsonpath='{.status.conditions[-1].status}')
    echo "$node: Ready=$status"
done
```

### 2. Critical Services

```bash
KUBECONFIG=/home/al/.kube/config

echo ""
echo "=== Critical Services ==="

# Check Temporal
temporal_ready=$(kubectl get pods -n temporal -l app=temporal-frontend -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "missing")
echo "Temporal Frontend: $temporal_ready"

# Check vLLM
vllm_ready=$(kubectl get pods -n vllm -l app=llm-api -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "missing")
echo "vLLM API: $vllm_ready"

# Check Flux
flux_ready=$(kubectl get pods -n flux-system -l app=source-controller -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "missing")
echo "Flux Source Controller: $flux_ready"
```

### 3. Storage

```bash
KUBECONFIG=/home/al/.kube/config

echo ""
echo "=== Persistent Volume Claims ==="
kubectl get pvc -A
```

### 4. Services

```bash
KUBECONFIG=/home/al/.kube/config

echo ""
echo "=== Services ==="
kubectl get svc -n ai-agents
kubectl get svc -n vllm
```

### 5. Secrets

```bash
KUBECONFIG=/home/al/.kube/config

echo ""
echo "=== Secrets (presence check) ==="
kubectl get secrets -n ai-agents | grep -v default-token
```

### 6. ConfigMaps

```bash
KUBECONFIG=/home/al/.kube/config

echo ""
echo "=== Model Configuration ==="
kubectl get configmap model-config -n ai-agents -o yaml 2>/dev/null | grep -A5 "data:" || echo "ConfigMap not found"
```

### Validation Checklist

- [ ] All nodes Ready
- [ ] Temporal frontend accessible
- [ ] vLLM API serving requests
- [ ] Model ConfigMaps in sync across namespaces
- [ ] Secrets present for Discord, database
- [ ] PVCs bound and accessible

---

## Troubleshooting Mode

Diagnose and resolve cluster problems.

### 1. Identify Problem Pods

```bash
KUBECONFIG=/home/al/.kube/config

echo "=== Problem Pods ==="
kubectl get pods -A | grep -v Running | grep -v Completed
```

### 2. Investigate a Pod

Replace `POD_NAME` and `NAMESPACE` with actual values:

```bash
KUBECONFIG=/home/al/.kube/config
POD_NAME="<pod-name>"
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
# Check if image exists locally
docker images | grep <agent-name>

# Push if missing
docker push registry.almckay.io/<agent-name>:TAG
```

#### CrashLoopBackOff
- Application error on startup
- Missing environment variables
- Failed dependency connections

```bash
KUBECONFIG=/home/al/.kube/config
POD_NAME="<pod-name>"
NAMESPACE="ai-agents"

# Check logs for error
kubectl logs $POD_NAME -n $NAMESPACE --tail=100

# Check env vars
kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath='{.spec.containers[0].env}' | jq .
```

#### Pending
- Insufficient resources
- Node selector mismatch
- PVC not bound

```bash
KUBECONFIG=/home/al/.kube/config
NAMESPACE="ai-agents"

# Check events
kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -20

# Check node resources
kubectl top nodes
```

### 4. Temporal Workflow Issues

```bash
KUBECONFIG=/home/al/.kube/config

# Check worker connectivity
kubectl logs -n ai-agents -l app.kubernetes.io/name=k8s-monitor --tail=50 | grep -i temporal

# Use Temporal MCP or tctl for workflow inspection
```

### 5. Recovery Actions

#### Restart Deployment

```bash
KUBECONFIG=/home/al/.kube/config
DEPLOYMENT="<deployment-name>"
NAMESPACE="ai-agents"

kubectl rollout restart deployment/$DEPLOYMENT -n $NAMESPACE
```

#### Force Pod Deletion

```bash
KUBECONFIG=/home/al/.kube/config
POD_NAME="<pod-name>"
NAMESPACE="ai-agents"

kubectl delete pod $POD_NAME -n $NAMESPACE --force --grace-period=0
```

### Escalation Path

If unable to resolve:
1. Check node health: `kubectl get nodes`
2. Check kubelet logs on the affected node
3. Review recent changes in git history
4. Check Flux reconciliation: `flux get all -A`
5. Consider rollback: use `/rollback` skill

---

## Health Indicators

| Indicator | Healthy State |
|-----------|---------------|
| Nodes | All `Ready` |
| Critical pods | All `Running` |
| Pending pods | None |
| Failed pods | None |
| Flux reconciliation | All successful |
| PVCs | All `Bound` |

## See Also

- [deployment](../deployment/SKILL.md) - Deploy agents with verification
- [rollback](../rollback/SKILL.md) - Rollback failed deployments
- [agents](../agents/SKILL.md) - Agent management
