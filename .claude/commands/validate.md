# Validate Cluster Health

Run comprehensive cluster validation to check all services, DNS, connectivity, and Kubernetes resources.

## Instructions

Run the cluster validation script to verify all services are healthy:

```bash
KUBECONFIG=/home/al/.kube/config ./scripts/validate_cluster.sh --full
```

## What Gets Checked

1. **Core Kubernetes Components**
   - CoreDNS, metrics-server, local-path-provisioner
   - Traefik LoadBalancer and its IP

2. **Flux CD GitOps**
   - All Flux controllers (source, kustomize, helm, notification)
   - Kustomizations status
   - HelmReleases status

3. **Infrastructure Services**
   - cert-manager, external-dns, gpu-operator
   - prometheus, grafana, loki, promtail

4. **Application Services**
   - postgresql, redis, authentik
   - temporal, vllm, open-webui, weave-gitops

5. **DNS Resolution** (standard/full mode)
   - All *.almckay.io hostnames
   - Verification against Traefik IP

6. **HTTPS Connectivity** (standard/full mode)
   - All web endpoints accessibility
   - TLS certificate validity

7. **TCP Services** (standard/full mode)
   - PostgreSQL (5432), Redis (6379)

8. **TLS Certificates** (full mode only)
   - All cert-manager certificates

9. **Node Health** (full mode only)
   - All Kubernetes nodes

## Validation Modes

- `--quick`: Only checks Kubernetes resources (fast)
- Default: Checks resources + DNS + connectivity
- `--full`: All checks including certificates and nodes

## Interpreting Results

- **Pass**: All checks successful
- **Warning**: Some non-critical issues (e.g., DNS pointing to wrong IP but services reachable)
- **Fail**: Critical issues that need attention

## Quick Remediation Commands

If validation fails, use these commands to investigate:

```bash
# Check Flux status
flux get all -A

# Check HelmRelease issues
kubectl get helmreleases -A -o wide

# Check pod issues
kubectl get pods -A | grep -v Running

# Check recent events
kubectl get events -A --sort-by='.lastTimestamp' | tail -20

# Force reconciliation
flux reconcile source git flux-system
flux reconcile kustomization flux-system
```

## Rollback Procedure

If changes caused issues:

1. Check recent git commits:
   ```bash
   git log --oneline -10
   ```

2. Revert to last known good state:
   ```bash
   git revert HEAD
   git push
   ```

3. Force Flux reconciliation:
   ```bash
   flux reconcile source git flux-system --with-source
   flux reconcile kustomization flux-system
   ```

## After Analyzing Results

Provide a summary of:
1. Overall cluster health status
2. Any failing or warning checks
3. Recommended actions for any issues found
4. Whether a rollback is recommended
