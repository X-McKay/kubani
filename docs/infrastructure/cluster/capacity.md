# Capacity Ledger

The source of truth for what each node can hold and what already claims a
slice of it. `just capacity` compares this file with reality
(`kubectl top nodes` and per-namespace requests) and is non-zero if any
node is above its ceiling. **A PR that adds or resizes a workload edits
this file as part of the same PR** — see roadmap section 9.1 rule 5 and
the [platform release process](../operations/release-process.md)'s
mandatory capacity ledger check.

## Nodes

Allocatable and the ceiling policy for each. "Mem ceiling %" is the
working-set percentage a node is not expected to cross; going over it
stops a rollout in progress (see the release process's "stop the line"
rule).

| Node | Role | CPU alloc | Mem alloc (GiB) | Mem ceiling % | Notes |
|---|---|---|---|---|---|
| asio | control plane, etcd | 8 | 15 | 65 | no new app workloads |
| rig0 | platform node | 27.5 | 50 | 75 | target for all new services |
| sparky | GPU, tainted nvidia.com/gpu | 15.5 | 110 | 80 | only vLLM, Alloy, DCGM; unified memory so GPU-resident bytes count |
| strix | small worker | 7 | 13 | 70 | overflow only |

## Workloads

Every workload with a requests/limits line, and the node it targets.
Figures for anything not yet live are starting values, to be corrected
from the observed-use snapshot after one week per roadmap section 9.2 —
the vLLM figures below already reflect that correction from the 2026-09-29
baseline.

| Service | Namespace | CPU req/lim | Mem req/lim | Node |
|---|---|---|---|---|
| gpu-broker | vllm | 100m / 1 | 128Mi / 512Mi | rig0 |
| gpu-broker-main | vllm | 100m / 1 | 128Mi / 512Mi | rig0 |
| vLLM main | vllm | 2 / — | 48Gi / 56Gi | sparky |
| vLLM fast | vllm | 500m / — | 12Gi / 16Gi | sparky |
| vLLM embeddings (replicas 0) | vllm | 500m / — | 12Gi / 14Gi | sparky |
| Prometheus server | monitoring | 250m / 1 | 1.5Gi / 3Gi | rig0 |
| Alertmanager | monitoring | 50m / 200m | 64Mi / 256Mi | rig0 |
| kube-state-metrics | monitoring | 50m / 200m | 128Mi / 256Mi | rig0 |
| Grafana | monitoring | 100m / 500m | 256Mi / 512Mi | rig0 |
| Loki (single binary) | monitoring | 200m / 1 | 512Mi / 1Gi | rig0 |
| Alloy (DaemonSet) | monitoring | 100m / 500m | 128Mi / 384Mi | every node |
| ntfy | monitoring | 20m / 100m | 32Mi / 128Mi | rig0 |
| Probe sidecar (vLLM watchdog) | vllm | 20m / 100m | 32Mi / 64Mi | sparky |
| agentgateway control plane | ai-gateway | 100m / 500m | 128Mi / 512Mi | rig0 |
| agentgateway data plane | ai-gateway | 100m / 1 | 128Mi / 512Mi | rig0 |
| Tempo (monolithic) | monitoring | 200m / 1 | 512Mi / 1Gi | rig0 |

vLLM main and fast carry a memory request now (Phase 0.4); embeddings
stays at `replicas: 0` (optional tier) but keeps a ledger line so
scaling it up has a pre-agreed number rather than a guess. Everything
else below the vLLM rows is planned (Phase 0.1 onward) and lands as its
own PR, each editing this file when it does.

## Observed use (2026-09-30 snapshot, `kubectl top nodes`)

| Node | Working-set memory |
|---|---|
| asio | 42% |
| rig0 | 53% |
| sparky | 26% cgroup-visible, plus ~48 GiB GPU-resident |
| strix | 18% |

Sparky's two numbers are both real: the cgroup figure is what `kubectl
top` and node exporter see, and the GPU-resident figure is unified memory
vLLM holds that never shows up in a cgroup counter. Read both against the
80% ceiling, which already accounts for the GPU-resident share.

## Reading cadence (roadmap 9.3)

Every stage of a rollout is read against this table at T+15 min, T+2 h,
and T+24 h; the 24 h reading is what corrects a ledger line from a
starting estimate to an observed one.

| Signal | Where | Threshold that stops a stage |
|---|---|---|
| Node memory % (working set) | `kubectl top nodes`; node exporter panel | any node above its ceiling above |
| Node memory on sparky incl. GPU | `free -g` on the node, `DCGM_FI_DEV_FB_USED`, vLLM "Free memory on device" log line | available below 15 GiB |
| Pod restarts | kube-state-metrics `kube_pod_container_status_restarts_total` | any restart of a new service in the soak window |
| OOMKilled | `kube_pod_container_status_last_terminated_reason` | any |
| CPU throttling | `container_cpu_cfs_throttled_periods_total` | above 25% of periods for a hot-path pod (gateway, broker) |
| PVC fill | `kubelet_volume_stats_used_bytes` | above 70% |
| Prometheus own TSDB | `prometheus_tsdb_head_series` | growth above 20% after a stage that added no targets |
| GPU | `DCGM_FI_DEV_GPU_UTIL`, power, `DCGM_FI_DEV_XID_ERRORS` | any Xid |
| Flux | `gotk_reconcile_condition` | not Ready for more than one interval |

## Related documentation

- [Platform release process](../operations/release-process.md) — the
  capacity ledger check as a mandatory change-record field
- [Node maintenance](../operations/node-maintenance.md) — what runs on
  each node and what a drain does to it
- `docs/plans/ideas/2026-09-29-inference-platform-roadmap.md` sections
  9.2–9.3 — the source rollout-time figures this ledger was seeded from
