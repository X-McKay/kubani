# Inference Platform Roadmap — 2026-09-29

**Status:** Phase 0 live on the cluster since 2026-10-01 (section 11); Phase 1.1 next
**Scope:** vLLM tuning, AI edge (agentgateway), Authentik integration, and the
cluster-wide items that make those observable and safe.
**Companions:** `docs/infrastructure/inference/release-process.md`,
`docs/troubleshooting/vllm-main-engine-hang-gb10.md`,
`docs/plans/active/2026-08-16-vllm-gpu-sleep-wake-broker.md`,
`docs/plans/ideas/2026-05-09-audit-followup.md`,
`docs/plans/ideas/2026-06-07-cluster-stability-and-maintenance.md`.

---

## 1. Goals

1. Faster, more stable inference on the GB10: target ~1.7x single-stream decode
   (MTP), lower long-prompt TTFT (FlashInfer GDN prefill), shorter restarts.
2. One authenticated AI endpoint with model routing, per-key token budgets,
   failover, and GenAI metrics, without giving up the gpu-broker's sleep/wake.
3. Authentik as the identity source for humans (OIDC) and agents (API keys
   issued through the gateway), including the MCP workstream.
4. Enough observability that the two failure modes seen on 2026-09-25 (engine
   stall behind a green `/health`, silent backup failure) page someone.

## 2. Non-goals

- Replacing Deployments with KServe `LLMInferenceService` (single GPU, single
  replica per model: the endpoint picker has nothing to pick from).
- KV cache offloading (LMCache): GPU and CPU share one 128 GB pool on Spark,
  the on-GPU prefix cache peaks at 1.6% use with a 72% hit rate, and hybrid
  GDN state has no known connector support.
- Level-2 sleep, driver 590.x, `--moe-backend b12x` (extra not in the image).

## 3. Invariants that shape every step

| Invariant | Consequence |
|---|---|
| `*.almckay.io` resolves via Cloudflare to Traefik's ServiceLB on the Tailscale IPs; reachability is tailnet-only | New hostnames are an `Ingress` with `ingressClassName: traefik` plus the cert-manager annotation. external-dns (Cloudflare, `policy: sync`) and cert-manager DNS-01 do the rest. Keep Traefik as the single TLS terminator. |
| In-cluster clients resolve `auth.almckay.io` to Traefik via the CoreDNS split-horizon override | Extend the rewrite to the wildcard (the commented line in `coredns-split-horizon.yaml`) once the gateway hostname exists, so in-cluster agents do not hairpin through Tailscale. |
| Default-deny ingress in every operational namespace | Every new path (Traefik -> gateway, gateway -> brokers, gateway -> MCP servers, Prometheus -> exporters) needs an explicit NetworkPolicy. |
| GitOps via Flux; SOPS for every Secret | Gateway config, API keys, and OIDC client secrets are `.enc.yaml`. |
| Serving changes go through the release process, one variable per stage | Gateway insertion is a hot-path change and is benchmarked like a flag change. |
| GPU memory on GB10 is host memory | vLLM pods carry a memory request equal to their real footprint. |

## 4. Baseline (measured 2026-09-29, main engine under real agent traffic)

| | |
|---|---|
| Image / model | `vllm/vllm-openai:v0.27.1-aarch64-cu129`, `nvidia/Qwen3.6-35B-A3B-NVFP4` |
| Kernels in use | Marlin W4A16 MoE (no native FP4), Triton/FLA GDN prefill, FlashInfer attention with fp8 KV, `FULL_AND_PIECEWISE` graphs |
| Traffic (30 min, 223 requests) | avg 4.3k prompt / 280 output tokens, 72% prefix hits, no queueing |
| TTFT p50 / p95 | ~0.35 s / ~0.75 s |
| ITL mean | 17 ms (~58 tok/s per stream); 0.3% of tokens above 100 ms |
| Aggregate decode, c=2 | ~100 tok/s |
| KV pool | 21 GiB provisioned, 1.6% peak use |
| Cold start | ~5.5 min: 142 s weights (CPU-bound repack), 48 s compile, 50 s warmup, ~45 s autotune + graph capture; nothing cached across restarts |
| Host | driver 580.95.05, DGX OS 7.3.1 (7.5.0 pending), boots to `graphical.target` |
| Public endpoint | `llm.almckay.io` has no authentication (tailnet-only mitigates) |

Findings that change the existing v0.30.0 release record:

- `v0.30.0-aarch64-cu129` cannot start: torch 2.14.0+cu130 with torchvision
  0.28.0+cu129; `vllm` dies on import (`torchvision::nms does not exist`).
  Use `v0.30.0-aarch64` (CUDA 13), which is also what unlocks FlashInfer GDN
  prefill on SM12x.
- `image_preflight.sh` reported every flag "NOT FOUND" because the CLI crashed;
  it must fail loudly on a non-zero `vllm serve --help`.
- The model card's Spark recipe now includes `--async-scheduling`,
  `--load-format fastsafetensors`, and MTP with a Triton draft backend. The
  Triton draft is the likely fix for the v0.17 MTP shape mismatch.

---

## 5. Phases

Dependencies run top to bottom; within a phase, stages are ordered.

### Phase 0 — Foundations (no serving-behaviour change)

