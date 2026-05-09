# Validate Cluster Health

Run comprehensive cluster validation to check services, DNS, connectivity, and Kubernetes resources.

## Instructions

```bash
KUBECONFIG=/home/al/.kube/config ./infrastructure/scripts/validate_cluster.sh --full
```

Or via just:

```bash
just validate-cluster
```

For static (no-cluster-required) checks:

```bash
just validate-local         # inventory + secrets + kustomize build
just validate-gitops-build  # kubectl kustomize all roots
just validate-flux          # flux Kustomization sanity check
```

## What `validate_cluster.sh` Checks

1. **Core Kubernetes Components** — CoreDNS, metrics-server, local-path-provisioner, Traefik LoadBalancer + IP
2. **Flux CD GitOps** — controllers (source, kustomize, helm, notification), Kustomizations, HelmReleases
3. **Infrastructure Services** — cert-manager, external-dns, gpu-operator, prometheus, grafana
4. **Application Services** — postgresql, redis, authentik, temporal, vllm
5. **DNS Resolution** (standard/full) — `*.almckay.io` resolves to Traefik IP
6. **HTTPS Connectivity** (standard/full) — endpoint reachability, TLS validity
7. **TCP Services** (standard/full) — postgres (5432), redis (6379)
8. **TLS Certificates** (full) — cert-manager Certificate state
9. **Node Health** (full) — Kubernetes nodes Ready

## Modes

- `--quick`: Kubernetes resources only (fast)
- (default): resources + DNS + connectivity
- `--full`: all checks including certificates and nodes

## Result Categories

- **Pass**: all checks successful
- **Warning**: non-critical issues (e.g., DNS pointing to wrong IP but services reachable)
- **Fail**: critical issues that need attention

## Quick Remediation

```bash
flux get all -A
kubectl get helmreleases -A -o wide
kubectl get pods -A | grep -v Running
kubectl get events -A --sort-by='.lastTimestamp' | tail -20

flux reconcile source git flux-system
flux reconcile kustomization flux-system
```

## Rollback Procedure

If a recent change caused issues:

```bash
git log --oneline -10
git revert HEAD
git push
flux reconcile source git flux-system --with-source
flux reconcile kustomization flux-system
```

## After Analyzing Results

Provide a summary of:
1. Overall cluster health
2. Failing or warning checks
3. Recommended actions
4. Whether a rollback is recommended
