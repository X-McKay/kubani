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
- `kubectl get` — read resources
- `kubectl describe` — resource details
- `kubectl logs` — container logs
- `kubectl top` — resource usage
- `flux get all -A` — Flux state

## Modifying Operations

Use caution with:
- `kubectl apply` — prefer GitOps; use only for emergency fixes
- `kubectl delete` — confirm scope first
- `kubectl rollout restart` — usually safe but kicks workloads
- `kubectl scale` — record prior replica count

## Dangerous Operations

Avoid unless explicitly requested:
- `kubectl delete namespace` — deletes all resources
- `kubectl delete --all` — bulk deletion
- Force deletion with `--force --grace-period=0`

## Debugging

For pod issues:
```bash
# Events for the namespace, newest last
kubectl get events -n <namespace> --sort-by='.lastTimestamp'

# Logs
kubectl logs <pod> -n <namespace> --tail=50
kubectl logs <pod> -n <namespace> --previous   # crashed container

# Exec into pod
kubectl exec -it <pod> -n <namespace> -- /bin/bash
```

## Common Namespaces

- `flux-system` — GitOps
- `cert-manager` — TLS certificates
- `database` — postgres, neo4j, qdrant
- `cache` — redis
- `monitoring` — prometheus, grafana
- `auth` — authentik
- `temporal` — workflows
- `vllm` — LLM inference
- `registry` — cluster image registry
- `longhorn-system` — distributed storage

See `.claude/rules/gitops.md` for the full namespace inventory.