| # | Change | Why | Verify |
|---|---|---|---|
| 0.1 | Revive `monitoring/` as it is (Prometheus, Alertmanager, Grafana, Loki), but replace Promtail with Grafana Alloy (Promtail reached end of life 2026-03); scrape vLLM `/metrics`, DCGM exporter, gpu-brokers, Flux, Longhorn, Traefik, node exporter; NetworkPolicies for the scrapes; import the community dashboards (vLLM official, DCGM exporter, Flux, Longhorn, Traefik, Node Exporter Full) as ConfigMaps | Every later change becomes measurable; alerts for the two silent failures; Alloy also carries OTel traces later (2.6) | Targets up; `vllm:*` and `DCGM_*` series present; Grafana at `grafana.almckay.io` behind Authentik SSO (existing OAuth secret) |
| 0.2 | Alerts: engine stall (`num_requests_running > 0` and generation throughput 0 for 2 min), backup CronJob failed, node NotReady, PVC > 85%, Flux not ready. Alertmanager routes to a self-hosted ntfy (`ntfy.almckay.io`, tailnet-only like everything else) for phone push | The 2026-09-25 stall and 2026-09-24 backup failure went unnoticed | Fire a synthetic alert; push arrives on the phone |
| 0.3 | Engine watchdog: probe sidecar running a 1-token completion with a deadline as the liveness probe, or alert-driven pod delete via broker admin API | `/health` stays 200 during the wedge | Simulate with a paused engine; pod is replaced |
| 0.4 | Memory requests/limits on `vllm`, `vllm-fast`, `vllm-embeddings` sized to real footprint (main ~45 GiB) | Scheduler is blind to unified memory today | `kubectl describe node sparky` shows the reservation |
| 0.5 | Fix `image_preflight.sh` (fail on CLI crash); refresh stale FP8-era comments in `model-config.yaml`; fast model `--tool-call-parser qwen3_xml` | Tooling and docs drift | `just drift` clean |
| 0.6 | Persist vLLM caches: PVC (local-path on sparky) at the cache root via `VLLM_CACHE_ROOT`; pin `--kv-cache-memory` to the logged value | Cuts ~1.5 min per restart; skips memory profiling | Second restart logs cache hits; init < 3 min |

### Phase 1 — vLLM tuning (release process, one variable per stage)

| Stage | Change | Expected | Risk / rollback |
|---|---|---|---|
| 1.0 | Baseline `main` and `fast` on v0.27.1 in a quiet window | Reference numbers (none exist) | none |
| 1.1 | Image `v0.30.0-aarch64` (cu130), fast first, then main | FlashInfer GDN prefill on SM12x (3.8-4.5x kernel, 5-7% TTFT on long prompts), post-0.28 Mamba state fixes, FlashInfer 0.6.18; soak is the stall gate | v0.27.1 cached on node |
| 1.2 | `--async-scheduling` | Few % ITL/throughput (model card) | flag revert |
| 1.3 | MTP: `--speculative-config '{"method":"mtp","num_speculative_tokens":3,"moe_backend":"triton"}'` | ~55 -> ~97 tok/s c=1, +28% at c=4, ~72% acceptance | Unmerged upstream fix for MTP + prefix caching on sm_121 (Xid 13); soak, and be ready to disable prefix caching |
| 1.4 | Scheduler: `--max-num-batched-tokens` 4096 vs 16384, `--long-prefill-token-threshold 8192` | Trade long-prompt TTFT vs the ITL tail | flag revert |
| 1.5 | `--load-format fastsafetensors` | Cold-start weight load only | flag revert |
| 1.6 | KV pool right-sizing: `--kv-cache-memory` ~8 GiB (~750k tokens) | Frees ~12 GiB for embeddings / fine-tuning at no measurable hit-rate cost | raise again |
| 1.7 | Host window: DGX OS 7.5.0 (driver 580.159.03), `multi-user.target`, optional `nvidia-smi -lgc 0,2200` | Stability, thermal headroom (~1% decode cost) | reboot; stay on 580 branch |

Stability backstops if the stall recurs at any stage, in order:
`--attention-backend TRITON_ATTN`; drop `--kv-cache-dtype fp8` (buys almost no
capacity on this hybrid); `VLLM_USE_FLASHINFER_SAMPLER=0`; `PIECEWISE` graphs;
`--enforce-eager` (~24% cost) last.

Benchmark client: `vllm bench serve --save-result` from the engine image,
run as the in-cluster Job, through the broker, with `compare.py` unchanged.
Keep `sleepwake` and `soak` in the custom harness. AIPerf only for
NVIDIA-comparable reports, never mixed into the same series.

### Phase 2 — AI edge: agentgateway

| # | Change | Notes |
|---|---|---|
| 2.0 | Routing decision (one page): Gateway API as the model for AI traffic; agentgateway owns its GatewayClass; Traefik keeps Ingress and TLS; identify what installed the existing Gateway API CRDs and align versions | Blocks the install; avoids three routers |
| 2.1 | Install via Flux `HelmRelease` (agentgateway ships a Flux guide) in an `ai-gateway` namespace; ClusterIP data plane; NetworkPolicies Traefik -> gateway, gateway -> `vllm` brokers | Standalone mode, no KServe |
| 2.2 | One `AgentgatewayModel` per engine with `baseURL` at the broker Services (`llm-api`, `fast-model-api`, embeddings); aliases and a virtual model; backend timeout + retry; failover main -> fast | Broker keeps sleep/wake; its multi-engine routing phase is shelved |
| 2.3 | Hostname: `ai.almckay.io` via Ingress -> gateway Service (inherits Cloudflare DNS + cert-manager); extend CoreDNS wildcard rewrite | Existing `llm*.almckay.io` stay until 2.5 |
| 2.4 | Release-process benchmark: gateway path vs broker path, same scenarios | Expect sub-ms overhead; gate on WARN |
| 2.5 | Cut over: point `llm.almckay.io`, `llm-fast`, `embeddings` Ingresses at the gateway; API-key policy on the public listener; OTel/Prometheus export into Phase 0 stack | Old Ingress backends are the rollback |
| 2.6 | Traces: add Grafana Tempo to `monitoring/` (storage on Longhorn or the NAS); agentgateway exports OTel spans (GenAI semantic attributes: model, tokens, latency) to Alloy -> Tempo; Grafana correlates traces with the vLLM metrics and engine logs | Request-level view without touching the agent runtime |

### Phase 3 — Authentik integration

| # | Change | Notes |
|---|---|---|
| 3.1 | Authentik OIDC provider for the gateway (humans: JWT auth on the listener, groups -> CEL authorization) | Authentik is a supported provider in agentgateway's MCP auth guides |
| 3.2 | Agent identities: gateway virtual keys with per-key token budgets and cost tracking; keys as SOPS Secrets; one key per agent/workstream | Replaces the audit's "vLLM `--api-key`" item |
| 3.3 | Keep Authentik proxy-provider middlewares for non-AI UIs (Qdrant, FalkorDB, Grafana) | No change |

