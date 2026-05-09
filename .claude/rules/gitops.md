---
paths:
  - infrastructure/gitops/**/*
---

# GitOps Deployment Rules

When working with Kubernetes manifests in `infrastructure/gitops/`:

## Deployment Changes

- Prefer GitOps over direct `kubectl` commands.
- Changes under `infrastructure/gitops/` are auto-synced by Flux.
- After updating manifests, run `just validate-local`, then commit and push to trigger reconciliation.

## Image Updates

This repo no longer hosts a `ship` CLI. Image tags in workload manifests are owned by the workstream that builds the image. For workloads still defined here (cluster services, infra add-ons, third-party charts), edit the image tag directly and commit.

When bumping image tags:
- Note the prior tag in the commit message
- Verify the new tag exists in the registry before committing
- Watch `flux-status` and pod rollout after Flux picks it up

## Manifest Standards

- Use `app.kubernetes.io/name` for pod selection
- Always set resource `requests` and `limits`
- Use `configMapRef` / `secretRef` for env config, never inline credentials
- Every operational namespace has default-deny `NetworkPolicy`; add explicit allow rules for each cross-namespace path

## Active Cluster Namespaces

Cluster-services namespaces managed from this repo:

- `flux-system` — GitOps controllers
- `cert-manager` — TLS cert issuance
- `external-dns` — DNS automation
- `gpu-operator` — NVIDIA driver/runtime
- `longhorn-system`, `nfs-csi-driver`, `smb-csi-driver`, `nas-storage` — storage
- `database` — postgresql, neo4j, qdrant
- `cache` — redis
- `monitoring` — prometheus, grafana, alertmanager
- `auth` — authentik
- `temporal` — workflow orchestration
- `vllm` — LLM inference
- `registry` — cluster Docker image registry
- `reloader`, `descheduler` — operators

## Verification

After deploying, verify with:
```bash
KUBECONFIG=/home/al/.kube/config kubectl rollout status deployment/<name> -n <namespace>
KUBECONFIG=/home/al/.kube/config flux get all -A
```
