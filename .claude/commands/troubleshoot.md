# Troubleshoot Cluster Issues

Diagnose and fix common cluster problems.

## Instructions

When the user reports an issue, follow this workflow:

### Step 1: Identify the Problem Category

1. **Node issues** — node not Ready, can't join cluster
2. **Pod issues** — crashing, not starting, pending
3. **Network issues** — services unreachable, DNS failures
4. **Storage issues** — PVC pending, mount failures
5. **GitOps issues** — Flux not reconciling, deployments not updating
6. **Cert/TLS issues** — Certificate stuck, ingress serving wrong cert

### Step 2: Run Diagnostics

#### Node Issues
```bash
KUBECONFIG=/home/al/.kube/config kubectl get nodes -o wide
KUBECONFIG=/home/al/.kube/config kubectl describe node <node> | tail -50
tailscale status | grep <node>
```

#### Pod Issues
```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -n <namespace>
KUBECONFIG=/home/al/.kube/config kubectl describe pod -n <namespace> <pod>
KUBECONFIG=/home/al/.kube/config kubectl logs -n <namespace> <pod> --tail=50
KUBECONFIG=/home/al/.kube/config kubectl logs -n <namespace> <pod> --previous
```

#### Network Issues
```bash
# DNS
KUBECONFIG=/home/al/.kube/config kubectl get pods -n kube-system -l k8s-app=kube-dns
KUBECONFIG=/home/al/.kube/config kubectl logs -n kube-system -l k8s-app=kube-dns --tail=30

# Ingress
KUBECONFIG=/home/al/.kube/config kubectl get svc -n kube-system traefik
KUBECONFIG=/home/al/.kube/config kubectl logs -n kube-system -l app.kubernetes.io/name=traefik --tail=30

# Pod-level routes (on the affected node)
ip route | grep 10.42

# NetworkPolicy review for the affected namespace
KUBECONFIG=/home/al/.kube/config kubectl get networkpolicy -n <namespace>
```

#### GitOps Issues
```bash
KUBECONFIG=/home/al/.kube/config flux get all -A
KUBECONFIG=/home/al/.kube/config kubectl logs -n flux-system -l app=kustomize-controller --tail=30
KUBECONFIG=/home/al/.kube/config kubectl logs -n flux-system -l app=source-controller --tail=30
```

#### Cert / TLS Issues
```bash
KUBECONFIG=/home/al/.kube/config kubectl get certificate -A
KUBECONFIG=/home/al/.kube/config kubectl describe certificate <name> -n <namespace>
KUBECONFIG=/home/al/.kube/config kubectl get certificaterequest -A
KUBECONFIG=/home/al/.kube/config kubectl logs -n cert-manager -l app=cert-manager --tail=50
```

### Step 3: Check Known Issues

- `docs/troubleshooting/` — incident playbooks and known issues
- `docs/infrastructure/cluster/` — cluster stability reference and runbooks
- `docs/infrastructure/operations/` — operational runbooks

### Step 4: Common Fixes

#### Flannel routes lost (after Tailscale upgrade)
```bash
sudo systemctl restart k3s-agent  # worker
sudo systemctl restart k3s        # control plane
```

#### DNS not working
```bash
KUBECONFIG=/home/al/.kube/config kubectl rollout restart deployment/coredns -n kube-system
```

#### Flux not syncing
```bash
KUBECONFIG=/home/al/.kube/config flux reconcile source git flux-system
KUBECONFIG=/home/al/.kube/config flux reconcile kustomization flux-system
```

#### Pod stuck Pending
```bash
KUBECONFIG=/home/al/.kube/config kubectl describe pod -n <namespace> <pod> | grep -A 10 Events
```
Common causes: resource constraints, node selectors, taints, image-pull failures, PVC binding.

### Step 5: Document New Issues

If a new issue is discovered and resolved, add an entry to `docs/troubleshooting/` following the existing format:
- Problem Summary
- Symptoms
- Investigation Steps
- Root Cause
- Solution
- Prevention