### Phase 4 — MCP through the gateway (when the MCP workstream has servers)

Static/virtual MCP backends, per-tool authorization, Authentik OAuth, MCP rate
limits; NetworkPolicies gateway -> MCP namespaces; `mcp.almckay.io`.

### Phase 5 — Platform hygiene (promoted from the May audit)

| # | Item |
|---|---|
| 5.1 | Registry `registry-data` off local-path onto Longhorn; keep `model-storage` on local-path (weights re-downloadable, NAS copy) |
| 5.2 | PostgreSQL -> CloudNativePG (retires Bitnami chart and homegrown backup CronJob; adds PITR); Redis and external-dns off Bitnami |
| 5.3 | Renovate in PR-only mode; preflight every image and chart before it reaches a manifest |
| 5.4 | ServiceLB `loadBalancerSourceRanges: 100.64.0.0/10` on the Traefik Service if Klipper honours it; Tailscale ACL audit |
| 5.5 | PSA restricted cleanup for `vllm` and `database`; scope of the agent runtime's kubeconfig |
| 5.6 | Backup restore drill on a schedule, alert on failure (0.2) |

### Phase 6 — Resilience (after the June plan's network substrate work)

Second control plane / etcd quorum; PodDisruptionBudgets and anti-affinity for
stateful singletons; roll long-lived controllers to reset restart counters.

### Deferred, with triggers

| Item | Trigger |
|---|---|
| KServe `LLMInferenceService` + agentgateway inference extension | Second GPU node or a multi-replica model; EPP prefix-aware routing becomes real |
| KV offloading (LMCache) | Dense model with connector support and a measured cold-prefix TTFT problem |
| Re-enable level-1 sleep on the main broker | Soak clean for 2 weeks on the Phase 1 config; KV cap under the ~40 GB wake burst |
| `--moe-backend flashinfer_b12x` | Upstream Xid 31 fix merged; measured ~4% slower than Marlin on Spark today |
| VictoriaMetrics in place of Prometheus (drop-in, lower RAM, cheap long retention) | Prometheus retention or memory pressure on strix-sized nodes |
| Prompt-level LLM tracing (Langfuse or Arize Phoenix, self-hosted) | The agent runtime workstream exports OTel/OpenInference spans; until then agentgateway traces in Tempo are the request-level view |

---

## 6. Sequencing

```
Phase 0 (0.1-0.6) ──> Phase 1 (1.0 -> 1.7) ──> Phase 2 (2.0 -> 2.5) ──> Phase 3 ──> Phase 4
                 └──> Phase 5 (independent, one PR each)
                                                  Phase 6 after the June network plan
```

Phase 0 first because it makes Phases 1 and 2 measurable and alertable.
Phase 1 before Phase 2 so the gateway's overhead is measured against a settled
baseline. Phase 5 runs alongside as single PRs.

## 7. Risks

