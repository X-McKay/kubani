# Move Control Plane to asio, Free sparky for Fine-Tuning

**Status:** Completed 2026-08-16
**Date:** 2026-08-16
**Plan:** `2026-08-16-control-plane-to-asio-plan.md` (same directory)

## Outcome (verified 2026-08-16)

- asio is the sole K3s server (`control-plane,etcd`), embedded etcd, at
  `https://100.92.107.71:6443`. Ansible provisioning converges idempotently.
- sparky is a worker with `nvidia.com/gpu=true:NoSchedule`, labels
  `node-role=worker` / `usage-class=inference`, zero Longhorn replicas, and
  only daemonset pods. GPU stack healthy: cuda-validator passed, 4 GPU
  time-slices allocatable.
- Memory on sparky: k8s-tracked usage 6261Mi → 3182Mi; host `available`
  114Gi; node allocatable ~110.7Gi for pods.
- Flux fully Ready; `just drift` reports only the two known service-level
  divergences (below). Registry pod recovered (was Pending on cordoned PV).
- sparky's nvidia device-plugin/dcgm crashloops self-healed during the
  migration restarts — GPU is schedulable for fine-tuning now.

## Follow-ups (out of scope, flagged)

1. **`postgresql` StatefulSet is scaled to 0** — single root cause of every
   remaining failure: temporal (4 pods crashlooping), authentik-server not
   Ready, and 5xx on auth/qdrant/falkordb ingress (authentik forward-auth
   middleware fails without its DB).
