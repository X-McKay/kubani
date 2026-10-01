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

### Image tag rule (arch and CUDA variant)

A tag existing in the registry does not mean it runs on this node. Sparky is
a GB10: `aarch64`, sm_121, CUDA 13. Verify a candidate vLLM image against
*this* build before it reaches a manifest:

- Confirm the tag is built for `aarch64`, not just `amd64`.
- Confirm the CUDA variant matches the driver on the node. Getting this wrong
  is not hypothetical: `v0.30.0-aarch64-cu129` could not start on sparky
  (torch 2.14.0+cu130 paired with torchvision 0.28.0+cu129 — `vllm` dies on
  import with `torchvision::nms does not exist`); `v0.30.0-aarch64` (cu130)
  is the tag that actually works there.
- Preflight every candidate image, flag, flag value and optional package with
  `just inference-preflight <image> [--module <pkg>] [--flag --<flag>=<value>]`
  before it reaches a manifest. This also pre-pulls the image on the node, so
  both the rollout and a rollback avoid a multi-GB pull. Upstream docs
  describing a flag are not evidence it exists in this build — only the
  preflight is.

## Manifest Standards

- Use `app.kubernetes.io/name` for pod selection
- Always set resource `requests` and `limits` on every container
- Use `configMapRef` / `secretRef` for env config, never inline credentials
- Every operational namespace has default-deny `NetworkPolicy`; add explicit
  ingress-allow and egress-allow rules for each cross-namespace path (a
  "NetworkPolicy pair", not just ingress)
- PSA-restricted `securityContext` on every container: `runAsNonRoot: true`,
  `capabilities: {drop: ["ALL"]}`, `seccompProfile: {type: RuntimeDefault}`,
  `allowPrivilegeEscalation: false`
- A `topology.kubani.io/*` nodeSelector — placement follows the topology
  labels, never a hostname (see `.claude/CLAUDE.md`)
- A line in the capacity ledger (`docs/infrastructure/cluster/capacity.md`)
  before the PR merges — `just capacity` checks it against the cluster
- `reloader.stakater.com/auto: "true"` on any workload that reads a
  ConfigMap or Secret, so a value change actually reaches the running pod
  (env vars from `secretKeyRef`/`configMapKeyRef` do not hot-reload
  otherwise — see `.claude/rules/secrets.md`)

Start new services from `infrastructure/gitops/_templates/service/`
(`deployment.yaml`, `service.yaml`, `netpol.yaml`, `ingress.yaml`,
`pdb.yaml`, `kustomization.yaml`, `auth.md`) via `just new-service <name>
<namespace>` rather than writing these from scratch — the template already
carries every item above.

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
- `ai-gateway` — agentgateway (Phase 2): model routing, API-key budgets,
  MCP backends in Phase 4. See `.claude/rules/auth.md` and
  `.claude/skills/gateway-onboard/SKILL.md`.
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