- GB10 stall reproduces under a new stage: soak gate catches it; backstops listed.
- agentgateway API churn (`AgentgatewayBackend` -> `AgentgatewayModel` between minors): pin the chart, upgrade only through Renovate PRs with a preflight.
- Two Gateway API implementations reconciling the same resources: settled by 2.0.
- Docker Hub pulls from sparky are flaky (today's cu130 pull failed on an existing tag): pre-pull with `just inference-preflight` before every rollout.
- Authentik upgrade is blocked upstream (see audit); Phase 3 uses the current version's OIDC, which is sufficient.

## 8. Open decisions for the operator

1. Observability: the plan assumes the full existing stack (Prometheus, Alertmanager, Grafana, Loki) plus Alloy, ntfy and later Tempo. Confirm, and pick metrics/log retention.
2. Alert delivery channel.
3. Hostname for the gateway (`ai.almckay.io` proposed) and whether `llm*.almckay.io` survive as aliases.
4. Trust model for the LAN and tailnet ACLs (audit question 1 and 2), which decides how much Phase 5.4 matters.
5. Bitnami: migrate on a plan or opportunistically.

---

## 9. Progressive rollout, validation, and rollback

### 9.1 Rules that apply to every stage

1. **One PR, one variable, one ring.** A stage is a single Flux-applied commit
   whose message records the prior value. Nothing is applied imperatively
   except pod deletion for recovery and the transient bench/preflight pods.
2. **Rings.** Ring 0 = preflight (no cluster impact). Ring 1 = canary (fast
   model, shadow hostname, scrape-only). Ring 2 = production (main model,
   hostname cutover, alerts live). A stage moves to the next ring only after
   its gate passes and its soak window elapses.
3. **Gates are numbers, not impressions.** Every gate below names the metric,
   the threshold, and where it is read. "Pod is Ready" and "`/health` is 200"
   are never gates.
4. **Rollback is a revert.** `git revert <stage sha>` then
   `flux reconcile kustomization apps --with-source`. Flux owns the spec, so
   never `kubectl rollout restart` or hand-edit a live object (Flux reverts it
   within 10 min, which is how the 2026-09-25 outage doubled). Rollback is
   verified the same way the rollout was: a real completion, then the gate.
5. **Everything new gets requests and limits**, lands on the platform node
   (rig0) unless it must run per-node, and is added to the capacity ledger in
   9.2 before the PR merges.
6. **Stop the line** on: any Xid in `journalctl -k` on sparky, a soak stall,
   a FAIL verdict, node memory above 80% on any node, or an alert that was
   not expected. The stage is reverted first and diagnosed second.

### 9.2 Capacity ledger

Allocatable and observed use on 2026-09-29 (`kubectl top nodes`):

| Node | Role | CPU alloc | Mem alloc | Mem used | Headroom policy |
|---|---|---|---|---|---|
| asio | control plane, etcd | 8 | 15 GiB | 47% | keep below 65%; no new app workloads |
| rig0 | platform node | 27.5 | 50 GiB | 51% | target for all new services; ceiling 75% |
| sparky | GPU, tainted | 15.5 | 110 GiB (unified with GPU) | 28% + 45 GiB GPU-resident | only vLLM, Alloy, DCGM; ceiling 80% incl. GPU |
| strix | small worker | 7 | 13 GiB | 18% | overflow only; ceiling 70% |

Planned additions (requests / limits, placement). Figures are starting
values to be corrected from observed use after one week.

| Service | Phase | CPU req/lim | Mem req/lim | Node | Storage |
|---|---|---|---|---|---|
| Prometheus server | 0.1 | 250m / 1 | 1.5 GiB / 3 GiB | rig0 | 10 GiB local-path (existing), 15 d retention |
| Alertmanager | 0.1 | 50m / 200m | 64 MiB / 256 MiB | rig0 | 2 GiB nas-smb (existing) |
| kube-state-metrics | 0.1 | 50m / 200m | 128 MiB / 256 MiB | rig0 | none |
| Grafana | 0.1 | 100m / 500m | 256 MiB / 512 MiB | rig0 | 5 GiB local-path (existing) |
| Loki (single binary) | 0.1 | 200m / 1 | 512 MiB / 1 GiB | rig0 | 20 GiB Longhorn, 7 d retention |
| Alloy (DaemonSet) | 0.1 | 100m / 500m | 128 MiB / 384 MiB | every node | none |
| ntfy | 0.2 | 20m / 100m | 32 MiB / 128 MiB | rig0 | 1 GiB Longhorn |
| Probe sidecar (vLLM watchdog) | 0.3 | 20m / 100m | 32 MiB / 64 MiB | sparky | none |
| vLLM main (request added) | 0.4 | 2 / — | 48 GiB / 56 GiB | sparky | existing |
| vLLM fast (request added) | 0.4 | 500m / — | 6 GiB / 8 GiB | sparky | existing |
| agentgateway control plane | 2.1 | 100m / 500m | 128 MiB / 512 MiB | rig0 | none |
| agentgateway data plane | 2.1 | 100m / 1 | 128 MiB / 512 MiB | rig0 | none |
| Tempo (monolithic) | 2.6 | 200m / 1 | 512 MiB / 1 GiB | rig0 | 20 GiB Longhorn, 3 d retention |

Sum of new requests on rig0: about 3.5 GiB memory and 1.2 CPU, taking rig0
from 51% to roughly 58%. Within the 75% ceiling with room for Tempo and
CloudNativePG later. Nothing new lands on strix or asio.

Sizing controls that keep these numbers honest:

- Prometheus scrape interval 30 s; vLLM histograms are per model and per
  engine, so cardinality stays small; drop `go_*` and `process_*` from
  exporters that do not matter.
- Loki: JSON parsing at query time, not ingest; drop the vLLM per-request
  access log lines (`POST /v1/chat/completions 200 OK`) at Alloy, keep the
  10 s `loggers.py` stats line and everything at WARNING or above.
- Tempo: head sampling 100% on the gateway while traffic is a few requests
  per second; revisit at 10 rps.

### 9.3 Watching resource consumption during rollout

Phase 0.1 has a bootstrap problem: the monitoring stack cannot watch itself
land. For that one stage use a manual checklist; every later stage uses the
Grafana panels.

| Signal | Where | Threshold that stops a stage |
|---|---|---|
| Node memory % (working set) | `kubectl top nodes`; node exporter panel | any node above its ceiling in 9.2 |
| Node memory on sparky incl. GPU | `free -g` on the node, `DCGM_FI_DEV_FB_USED`, vLLM "Free memory on device" log line | available below 15 GiB |
| Pod restarts | kube-state-metrics `kube_pod_container_status_restarts_total` | any restart of a new service in the soak window |
| OOMKilled | `kube_pod_container_status_last_terminated_reason` | any |
| CPU throttling | `container_cpu_cfs_throttled_periods_total` | above 25% of periods for a hot-path pod (gateway, broker) |
| PVC fill | `kubelet_volume_stats_used_bytes` | above 70% |
| Prometheus own TSDB | `prometheus_tsdb_head_series` | growth above 20% after a stage that added no targets |
| GPU | `DCGM_FI_DEV_GPU_UTIL`, power, `DCGM_FI_DEV_XID_ERRORS` | any Xid |
| Flux | `gotk_reconcile_condition` | not Ready for more than one interval |

Cadence: read the panel at T+15 min, T+2 h, T+24 h for every stage; the
24 h reading is what corrects the ledger.

### 9.4 Validation and rollback per phase

**Phase 0 (monitoring, alerts, watchdog, requests, caches)**

| Stage | Ring 1 canary | Gate | Soak | Rollback | Rollback check |
|---|---|---|---|---|---|
| 0.1 | Scrape-only: Prometheus and Alloy up, no alert rules, Grafana behind SSO | All targets `up == 1`; rig0 memory below 60%; Loki ingests the vLLM stats line | 48 h | revert; PVCs kept (data survives) | targets gone, rig0 memory back |
| 0.2 | Rules with `severity: test` routed to ntfy only | Synthetic alert reaches the phone in under 2 min; no unexpected alert in 24 h | 48 h | revert the rules ConfigMap | no alerts fire |
| 0.3 | Sidecar on `vllm-fast` first, exec-only (no liveness wiring) | 7 days without a false positive; then wire as liveness on fast; then on main | 7 d per ring | revert; pod recreates with old probe | `/health` liveness restored |
| 0.4 | Requests on `vllm-fast` first | Pod schedules; `kubectl describe node sparky` reflects the reservation; no eviction | 24 h | revert | reservation gone |
| 0.5 | Preflight script fix run against v0.27.1 and v0.30.0 images | v0.27.1 flags "accepted", v0.30.0 cu129 "CLI failed" | none | revert | n/a |
| 0.6 | Cache PVC on `vllm-fast` | Second restart shows compile-cache hit; fast init under 60 s; then main: init under 3 min | 48 h | revert; delete PVC | init time back to baseline |

**Phase 1 (vLLM tuning)** follows `release-process.md` exactly:

| Stage | Ring 1 | Gate | Soak | Rollback |
|---|---|---|---|---|
| 1.0 baseline | — | `perf.no_errors`, `soak.no_stalls` on the current config; promoted | — | — |
| 1.1 image | fast model on cu130 for 48 h | `fast` PASS/WARN with reason; then main: PASS on `perf`, `soak.no_stalls` at c=4 for 30 min, no Xid | 72 h real traffic before 1.2 | revert; v0.27.1 image is cached on sparky; delete the pod, never rollout-restart |
| 1.2 async | main only (fast is eager, proves nothing) | PASS; ITL p95 at c=4 not worse than 10% | 48 h | revert flag |
| 1.3 MTP | main only | c=1 decode at least 1.4x baseline; acceptance rate above 60% (`vllm:spec_decode_*`); soak clean; no Xid | 7 d (upstream fault is load-dependent) | revert flag; if Xid, also test with prefix caching off before giving up |
| 1.4 scheduler | main only | TTFT p95 on 8k/32k and ITL p95 at c=4 both within thresholds; pick the value that wins on the live traffic mix, not the synthetic one | 48 h | revert flag |
| 1.5 fastsafetensors | fast then main | weight-load time from the engine log; no gate on serving metrics | 24 h | revert flag |
| 1.6 KV cap | main | prefix hit rate from `/metrics` within 5 points of baseline over 24 h | 72 h | raise value |
| 1.7 host | fast model first after reboot, then main | boot to Ready; drivers load; `nvidia-smi` clocks; full `perf` PASS | 7 d | DGX OS rollback is a reimage, so before the window confirm every local-path PVC on sparky is re-creatable (model weights have a NAS copy, the cache PVC is disposable) and keep the `age.key` and kubeconfig off the node |

**Phase 2 (agentgateway)**

| Stage | Ring 1 | Gate | Soak | Rollback |
|---|---|---|---|---|
| 2.1 install | Gateway with no routes | control plane Ready; rig0 memory within ledger; Gateway API CRDs unchanged in version (Traefik unaffected: all existing Ingresses still serve) | 48 h | revert HelmRelease; Flux `remediation.retries: 3`, `rollback` on failed upgrade |
| 2.2-2.3 shadow hostname | `ai.almckay.io` live, nothing points at it | real completion through the gateway to each engine; failover test by scaling `gpu-broker-main` to 0 for one minute | 7 d with the benchmark harness and one agent pointed at it | revert; DNS record removed by external-dns (`policy: sync`) |
| 2.4 benchmark | — | `perf` through the gateway vs through the broker: WARN at most, with the overhead written down | — | — |
| 2.5 cutover | Ingress backend swap for `llm-fast` first, then `llm`, then `embeddings`; API keys issued to each client before the swap | zero 401s from known clients in 24 h; TTFT p95 within 10% of 2.4; gateway CPU throttling below threshold | 72 h per hostname | revert the Ingress commit; Traefik IP does not change, so no DNS propagation is involved and rollback is immediate |
| 2.6 traces | Tempo up, gateway exporting | spans visible for a known request; Tempo PVC growth matches the 3 d retention estimate | 7 d | revert; Tempo PVC deleted |

**Phase 3 (Authentik)**

| Stage | Ring 1 | Gate | Rollback |
|---|---|---|---|
| 3.1 OIDC | JWT policy on `ai.almckay.io` only, API keys still valid | human login via Authentik works; agent keys unaffected | revert policy |
| 3.2 keys | one agent moved to a virtual key with a budget | token accounting matches vLLM `prompt_tokens_total` delta within 2%; budget exhaustion returns 429 in a test | revert key policy |

**Phase 5 and 6** are one PR each with the same shape: canary on the least
critical instance, a 48 h soak, revert as rollback. Data-bearing migrations
(registry to Longhorn, CloudNativePG) add a restore rehearsal before the
cutover and keep the old volume until the soak passes.

### 9.5 Performance optimisation loop during rollout

Optimisation is continuous, not a phase. The loop runs after every stage:

1. **Measure**: the stage's benchmark plus 24 h of live histograms (TTFT,
   ITL, e2e, prefix hit rate, KV use, GPU power and clocks, gateway
   latency).
