# Node Maintenance

What runs on each node, what a drain does to it, and the `just
node-maintenance` flow that wraps both.

## What runs on each node

From the [capacity ledger](../cluster/capacity.md) and the topology labels
in `infrastructure/ansible/inventory/hosts.yml`:

- **asio** — control plane, etcd, host node exporter. `topology.kubani.io/usage-class: general`, no `role` label. No new application workloads (capacity ledger ceiling policy).
- **rig0** — platform node: the gpu-brokers, PostgreSQL, Redis, Authentik, Temporal, the registry, Qdrant, FalkorDB, and the monitoring stack are the intended home once Phase 0 lands. `topology.kubani.io/usage-class: general`, also the operator's workstation.
- **sparky** — vLLM engines (main, fast, embeddings), DCGM exporter, Alloy. `topology.kubani.io/usage-class: inference`, tainted `nvidia.com/gpu=true:NoSchedule` — nothing schedules here without a matching toleration. Longhorn scheduling is disabled on this node; it is a GPU node, not a storage node.
- **strix** — carries `topology.kubani.io/role: database`, the only node with that label. PostgreSQL's `HelmRelease` requires it via `nodeAffinity` (`infrastructure/gitops/apps/postgresql/helmrelease.yaml`), so PostgreSQL is pinned here today regardless of the platform-node target above. Otherwise general-purpose overflow.

Two workloads are pinned by explicit `nodeSelector` rather than by the
general topology labels above, and are worth knowing before you drain
anything:

- Authentik's `server` replica is pinned to `asio`; its `worker` replica is
  pinned to `strix` (`infrastructure/gitops/apps/authentik/helmrelease.yaml`).
- Prometheus explicitly avoids `rig0` and `asio` via `nodeAffinity`
  (`infrastructure/gitops/apps/monitoring/prometheus-helmrelease.yaml`), so
  in practice it lands on `strix` today (`sparky` is tainted against it).

Treat the ledger's per-node role list as the target layout the platform is
moving toward; treat this section's pinned exceptions as what is actually
enforced by a manifest today. If a service you're about to drain is not
in either list, check its `Deployment`/`HelmRelease` for a `nodeSelector`
or `affinity` block before assuming it will reschedule freely.

## What a drain does to each node

- **sparky**: draining forces a full vLLM engine restart — about 5 minutes
  per engine (weight load, kernel compile, warmup; see
  `docs/infrastructure/inference/release-process.md` and the cold-start
  breakdown in the roadmap's baseline). Restart the `fast` model first,
  then `main`, so the canary proves the node is healthy before the
  maintenance-window restart. Never `kubectl rollout restart` — delete the
  pod (see `docs/troubleshooting/vllm-main-engine-hang-gb10.md`).
- **rig0**: everything in the platform tier restarts — brokers, and
  whichever of PostgreSQL/Redis/Authentik/Temporal/registry/Qdrant/
  FalkorDB/monitoring is actually scheduled there at drain time. Expect a
  short window (seconds to low minutes per workload) rather than sparky's
  multi-minute engine restart, but expect *all* of it at once unless you
  cordon and evict selectively.
- **asio**: single control-plane node, no HA etcd quorum yet (Phase 6 adds
  a second). Draining it is not possible without a control-plane outage —
  do not drain; use `kubectl cordon` only for the brief window a host
  maintenance task needs, and keep it short.
- **strix**: draining moves PostgreSQL (and, if pinned there at the time,
  the Authentik worker and Prometheus) — plan a PostgreSQL restart window
  around any strix maintenance the same way you would for rig0.

## `just node-maintenance` flow

```
just node-maintenance <host> pre    # cordon, pre-checks
# ... do the host work (reboot, driver update, OS patch) ...
just node-maintenance <host> post   # uncordon, verify, drift bench
```

`pre` cordons the node and runs the pre-checks appropriate to it (on
sparky: confirm every local-path PVC is re-creatable, the image cache
state, and that `age.key` and the cluster kubeconfig are not present on
the node — see the host-window rollback note for stage 1.7 in the
roadmap). `post` uncordons, waits for the node's workloads back to Ready,
and runs a drift bench
(`docs/infrastructure/inference/release-process.md`'s "watch for
degradation" section) since a host change is exactly the kind of change
that needs one. See the `host-maintenance` skill for the guided version of
this flow on sparky specifically (driver/DGX OS windows).

## Related documentation

- [Capacity ledger](../cluster/capacity.md)
- [Maintenance calendar](maintenance-calendar.md)
- [Platform release process](release-process.md) — host driver/OS changes
  are a change-record profile of their own
- `docs/troubleshooting/vllm-main-engine-hang-gb10.md` — why `kubectl
  rollout restart` is never the recovery step on a Flux-managed Deployment
