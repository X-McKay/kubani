# 2026-10-17 Tetragon eBPF trial on strix

**Status:** in progress. Ring 1 passed on run 2 (2026-10-17 23:23Z); ring 2 (stage 2 policies) next
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
2. Revert newest first, each merge with its mainline, then push and
   `just flux-reconcile`: `git revert -m 1 <merge of the export-filter PR>`,
   then `git revert -m 1 2474e6f84aef5481bb8ccd4bac5cf0fede7a83e1`. Reverting
   #204 alone conflicts with the later change to the same files. `prune: true`
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
     T+15 min and T+1 h (Al shortened the soak on 2026-10-17); no Postgres or FalkorDB regression vs the
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

- **T+15 min (22:11Z): FAIL on event volume.** Tetragon sent 93.7 MB to
  Loki in 15 min and 32.6 MB in the last 5 min, about 9.4 GB/day steady
  against the 1 GB/day gate (all of Loki was 478 MB/day before). Every other
  reading passed: agent CPU p95 0.018 cores, 160 MiB in the namespace,
  strix memory 23.9%, Postgres 0.85 ms per transaction (baseline 0.92),
  no restarts, no FalkorDB errors, no unredacted credentials.
  Top binaries in 10 min (exec + exit events): runc 3822,
  `/proc/self/fd/6` (runc re-exec) 1903, iptables 675, postgres 601,
  bash 523, pg_isready 243.
- **22:12Z fast stop:** strix unlabelled, agent pod gone within seconds,
  operator left running (it costs nothing on strix).
- Fix (next PR): drop PROCESS_EXIT from the export, deny runc, the runc
  re-exec, iptables/nft and pg_isready by binary, drop the embedded parent
  from exec events, and cap the export at 100 events/minute (0.78 GB/day even at the measured
  5.4 KB per event), and deny the runc re-exec only when runc is the parent
  (parent checked in Loki: runc for 1932 of 1938 `/proc/self/fd` execs; the rest
  were systemd re-executing itself, which stays exported). Ring 1 then
  restarts from the label step with the same checks.

- **Run 2.** #205 merged (export filters, 100 events/min cap) and Ready.
  22:21Z: strix relabelled, agent Ready, `tetra status` running.
- Redaction (run 2): `true --requirepass kubani-sentinel-3 postgres://u:kubani-sentinel-4@h`
  exported as `--requirepass ***** postgres://u:*****@h`; no
  `kubani-sentinel-` match in Loki. **PASS**
- **T+15 min (22:37Z): PASS.** Last 5 min: 508 events, 2.8 MB, about
  0.81 GB/day. The first minute was a burst from the startup process-tree
  dump (procFS events).
- **T+1 h (23:23Z): PASS.** Last 30 min: 3109 events (104/min), 17.2 MB,
  about 0.83 GB/day at ~5.5 KB per event. The cap is binding: about 226
  events (7%) dropped by the rate limit in those 30 min. What remains is
  mostly probe and lifecycle churn (authentik's `/lifecycle/ak` and
  python, `sh`/`bash`, `cat`, `mkdir`, `umount`, each 290-370 per 30 min).
  Because stage 2's kprobe events share the same 100/min budget, they can
  be dropped too; ring 2 reads the drop count alongside volume.

## Resource readings
| | Baseline | T+15 min | T+1 h |
|---|---|---|---|
| strix memory % | 22.1% (24 h max 23.2%) | 23.9% (run 1), 23.4% (run 2) | 24.2% max over the hour (run 2) |
| Tetragon agent CPU (p95, cores) | n/a | 0.018 (run 1), 0.011 (run 2) | 0.012 (run 2) |
| `tetragon` namespace memory | n/a | 160 MiB (run 1), 106 MiB (run 2) | 132 MiB (run 2) |
| Pod restarts (`tetragon`, `database`) | database 0 | 0 (run 1), 0 (run 2) | 0 (run 2) |
| Postgres active time per transaction (`pg_stat_database`; no `pg_stat_statements` exporter) | 0.92 ms (24 h), 0.85 ms (1 h) | 0.85 ms (run 1), 0.84 ms (run 2) | 0.85 ms (run 2) |
| FalkorDB TIMEOUT errors (24 h) | 0 (no log lines at all in 24 h) | 0 (run 1), 0 (run 2) | 0 (run 2) |
| Tetragon events into Loki (per day) | n/a (all of Loki: 478 MB/day) | **~9.4 GB/day (run 1, FAIL)**, ~0.81 GB/day (run 2) | ~0.83 GB/day, 7% dropped by the cap (run 2) |

## Decision
<kept / reverted, and why; ledger corrected from the T+24h reading: yes/no>