2. **Attribute**: compare with the previous stage; if the change is within
   run-to-run noise (a few percent), say so and move on.
3. **Tune only what the numbers point at**:

| Observation | Knob |
|---|---|
| ITL tail grows at c=2 to 4 | lower `--max-num-batched-tokens`, set `--long-prefill-token-threshold` |
| TTFT on 8k+ prompts grows | raise batched tokens; check prefix hit rate; check for JIT warnings in the log |
| Prefix hit rate drops after MTP | `--prefix-cache-retention-interval` at the block size |
| GPU power flat at ~40 W with low tok/s | memory-bound decode; only MTP or a lighter model moves it |
| GPU clocks pinned low or "SW Power Capping" rising | thermal; the 1.7 clock cap or airflow |
| Gateway p99 above 5 ms | check CPU throttling; raise data plane limits |
| Prometheus RAM climbing | scrape interval, drop rules, retention |
| rig0 memory above 65% | move Tempo retention down before adding anything else |

4. **Record** in the change record; promote the baseline only on PASS.

### 9.6 Order and timeline

Soak windows dominate: about 4 weeks for Phase 0, 5 to 6 weeks for Phase 1
(the MTP soak is the long pole), 3 weeks for Phase 2, 1 week for Phase 3.
Phase 5 PRs interleave wherever a soak window is idle, never on the same day
as a Phase 1 or 2 stage so that attribution stays clean.

---

## 10. Process, tooling, and guidance updates

The rollout above only works if the repo's own guidance says the same thing
the runbooks learned the hard way. These are the concrete edits, grouped by
where they live, with the phase that needs them.

### 10.1 Claude rules and skills (`.claude/`)