2. **`gpu_support` Ansible role deploys a broken duplicate device plugin**
   into kube-system (crashloops on missing `/etc/nvidia/config.yaml`,
   conflicts with the gpu-operator's plugin). It was deleted from the
   cluster after `add_node.yml` created it; the role needs fixing before
   the next provisioning run against a GPU host recreates it.
3. **Unknown host `osprey`** connected to the cluster as an agent during the
   migration (asio journal: "Handling backend connection request [osprey]").
   Not in inventory, no node object, but it holds a valid join token — the
   token survived the migration unchanged. Identify the machine or rotate
   the token.
4. **external-dns** still published sparky's IP shortly after migration;
   verify records converge now that sparky no longer runs svclb.
5. **vLLM** stays paused (deliberate, for fine-tuning); re-enable later.

## Goal

Relocate the K3s control plane from sparky to asio and move all active
non-daemonset services off sparky, so sparky's memory (125Gi) is available for
in-cluster model fine-tuning. vLLM endpoints are already paused and stay out of
scope.

## Current State (verified 2026-08-16)

| Node | Arch | CPU / Mem | Role today | Notes |
|---|---|---|---|---|
| sparky | arm64 | 20 / 125Gi | Sole K3s server (embedded **sqlite**) | DGX Spark; taint `gpu-workloads=true:PreferNoSchedule`; hosts all platform pods |
| asio | amd64 | 8 / 15Gi | Worker, **cordoned** | No special role |
| strix | amd64 | 8 / 15Gi | Worker, **cordoned** | `topology.kubani.io/role=database` |
| rig0 | amd64 | 32 / 60Gi | Worker | Operator workstation; RTX 5090; runs Traefik, FalkorDB, Qdrant, Redis, Authentik |

Because asio and strix are cordoned, every non-daemonset platform workload
(Flux controllers, cert-manager, external-dns, Longhorn CSI sidecars + UI,
metrics-server, local-path-provisioner, reloader, Temporal, CoreDNS replica)
has piled onto sparky.

Confirmed facts that shape the design:

- K3s uses the default embedded sqlite datastore — a second server cannot join
  until the datastore is migrated to embedded etcd (`cluster-init`).
- Longhorn has three volumes; one detached 20Gi volume's **only replica lives
  on sparky** and must be evicted before sparky is touched.
- The registry pod is Pending because its local-path PV is pinned to a
  cordoned node; uncordoning resolves it.
- Inventory drift: rig0's `nvidia.com/gpu:NoSchedule` taint exists in
  `inventory/hosts.yml` but not on the live node. Decision: **remove it from
  the inventory** — rig0 stays a general worker with a GPU; databases keep
  running there.
- Pre-existing failures, explicitly out of scope but flagged:
  - Temporal crashloops (66 days) because the `postgresql` StatefulSet is
    scaled to 0. Moving the pods does not fix this.
  - sparky's nvidia device-plugin and dcgm-exporter are crashlooping. This
    must be fixed before in-cluster fine-tuning can claim the GPU, as
    separate work.

## Decisions

1. **Uncordon both asio and strix** — cordons are leftover, confirmed safe.
2. **asio becomes the control plane** — strix keeps its database role;
   spreading control plane and databases across nodes limits blast radius.
3. **Fine-tuning runs in-cluster on sparky** — sparky remains a K3s worker
   with taint upgraded to `nvidia.com/gpu=true:NoSchedule`; fine-tuning
   workloads tolerate it.
4. **Migration method: sqlite → embedded etcd, join, demote** — K3s's
   supported path. Cluster identity, certs, and join tokens survive.

## End State

- **asio**: sole K3s server, embedded etcd, uncordoned, runs platform services.
- **strix**: worker, uncordoned, keeps `topology.kubani.io/role=database`.
- **sparky**: K3s agent only. `nvidia.com/gpu=true:NoSchedule` taint
  (Amended: gpu-operator daemonsets tolerate only the nvidia.com/gpu key). Longhorn
  scheduling disabled on sparky, replica evicted. Freed: k3s server components
  (~2–4Gi), platform pods (~4–6Gi), Longhorn instance-manager, Temporal
  crashloop churn.
- **rig0**: untouched at runtime; inventory taint entry removed to match
  reality. No Ansible provisioning run against rig0 during this work.

## Phases

> **Amended execution order** (see implementation plan): Phase 0 → Phase 2
> steps 1–3 (promote asio while it is still cordoned and empty, re-point
> agents) → Phase 1 (rebalance) → Phase 2 steps 4–5 (demote sparky, taint)
> → Phase 3. Promoting first is zero-disruption because asio hosts nothing,
> and agents are never left pointing at a demoted server.

### Phase 0 — Preflight & backups (imperative, on sparky)

1. `just preflight`; verify asio/strix health (disk, memory, tailscale) to
   validate "safe to uncordon".
2. Back up on sparky, to sparky-local disk outside any git checkout:
   `/var/lib/rancher/k3s/server/db/`, `/var/lib/rancher/k3s/server/token`,
   and a copy of the operator kubeconfig. No secret material enters the repo.

### Phase 1 — Rebalance workloads off sparky

1. Uncordon asio and strix.
2. Longhorn: disable scheduling on the sparky node, evict its replica; wait
   for the rebuild on another node to reach healthy.
3. Drain sparky's non-daemonset pods so they reschedule onto asio/strix/rig0.
4. Audit daemonset tolerations ahead of the NoSchedule taint: nfs/smb CSI
   node, node-exporter, gpu-operator stack, and svclb must either tolerate it
   or be accepted losses on sparky (Longhorn DS pods are no longer wanted
   there anyway).

### Phase 2 — Control-plane migration

1. On sparky: stop k3s, add `cluster-init: true` to the server config, start
   k3s → built-in sqlite→etcd migration.
2. Join asio as a second server (join token read from sparky at run time —
   never committed).
3. Verify two etcd members and API health via asio; add asio's tailscale IP
   to `tls-san`; re-point the operator kubeconfig at asio.
4. Demote sparky: stop the k3s server, remove its etcd member
   (`etcd.k3s.cattle.io/remove=true`), reinstall k3s **agent** on sparky
   pointing at asio. Node name is preserved.
5. Apply `nvidia.com/gpu=true:NoSchedule` to sparky.

### Phase 3 — Repo reconciliation

- `inventory/hosts.yml`: asio → `control_plane` (etcd/cluster-init vars),
  sparky → `workers` with NoSchedule gpu taint and inference labels kept,
  rig0 taint entry removed, header comment updated.
- `k3s_control_plane` role: support `cluster-init: true` and server-join so
  `just provision` converges on the new topology.
- Docs: update runbooks that name sparky as control plane; `just drift`
  should come back clean.
- No GitOps manifest changes are required for the migration itself.

## Risks & Rollback

- **Two-member etcd window** during the join has no quorum fault tolerance.
  If asio dies mid-migration, sparky still holds the data — restart its k3s.
  Before demotion, rollback is always "sparky is still a server."
- **After demotion**, rollback = rejoin sparky as a server against asio.
- **Longhorn replica eviction happens before any k3s surgery**, so volume
  data is never resident on a node being reinstalled.
- rig0 is the operator's workstation: no provisioning runs target it, and no
  K3s restart on rig0 occurs in any phase.

## Verification

- `just validate-cluster`, `just flux-status` green.
- `kubectl get nodes`: asio shows `control-plane,master`; sparky shows worker
  with the NoSchedule taint; nothing cordoned.
- All evicted pods Running on other nodes; registry pod scheduled; Longhorn
  volumes healthy with no replicas on sparky.
- Memory footprint on sparky measured before/after via node stats.
