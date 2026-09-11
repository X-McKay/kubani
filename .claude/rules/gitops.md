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

## NetworkPolicy Conventions

All policies live in `infrastructure/gitops/infrastructure/networking/`, one
`netpol-<namespace>.yaml` per namespace. Do not add policies beside workloads.
Every operational namespace carries the same base set: `default-deny-ingress`,
`allow-same-namespace`, `allow-traefik-ingress`, `allow-dns-egress`, then
explicit cross-namespace rules on top.

- Rules that admit kube-system must select pods, not the namespace: Traefik
  ingress uses `app.kubernetes.io/name: traefik`, DNS egress uses
  `k8s-app: kube-dns`. Whole-namespace grants were removed on 2026-09-09.
- `allow-dns-egress` selects every pod with `policyTypes: [Egress]`, so egress
  in that namespace is DNS-only until another rule adds more. Add a named
  egress rule per destination (see `allow-egress-to-database` in
  `netpol-auth.yaml`), never widen the DNS rule.
- Helm charts must not ship their own policy. Bitnami charts default
  `networkPolicy.enabled: true` and admit any source; set it false in the
  HelmRelease. Check the chart's values for where the key lives:
  PostgreSQL 16.x reads it under `primary`, Redis 20.x at the top level.
- Verify with a throwaway pod that sleeps ~20s before connecting. The policy
  engine adds a new pod's IP to its allow sets after a short delay, so an
  instant probe from an allowed namespace reports blocked and is misleading.
  Tailscale clients reach services through Traefik, so `allow-traefik-ingress`
  is the only rule external access needs.
- Node-originated traffic is a client too, and it never passes through Traefik
  or a pod. Kubelet image pulls hit the registry Service directly from the
  node's flannel.1 (`10.42.<n>.0`) or cni0 (`10.42.<n>.1`) address; kubelet
  probes arrive from cni0. Before adding default-deny to a namespace, list
  every client including hosts, and verify each real path afterwards: a
  policy that passes an HTTP check through Traefik can still break
  `crictl pull` on every node, which is what happened to the registry on
  2026-09-09.

## Active Cluster Namespaces

Cluster-services namespaces managed from this repo:

- `flux-system` — GitOps controllers
- `cert-manager` — TLS cert issuance
- `external-dns` — DNS automation
- `gpu-operator` — NVIDIA driver/runtime
- `longhorn-system`, `nfs-csi-driver`, `smb-csi-driver`, `nas-storage` — storage
- `database` — postgresql, falkordb, qdrant
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