| Item | Change | Why | Needed by |
|---|---|---|---|
| `rules/kubernetes.md` | `kubectl rollout restart` moves from "usually safe" to "never on Flux-managed Deployments; delete the pod". Add the stall signature and the recovery command from the GB10 runbook. Add `kubectl top` reading against the capacity ledger as a safe operation | The rule contradicts the troubleshooting doc that documents a doubled outage | Phase 0 |
| `hooks/pre-bash.sh` | The `kubectl apply/delete` guard checks for namespaces `production`/`prod`, which do not exist. Replace with the real operational namespaces (`vllm`, `database`, `auth`, `ai-gateway`, `monitoring`, `flux-system`) while allowing `kubectl delete pod -n vllm` (the documented recovery) and the transient bench/preflight pods. Block `kubectl rollout restart` everywhere | Guard is currently a no-op | Phase 0 |
| `rules/gitops.md` | Add: every workload declares requests/limits, a PSA-restricted `securityContext`, a NetworkPolicy pair, a topology `nodeSelector`, and a capacity-ledger line. Add the image tag rule: verify arch and CUDA variant, preflight before merge (today's cu129 lesson) | Manifest standards exist but stop at requests/limits and netpol | Phase 0 |
| `rules/auth.md` (new) | The auth decision table from 10.5 as a rule so new services pick the right model automatically; never a key in a ConfigMap or manifest; rotation steps | Gateway keys and OIDC clients arrive in Phase 2-3 | Phase 2 |
| `skills/inference-release` | Add: cu130 vs cu129 tag guidance; "preflight must fail on CLI crash"; `vllm bench serve` as the perf client; the capacity ledger check before a stage; the gateway path (bench through the gateway once it fronts the engines, and through the broker for engine-only stages); the 9.4 gate table as the decision reference | Skill predates the findings in section 4 | Phase 1 |
| `skills/host-maintenance` (new) | DGX OS / driver / kernel window on sparky: pre-checks (PVC re-creatability, image cache, `age.key` off node), cordon, reboot, verify (`nvidia-smi`, fast then main engine, `perf` drift run), rollback = reimage note | Stage 1.7, and every future driver update | Phase 1 |
| `skills/gateway-onboard` (new) | Add a model or MCP backend to agentgateway, issue a virtual key into SOPS, attach budget and authorization policy, validate with a curl through `ai.almckay.io`, record in the auth inventory | Repeated every time an agent or server is added | Phase 2 |
| `skills/authentik-app` (new) | Wraps `authentik-app-access.md`: choose OIDC vs forwardAuth vs gateway key, write the blueprint, create the provider, validation curls, entry in the auth inventory | The pattern doc exists; the procedure is manual | Phase 3 |
| `skills/incident-capture` (new) | One command that captures the forensics bundle before a restart: `nvidia-smi -q`, engine and broker log tails, `journalctl -k` Xid lines, `/metrics` snapshot, running request count; writes to `~/kubani-forensics/<date>/` and drafts a troubleshooting record from the template in 10.6 | The 2026-09-25 record notes no stack was captured | Phase 0 |
| `commands/troubleshoot.md` | Add a GPU / inference section: the wedge table from the runbook, the watchdog alert, DCGM Xid counter, and the capture skill | Six categories today, none for the GPU | Phase 0 |
| `commands/cluster-status.md` | Add the capacity ledger comparison and the alert summary from Alertmanager | Status today is node/pod/Flux only | Phase 0 |

### 10.2 `justfile` recipes

| Recipe | Does |
|---|---|
| `inference-restart <engine>` | `kubectl delete pod` for the engine, `rollout status`, then one real completion through the broker. Replaces the hand-typed sequence in the runbook |
| `incident-capture <engine>` | Runs the capture skill non-interactively |
| `capacity` | `kubectl top nodes` and per-namespace requests vs the ledger in `docs/infrastructure/cluster/capacity.md`; non-zero if any node is above its ceiling |
| `node-maintenance <host> {pre,post}` | Cordon and pre-checks; uncordon, verify, drift bench |
| `gateway-key <name>` | Generates a key, encrypts it with SOPS into the gateway's secret, prints the kustomize line to add |
| `alerts` | Active alerts and silences from Alertmanager |
| `new-service <name> <namespace>` | Scaffolds the service skeleton from 10.3 |
| `inference-bench main drift-$(date +%Y%m)` | Added to the scheduled audit workflow monthly, never promoted |

### 10.3 Deployment standards

`docs/infrastructure/gitops/guides/deploying-services.md` shows a Deployment,
Service, kustomization and Ingress. It does not show a NetworkPolicy, a
PSA-restricted `securityContext`, topology labels, tolerations, a
PodDisruptionBudget, the reloader annotation, or Prometheus scrape
configuration, which is why new services keep arriving without them.

Replace the prose with a **service skeleton** under
`infrastructure/gitops/_templates/service/` (kustomize component or a
scaffold copied by `just new-service`):

- `deployment.yaml`: requests and limits, restricted `securityContext`,
  `topology.kubani.io/*` nodeSelector, startup/liveness/readiness probes
  that prove service, `reloader.stakater.com/auto`, image pinned by digest
  or CI sha tag.
- `netpol.yaml`: default-deny is namespace-level already; the skeleton
  carries the allow-from-Traefik and allow-DNS pair plus a placeholder for
  each cross-namespace path.
- `servicemonitor.yaml` (or pod annotations if the Prometheus chart is kept):
  scrape on by default with the `go_*`/`process_*` drop rules.
- `ingress.yaml`: Traefik class, cert-manager annotation, and a comment that
  external-dns publishes it to Cloudflare on the Tailscale IP.
- `pdb.yaml` for anything that must survive a node drain.
- `auth.md` stub: which row of the auth decision table this service uses.

Every existing workload in `apps/` and `infrastructure/` is measured against
the skeleton by `just drift` (advisory), and the eight Deployments currently
missing requests are fixed as Phase 0.4 and Phase 5 PRs.

### 10.4 Release process

`docs/infrastructure/inference/release-process.md` is inference-specific.
Generalise it into a **platform release process** with the inference process
as one profile:

- Applies to every hot-path or data-bearing change: vLLM, gpu-broker,
  agentgateway, Traefik, Authentik, PostgreSQL, Longhorn, and host driver or
  OS changes on any node.
- Keeps the shape: change record, preflight, baseline, ring 1 canary, gate,
  soak, decision, rollback. Adds the capacity ledger check and the 9.3
  resource readings as mandatory fields in the change record template.
- Inference-specific additions: image tag guidance (arm64, cu130 for GB10;
  preflight must fail on CLI crash); `vllm bench serve` as the perf client
  pinned to the engine image; a bench profile per path (engine via broker,
  and via gateway once fronted); host changes trigger a drift run.
- Gateway-specific profile: shadow hostname, failover test, cutover per
  hostname, 401 count as a gate.
- A `releases/` directory per profile, with the change record template
  requiring the rollback commit SHA before the stage is applied.

### 10.5 Auth and Authentik guidance

Extend `docs/infrastructure/configuration/authentik-app-access.md` from the
current three-row rule to a decision table that covers the AI edge:

| Client | Surface | Mechanism | Where configured |
|---|---|---|---|
| Human in a browser | Admin UI (Grafana, Qdrant, FalkorDB, Temporal) | Authentik: native OIDC if supported, else Traefik forwardAuth via blueprint | Authentik blueprints in `apps/authentik/` |
| Human in a browser | AI gateway UI/API | Authentik OIDC, JWT policy on the gateway listener, groups to CEL authorization | `AgentgatewayPolicy` |
| Agent / service | LLM API (`ai.almckay.io`, `llm*.almckay.io`) | Gateway virtual key with token budget; one key per agent or workstream; SOPS-stored | gateway policy + `.enc.yaml` |
| Agent / service | MCP servers | Gateway OAuth with Authentik as provider; per-tool authorization | `AgentgatewayPolicy`, Authentik provider blueprint |
| Service to service inside the cluster | Any | NetworkPolicy plus the service's native auth; never the human SSO | netpol + app config |
| TCP protocols (Postgres, Redis, FalkorDB) | Databases | Private network and native credentials; tailnet ACL is the outer layer | SOPS secrets, Tailscale ACL |

Add to the doc:

- **Auth inventory**: one table listing every hostname, the row it uses, the
  Authentik application or gateway key name, and the rotation date. Checked
  by `just drift` against live Ingresses and gateway policies.
- **Rotation runbook** for gateway keys and OIDC client secrets, following the
  secrets rule's step 6 (restart the consumer; env from `secretKeyRef` does
  not hot-reload).
