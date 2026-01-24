# Troubleshoot Cluster Issues

Help diagnose and fix common cluster problems.

## Instructions

When the user reports an issue, follow this diagnostic workflow:

### Step 1: Identify the Problem Category

Ask the user or determine from context:
1. **Node issues** - Node not Ready, can't join cluster
2. **Pod issues** - Pods crashing, not starting, pending
3. **Network issues** - Services unreachable, DNS failures
4. **Storage issues** - PVC pending, mount failures
5. **GitOps issues** - Flux not reconciling, deployments not updating

### Step 2: Run Diagnostics

Based on the category, run appropriate diagnostics:

#### Node Issues
```bash
KUBECONFIG=/home/al/.kube/config kubectl get nodes -o wide
KUBECONFIG=/home/al/.kube/config kubectl describe node <node_name> | tail -50
```

Check Tailscale connectivity:
```bash
tailscale status | grep <node_name>
```

#### Pod Issues
```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -n <namespace>
KUBECONFIG=/home/al/.kube/config kubectl describe pod -n <namespace> <pod_name>
KUBECONFIG=/home/al/.kube/config kubectl logs -n <namespace> <pod_name> --tail=50
```

#### Network Issues
```bash
# Check DNS
KUBECONFIG=/home/al/.kube/config kubectl get pods -n kube-system -l k8s-app=kube-dns

# Check Traefik
KUBECONFIG=/home/al/.kube/config kubectl get svc -n kube-system traefik
KUBECONFIG=/home/al/.kube/config kubectl logs -n kube-system -l app.kubernetes.io/name=traefik --tail=30

# Check routes on affected node
ip route | grep 10.42
```

#### GitOps Issues
```bash
KUBECONFIG=/home/al/.kube/config flux get all -A
KUBECONFIG=/home/al/.kube/config kubectl logs -n flux-system -l app=kustomize-controller --tail=30
```

### Step 3: Check Known Issues

Reference the troubleshooting documentation:
- `docs/troubleshooting/flannel-routes-lost-after-tailscale-upgrade.md` - Network issues after Tailscale upgrade
- `docs/troubleshooting/common-issues.md` - General troubleshooting guide
- `docs/infrastructure/cluster/troubleshooting/` - Infrastructure-specific issues

### Step 4: Common Fixes

#### Flannel Routes Lost (after Tailscale upgrade)
```bash
sudo systemctl restart k3s-agent  # On worker nodes
sudo systemctl restart k3s        # On control plane
```

#### DNS Not Working
```bash
# Restart CoreDNS
KUBECONFIG=/home/al/.kube/config kubectl rollout restart deployment/coredns -n kube-system
```

#### Flux Not Syncing
```bash
KUBECONFIG=/home/al/.kube/config flux reconcile source git flux-system
KUBECONFIG=/home/al/.kube/config flux reconcile kustomization flux-system
```

#### Pod Stuck Pending
```bash
# Check events for the pod
KUBECONFIG=/home/al/.kube/config kubectl describe pod -n <namespace> <pod_name> | grep -A 10 Events

# Common causes: resource constraints, node selectors, taints
```

### Step 5: Document New Issues

If a new issue is discovered and resolved, add it to `troubleshooting/` directory following the existing format:
- Problem Summary
- Symptoms
- Investigation Steps
- Root Cause
- Solution
- Prevention
