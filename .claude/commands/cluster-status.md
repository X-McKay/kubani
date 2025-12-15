# Cluster Status Check

Quickly check the health and status of the Kubernetes cluster.

## Instructions

Run these commands to get a comprehensive cluster status:

### Node Status

```bash
KUBECONFIG=/home/al/.kube/config kubectl get nodes -o wide
```

### Pod Status (All Namespaces)

```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -A | grep -v "Running\|Completed" | head -20
```

This shows any pods that are NOT in Running or Completed state (i.e., problems).

### Flux GitOps Status

```bash
KUBECONFIG=/home/al/.kube/config flux get all -A 2>/dev/null | grep -v "True" | head -20
```

### Recent Events (Warnings/Errors)

```bash
KUBECONFIG=/home/al/.kube/config kubectl get events -A --field-selector type!=Normal --sort-by='.lastTimestamp' | tail -10
```

### Resource Usage

```bash
KUBECONFIG=/home/al/.kube/config kubectl top nodes 2>/dev/null || echo "Metrics not available"
```

### Tailscale Network Status

```bash
tailscale status | grep -E "sparky|rig0|asio|strix"
```

## Quick Health Summary

After running the above commands, summarize:
1. **Nodes**: How many are Ready vs NotReady
2. **Pods**: Any pods in CrashLoopBackOff, Pending, or Error state
3. **GitOps**: Any Flux resources not reconciled
4. **Network**: All cluster nodes reachable via Tailscale

## Common Issues

- **Node NotReady**: Check kubelet logs on that node
- **Pod CrashLoopBackOff**: Check pod logs with `kubectl logs -n <ns> <pod>`
- **Flux not reconciling**: Run `flux reconcile kustomization flux-system`
- **Tailscale offline**: Restart tailscaled on the affected node