- **Grafana**: use the existing `oauth-secret.enc.yaml` with an Authentik
  OIDC provider managed by blueprint; no local admin login exposed.
- **Tailnet ACL**: written down as the outer layer, with the audit's open
  question answered (which devices reach which ports).
- **Authentik version pin**: the upstream migration blocker stays documented;
  Phase 3 uses the pinned version's OIDC, which is sufficient.

### 10.6 Operations standardisation

| Item | Change |
|---|---|
| Runbook index | `docs/infrastructure/README.md` gains an operations index: restart procedure per workload (vLLM delete pod; Flux reconcile; Longhorn attach), node reboot procedure, backup restore drill, host maintenance, alert-to-runbook map |
| Alert annotations | Every Alertmanager rule carries `runbook_url` pointing at the matching doc; ntfy shows it |
| Incident record template | The GB10 runbook's structure (one-line answer, how to recognise, incident record, why the cluster did not heal, follow-ups) becomes `docs/troubleshooting/_template.md`; the capture skill drafts from it |
| Capacity ledger as a doc | `docs/infrastructure/cluster/capacity.md` is the source of truth for 9.2; `just capacity` compares it with reality; changes to it are part of the PR that adds a workload |
| Maintenance calendar | `docs/infrastructure/operations/maintenance-calendar.md`: monthly drift bench, quarterly restore drill, DGX OS on the 580 branch when 7.x ships, Longhorn stepwise minors, Authentik when unblocked, Renovate PRs weekly |
| Scheduled audit | Add the drift bench and `just capacity` to the existing GitHub runner workflow; a red run posts to ntfy |
| Renovate | PR-only, grouped by chart; preflight job runs on vLLM image PRs |
| Node maintenance | `just node-maintenance` plus a doc that names what runs on each node and what happens when it is drained (sparky: 5 min engine restart, fast first) |
| Post-incident follow-ups | The follow-up checklist in each troubleshooting doc is mirrored as GitHub issues so they stop being lost in prose |

---

## 11. Implementation status (2026-09-30)

Implemented on branch `claude/vllm-performance-optimization-74ce1e`; nothing
reaches the cluster until it merges to `main`. Validated with `just
validate-local` (kustomize build, secrets scan, unit tests, hooks), `just
drift-offline` (clean), `helm template` of every monitoring HelmRelease, and
the pre-bash hook test suite.

