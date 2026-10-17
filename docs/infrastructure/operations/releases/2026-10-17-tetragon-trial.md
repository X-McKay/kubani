# 2026-10-17 Tetragon eBPF trial on strix

**Status:** in progress (ring 1 since 2026-10-17 21:52Z)
**Profile:** platform
**Scope:** host (eBPF programs in strix's kernel); new `tetragon` namespace;
Prometheus scrape job; strix node label
**Window:** no downtime expected. The agent only observes; nothing is
enforced or blocked.

Plan: `docs/plans/ideas/2026-10-17-mcp-gateway-openshell-tetragon.md`,
sections 4 (design and 2-week gates) and 6 (testing and rollback).

## Change
| | Before | After |
|---|---|---|
| Version / image | none | Tetragon chart 1.7.1 (`quay.io/cilium/tetragon:v1.7.1`, operator `quay.io/cilium/tetragon-operator:v1.7.1`) |
| Flags / config | none | agent on nodes labelled `topology.kubani.io/ebpf-trial=true` (strix only), no tolerations, stdout export to Loki, metrics on :2112; operator on rig0 |
| Policies | none | stage 1: built-in process exec/exit only. Stage 2: `sensitive-files` and `egress-outside-cluster` TracingPolicies, observe only |

## Why
Find out what an eBPF runtime-security layer shows on the database node,
at what cost, before deciding whether to remove it, extend it to rig0, or
add enforcement. strix is the only node left after excluding rig0, sparky
and the control plane.

## Risks and rollback
**Rollback commit SHA:** `2474e6f84aef5481bb8ccd4bac5cf0fede7a83e1` (merge of #204),
recorded before strix was labelled.

Risks: kprobe overhead on a 7-core node that runs Postgres and FalkorDB;
event volume into Loki; the agent is privileged with hostPID and
hostNetwork; exec arguments carrying credentials (FalkorDB starts with
`--requirepass <password>`) reaching Loki, which `redactionFilters` in the
HelmRelease prevents and ring 1 checks first.

**Fast stop** (seconds, no Flux involvement, because the label is an
inventory label and not a Flux object):

```bash
KUBECONFIG=/home/al/.kube/config kubectl label node strix topology.kubani.io/ebpf-trial-
```

The DaemonSet then has no node to run on, the agent pod terminates, and
Tetragon unloads its BPF programs on shutdown. Stage 2 alone can be backed
out by commenting `policies/` out again in
`infrastructure/gitops/infrastructure/tetragon/kustomization.yaml`.

**Full rollback:**

1. Fast stop above, if not already done.
2. `git revert <rollback sha>`, push, `just flux-reconcile`. `prune: true`
   removes the HelmRelease, namespace, network policy, Prometheus job and
   the extra egress port. The revert also drops the `ebpf-trial` line from
   the inventory, which does not unlabel the node; step 1 does that.
3. Clean up what the revert leaves:
   - TracingPolicy CRDs, installed by the operator and not removed by Helm:
     `kubectl get crd | grep cilium.io`, then delete the Tetragon ones
     (`tracingpolicies`, `tracingpoliciesnamespaced`, `podinfo` if present).
   - On strix: `sudo ls /sys/fs/bpf/tetragon`. It should be absent or empty;
     if programs are still pinned there, `sudo rm -rf /sys/fs/bpf/tetragon`.
4. Verify the same way as the rollout: `just flux-status` all Ready, no
   pods in `tetragon`, `just capacity` back to the baseline, Postgres and
   FalkorDB readings unchanged from the baseline.

## Capacity ledger check
Yes: agent + export sidecar 120m / 1.1 CPU, 288Mi / 832Mi on strix;
operator 20m / 200m, 64Mi / 128Mi on rig0. Both lines added to
`docs/infrastructure/cluster/capacity.md` in the same PR.

## Stages

0. **Preflight (ring 0, no cluster impact)**
   - `just pre-push-check`; both TracingPolicies validated against the
     v1.7.1 CRD schema.
   - On strix: `ls /sys/kernel/btf/vmlinux` exists (Tetragon needs BTF).
   - **Baseline**, recorded below before merging: `just capacity`, strix
     CPU and memory, Postgres mean query time, FalkorDB TIMEOUT count in
     Loki over the last 24 h.
1. **Merge, nothing labelled yet.** After `just flux-reconcile`:
   - `flux get helmreleases -n tetragon` Ready.
   - The operator is Running on rig0 and
     `kubectl get crd tracingpolicies.cilium.io` exists.
   - `kubectl get ds -n tetragon tetragon` shows **desired 0**. This proves
     the agent will not spread to sparky, asio or rig0.
2. **Ring 1: label strix** (the same label the inventory now records, so the
   next provisioning run keeps it):
   `kubectl label node strix topology.kubani.io/ebpf-trial=true`.
   Gate:
   - **Redaction first.** On strix, run
     `/bin/true --requirepass kubani-sentinel-1 postgres://u:kubani-sentinel-2@h`.
     Within a minute, `tetra getevents -o compact` and Loki
     (`{namespace="tetragon"} |= "kubani-sentinel"`) must show no match, and the
     same exec event must show `*****` in their place. A match is a fast
     stop. Then search Loki for `requirepass` in the `tetragon` namespace,
     and if FalkorDB's real password appears, rotate it per
     `.claude/rules/secrets.md` ("Rotating a Credential").
   - DaemonSet desired 1, the pod Running on strix, no restarts.
   - `kubectl exec -n tetragon ds/tetragon -c tetragon -- tetra status` is
     healthy.
   - An exec into the Postgres pod shows up in
     `tetra getevents -o compact --namespace database` and in Loki.
   - Prometheus target `tetragon` is up.
   - Agent CPU under 5% of a core and strix memory under its 80% ceiling at
     T+15 min, T+2 h and T+24 h; no Postgres or FalkorDB regression vs the
     baseline.
3. **Ring 2: stage 2 policies**, as a separate one-line PR that uncomments
   `policies/`. Gate:
   - `tetra tracingpolicy list` shows both policies enabled.
   - On strix, `sudo head -c1 /etc/shadow > /dev/null` (a real one-byte
     read; `-c0` opens without reading and would not fire the hook)
     produces a `PROCESS_KPROBE` event for `security_file_permission` on
     `/etc/shadow`, not just the exec event for `head`. `curl -sI
     https://example.com` produces a `PROCESS_KPROBE` event for
     `tcp_connect`.
   - The same CPU, memory, latency and Loki-volume readings as ring 1.
4. **Soak**: 2 weeks against the gate table in plan section 4.4. Any gate
   failure, or a node crossing its ceiling, means the fast stop first and
   the investigation second.

## Ring 1 results (2026-10-17)

- Stage 1 merge: HelmRelease Ready, operator Running on rig0,
  `tracingpolicies.cilium.io` present, DaemonSet desired **0** before the
  label. Rendered DaemonSet has no tolerations.
- 21:52Z: strix labelled. Agent Ready on strix only, 0 restarts,
  `tetra status` running.
- Redaction: `true --requirepass kubani-sentinel-1 postgres://u:kubani-sentinel-2@h`
  run in `postgresql-0` was exported as
  `--requirepass ***** postgres://u:*****@h`. Loki over the last 20 min:
  no `kubani-sentinel-` match, no unredacted
  `requirepass|masterauth|password` argument. **PASS**
- Prometheus `up{job="tetragon"}` = 1. At T+2 min: agent 16m CPU / 87 Mi,
  strix memory 23.5%.

## Resource readings
| | Baseline | T+15 min | T+2 h | T+24 h |
|---|---|---|---|---|
| strix memory % | 22.1% (24 h max 23.2%) | | | |
| Tetragon agent CPU (p95, cores) | n/a | | | |
| Pod restarts (`tetragon`, `database`) | database 0 | | | |
| Postgres active time per transaction (`pg_stat_database`; no `pg_stat_statements` exporter) | 0.92 ms (24 h), 0.85 ms (1 h) | | | |
| FalkorDB TIMEOUT errors (24 h) | 0 (no log lines at all in 24 h) | | | |
| Tetragon events into Loki (per day) | n/a (all of Loki: 478 MB/day) | | | |

## Decision
<kept / reverted, and why; ledger corrected from the T+24h reading: yes/no>
