---
paths:
  - "**/*"
---

# Kubernetes Operations Rules

When interacting with the Kubernetes cluster:

## Environment

Always use explicit kubeconfig:
```bash
KUBECONFIG=/home/al/.kube/config kubectl <command>
```

## Safe Operations

These are safe and can be run freely:
- `kubectl get` - Read resources
- `kubectl describe` - Resource details
- `kubectl logs` - Container logs
- `kubectl top` - Resource usage

## Modifying Operations

Use caution with:
- `kubectl apply` - Apply manifests
- `kubectl delete` - Remove resources
- `kubectl rollout restart` - Restart deployments
- `kubectl scale` - Change replica count

## Dangerous Operations

Avoid unless explicitly requested:
- `kubectl delete namespace` - Deletes all resources
- `kubectl delete --all` - Bulk deletion
- Force deletion with `--force --grace-period=0`

## Debugging

For pod issues:
```bash
# Check events
kubectl get events -n <namespace> --sort-by='.lastTimestamp'

# Check logs
kubectl logs <pod> -n <namespace> --tail=50

# Previous container logs
kubectl logs <pod> -n <namespace> --previous

# Exec into pod
kubectl exec -it <pod> -n <namespace> -- /bin/bash
```

## Common Namespaces

- `ai-agents` - AI monitoring agents
- `vllm` - LLM inference
- `temporal` - Workflow orchestration
- `flux-system` - GitOps
- `cert-manager` - TLS certificates