| Stage | State | Notes |
|---|---|---|
| 0.1 monitoring | manifests ready | Prometheus/Alertmanager/kube-state-metrics/Grafana pinned to 1 replica with Flux drift detection, on rig0; Alloy replaces Promtail; Loki 20 GiB Longhorn, 7 d; scrape and egress NetworkPolicies added in monitoring, vllm, database, cache, temporal, auth. No importable Alloy dashboard exists (mixin only); gpu-broker has no `/metrics` (broker workstream). |
| 0.2 alerts | manifests ready | Rules with `runbook_url`; ntfy + alertmanager-ntfy bridge; `Watchdog` proves the push path on topic `kubani-watchdog`, everything else on `kubani-alerts`. Operator: subscribe the phone app. |
| 0.3 watchdog | ring 1 ready | Exec-only sidecar on `vllm-fast`; `WATCHDOG_MODE=probe` is the ring 2 liveness form. |
| 0.4 requests | ready | main 2 CPU, 48/56 GiB; fast 12/16 GiB (ledger said 6/8: the 0.1 pool alone is ~12 GiB). cgroups see only the ~9 GiB CPU side, so limits cannot OOM-kill a healthy engine. |
| 0.5 tooling | done and verified | Preflight fails loudly on CLI crash and rejects flag prefixes (`--kv-cache-memory` would have passed as `--kv-cache-memory-bytes`). Comments and the fast tool parser fixed. |
| 0.6 caches | ready | Per-engine local-path cache PVCs at `VLLM_CACHE_ROOT`; main pinned with `--kv-cache-memory-bytes 22473494016`. Both verified against the running v0.27.1 image. |
| 1.0 baseline | **measured** | main `20260930T2202Z_baseline-v0.27.1.json` promoted: c1 decode 74.7 tok/s, TTFT p50 149 ms; 8k prefill TTFT 1.31 s, 32k 6.14 s, prefix-hit 8k 0.44 s; c4 aggregate 173 tok/s, ITL p95 28 ms; soak 900 s at c=4: 308 ok, 0 errors, 0 stalls. Fast baseline: see `benchmarks/fast/`. |
| 1.1 image | **preflight passed** | `v0.30.0-aarch64` cached on sparky; every current flag accepted, plus `--async-scheduling`, MTP, `--gdn-prefill-backend flashinfer`. Preflight pods need a GPU slice since v0.30.0. |
| 1.2-1.7 | not started | Each is one flag commit through the release process after 1.1 soaks. 1.5 changes to `--load-format instanttensor`: `fastsafetensors` no longer exists in v0.30.0. |
| 2.0 decision | written, unblocked | `docs/infrastructure/configuration/ai-gateway.md` and the decisions record. The suspected Gateway API gap is not one: agentgateway 1.5.x supports Gateway API 1.4-1.6, the cluster has v1.4.0, no CRD change needed. |
| 2.1-2.3, 2.6 | staged and verified, not wired | Every field checked against the pulled `v1.5.0` charts and CRD schemas and `helm template`; Flux sources wired; enabling 2.1 is adding `- ai-gateway/` to `apps/kustomization.yaml`. A Prometheus job for the gateway is already in the scrape config. |
| 3, 4 | not started | Rule and skills exist (`rules/auth.md`, `gateway-onboard`, `authentik-app`). |
| 5.3 Renovate | config ready | `renovate.json` PR-only; needs the Renovate app enabled on the repo. |
| 10.x | done | Rules, hook (20 tests), skills, `just` operations recipes, service skeleton, platform release process, auth table and inventory, ops index, incident template, capacity ledger, maintenance calendar, node maintenance doc, monthly drift bench in the audit workflow. |

Found while validating, fixed in the same branch: the bench runner could not
pass extra arguments (jq `--args`), new pods are refused for ~2 s until
kube-router programs their policy chains (bench now waits), the result JSON
was discarded when a stderr line landed inside it, the Prometheus scrape
egress selected same-namespace pods instead of all namespaces, the
pushgateway values key never reached the subchart, and `alerts` cannot exec
python inside the Alertmanager image (now reads through the API proxy).

Rollout order stays as section 6 and 9.4: merge 0.5 first (tooling only),
then 0.1 and watch rig0 memory against the ledger for 48 h, then 0.2, 0.4
(fast then main), 0.6 (fast then main), 0.3, then Phase 1.

### Rollout outcome (2026-10-01)

Merged to `main` and reconciled by Flux: PR #154 (the branch), then #157,
#158, #159, #160, #161 for what the rollout exposed. Everything in Phase 0
is live; both engines restarted once and serve.

| Gate | Result |
|---|---|
| 0.1 targets up | vLLM (2), DCGM, Flux controllers, Longhorn, Loki, Alloy, Authentik, Postgres, Redis, Temporal, Traefik (pod scrape), node exporters on sparky/strix/rig0, kube-state-metrics with Flux resource state (35 resources). Still down: the host node exporter on asio (not listening on 9100) and Qdrant `/metrics` (needs the API key; job removed until it is wired from SOPS). |
| 0.1 logs | Pod logs and the scoped journal (k3s, tailscaled, containerd, kernel ring) in Loki; engine probe and scrape access lines dropped at Alloy. |
| 0.2 push path | `Watchdog` delivered to `ntfy.almckay.io/kubani-watchdog` with the runbook link; `just alerts` works through the Grafana pod. |
| 0.4 | Requests visible on sparky; main 48 GiB, fast 12 GiB. |
| 0.6 | Compile cache written under the PVC (`/cache/vllm`); KV pool pinned at 1.99M tokens; first init 155 s, the next restart should hit the cache. |
| Capacity | rig0 62% after the stack (ledger said 58%; Prometheus needs 6 GiB, not 3). |

What broke on the way and how it was fixed, for the next person:

- Main engine refused to start without `--gpu-memory-utilization`: the
  0.92 default check fails with the fast engine resident. Both flags stay.
- Prometheus was OOM-killed at 3 GiB replaying its WAL; limit back to 6 GiB.
- Alertmanager's nas-smb claim no longer mounts and a StatefulSet cannot
  change its volume templates; it now runs ephemeral under a new release
  name.
- Flux 2.x controllers do not export `gotk_resource_info`; it comes from
  kube-state-metrics custom-resource state.
- Loki's active-stream cap was exhausted by one journal stream per unit per
  node; the journal is scoped and the cap raised.
- The alertmanager-ntfy bridge renders per alert (`labels`, `annotations`),
  not per group, and needs the reloader annotation.
- The API-server service proxy is rejected by default-deny ingress; in-
  namespace checks go through the Grafana pod.
- The pre-bash guard misread `helm template -f` next to `origin/main` as a
  force push; it now inspects only the `git push` segment.

Open after Phase 0: the asio host node exporter, Qdrant metrics auth,
`prometheus.almckay.io` has no auth (forwardAuth follow-up in the auth
inventory), the 7-day watchdog observation before ring 2, and the
sparky resolver timeouts that slow Docker Hub pulls.
