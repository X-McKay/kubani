# Kubani GPU Sleep/Wake Broker and Training Arbitration Specification

**Status:** Adopted (full spec, with normative amendments) — Phase 0 in progress
**Target environment:** Kubani / K3s / Flux / NVIDIA DGX Spark (GB10) / vLLM
**Primary use case:** Automatically sleep idle vLLM engines, transparently wake them for inference, and safely lend the DGX Spark GPU to fine-tuning or evaluation jobs.

---

> **Imported 2026-08-16** from an externally authored spec, after assessment.
> The body below is preserved as written except one inline correction in
> §21 (training-Job toleration). Read these import notes first — they record
> where the spec has drifted from the cluster and what must be added before
> implementation.
>
> **Corrections to the spec's baseline:**
>
> 1. **Taint model (supersedes §21 and any `gpu-workloads` reference):**
>    sparky's taint is now `nvidia.com/gpu=true:NoSchedule` (2026-08-16
>    control-plane migration). Every pod targeting sparky — vLLM engines,
>    training Jobs, the qualification suite — must tolerate that key/effect.
>    The vLLM deployments themselves were fixed in this same branch.
> 2. **Prometheus is currently scaled to 0** (as is the whole monitoring
>    stack, ~8 months). §23's metrics/dashboards are a dependency to
>    re-enable, not an existing capability.
> 3. **Embeddings and fast model have their own hostnames/Services**, so
>    §24's "no raw engine is publicly routable" only holds per-engine as each
>    is migrated behind the broker (Phase A covers `llm.almckay.io` only).
>
> **Additions required before implementation:**
>
> 4. **Probe semantics while sleeping:** the current vLLM liveness/readiness
>    probes assume an always-awake engine. If readiness fails during sleep,
>    the `llm-engine` Service loses its endpoint and the broker cannot reach
>    `/wake_up`. Phase 0 must verify `/health` behavior under sleep and
>    retune probes accordingly.
> 5. **Admin-port auth is mandatory, not optional:** the §24.4 SOPS-managed
>    bearer token on `:8081` is required; NetworkPolicy alone is not enough
>    for "sleep the production LLM / grant a GPU lease".
> 6. **Traefik/client timeout alignment:** the wake path (up to 180s
>    queueing) and unbounded streaming must fit inside Traefik's response
>    timeouts; audit those alongside Phase 1.
> 7. **Broker image hosting:** use ghcr.io as the spec sketches;
>    registry.almckay.io has a known in-cluster TLS mismatch.
> 8. **Broker restarts drop in-flight streams** (single replica on the hot
>    path); acceptable, but deploys should be scheduled accordingly.
>
> **Scope decision (open):** the lease/arbitration track (Phases 1, 2, 4
> with `training_reclaim_mode: restart`) solves the actual pain — no more
> manual scale-up/down around fine-tuning — without qualifying sleep mode
> on GB10 at all. Idle auto-sleep (Phases 0, 3, 5) is a separable
> efficiency layer carrying all the open GB10 wake-crash risk. Decide
> arbitration-first vs full spec before creating the broker repo.

> **Research findings (2026-08-16, four-agent web research):**
>
> - **v0.20.0 cannot do this at all.** Qwen3.6-35B-A3B is a hybrid
>   GDN-MoE; with `--kv-cache-dtype fp8`, `/wake_up` crashes the engine
>   on every version before **v0.27.0** (vllm#39078 / #41564, fixed by
>   PR #41602 in v0.27.0 with a 200-cycle hybrid validation). Upgrading
>   to **>= v0.27.1** is a hard prerequisite for any sleep-mode work.
> - **GB10 wake-burst crash (vllm#50011, OPEN):** wake dies natively when
>   the discarded region re-mapped in one burst exceeds ~37-56 GiB.
>   Measured on a 35B MoE on Spark: KV capped at ~40 GB -> sleep ~9.5 s,
>   wake ~5.7 s, reliable; at 0.85 util -> crash. Mitigation: cap
>   `--kv-cache-memory` ~= 40e9 so the burst stays under threshold.
> - **Level 2 is off the table for this FP8 checkpoint**: calibrated FP8
>   KV scales silently reset to 1.0 on wake (fix unmerged, vllm#45617),
>   quantized `reload_weights` is broken with no fix planned
>   (vllm#28606), and SSM-page poisoning on hybrids is not fully fixed
>   (vllm#45542 unmerged). `training_reclaim_mode: level2` (Phase 5)
>   should be dropped indefinitely, not merely deferred.
> - **On GB10 unified memory, level-1 sleep frees ~78-80 GiB** (KV +
>   graphs; the ~23 GiB weight backup stays in the same LPDDR pool).
>   Enough for LoRA-class fine-tuning of the 35B; full fine-tuning needs
>   engine stop (`restart` reclaim). Make reclaim mode a per-lease
>   parameter. `drop_caches` before training jobs (page cache is not
>   reclaimed reliably by CUDA allocation pressure on GB10).
> - **`/health` stays 200 after a native EngineCore death** (vllm#50011)
>   - the broker must use an active probe (tiny completion or
>   `/is_sleeping` + engine check), never the health endpoint alone.
> - **Requests sent to a sleeping engine hang forever** (vllm#45326
>   open) - the broker's traffic gating is mandatory for correctness,
>   not just UX.
> - **vLLM upstream does not consider sleep/wake production-ready**: RFC
>   #48311 (July 2026) counts 9 P0 + 4 P1 open blockers; RFC #48310
>   requires logprob-equivalence oracles across cycles - add that to the
>   S15.1 qualification suite (compare fixed-prompt logprobs against a
>   fresh engine, not just deterministic text).
> - **Build-vs-buy confirmed: build.** Production Stack still errors on
>   sleeping engines (no wake-on-request; issue #391 by design), llm-d
>   sleep support is an open feature request, Dynamo cannot scale to
>   zero, KubeAI/KServe wake = pod cold start (minutes). No project
>   anywhere offers GPU-lease arbitration. Worth reading before
>   building: SailorJoe6/vllm-sleeper-proxy (DGX Spark, level-2 wake
>   sequence incl. cache resets) and Batchputz/LLMeister (DGX Spark,
>   memory-admission LRU); llama-swap as the battle-tested
>   process-swap fallback pattern.
> - **Net risk picture:** with v0.27.1 + level-1-only + ~40 GB KV cap +
>   active probing + gated traffic, the worst credible auto-sleep
>   failure is a wake crash that the broker recovers by engine restart
>   (~4-6 min degraded, warm cache) - an availability blip, not data
>   loss. The full spec is viable under those amendments.

> **Normative amendments (2026-08-16, adopted with the full-spec decision;
> these supersede the imported body wherever they conflict):**
>
> 1. **Phase 0 prerequisite — vLLM upgrade:** main and fast-model images
>    move to `vllm/vllm-openai:v0.27.1-aarch64-cu129` (the release line
>    has no cu130 builds after v0.20; cu129 userspace is compatible with
>    sparky's CUDA 13.0 driver). Applied in kubani while `replicas: 0`;
>    first unpause doubles as the upgrade validation. The embeddings
>    engine stays on its NVIDIA NGC image until Phase 6 brings it under
>    the broker.
> 2. **S13.2 / Phase 5 deleted:** `training_reclaim_mode: level2` and the
>    `reload_weights` path are permanently out of scope for FP8
>    checkpoints (vllm#45617 unmerged, vllm#28606 not planned,
>    vllm#45542 unmerged) - not merely deferred.
> 3. **S10.1 amended:** reclaim mode is a per-lease parameter
>    (`reclaim: sleep | restart`), not global config. `sleep` grants
>    ~80 GiB (LoRA-class jobs); `restart` stops the engine and grants the
>    full pool (heavy jobs, ~4-6 min service restoration).
> 4. **S17 / S34 amended:** when sleep is enabled, the main engine must
>    cap KV (`--kv-cache-memory` ~= 40e9) so the wake remap burst stays
>    inside the GB10 envelope (vllm#50011: ~40 GB wakes in ~5.7 s;
>    larger bursts crash natively).
> 5. **S22.2 amended:** engine liveness uses an active probe (tiny
>    completion or engine-state check). vLLM `/health` returns 200 after
>    a native EngineCore death and must never be the sole signal.
> 6. **S8 hardened:** broker traffic gating is a correctness requirement
>    - requests reaching a sleeping engine hang forever (vllm#45326).
> 7. **S15.1 strengthened:** the qualification suite compares
>    fixed-prompt logprobs against a fresh engine across cycles (vLLM
>    RFC #48310's oracle), not just deterministic text output.


## 1. Executive Summary

Kubani should add a small, always-on, CPU-only **GPU Broker / Inference Gateway** in front of vLLM.

The broker becomes the only externally reachable OpenAI-compatible inference endpoint. It:

1. Proxies `/v1/*` requests to the appropriate vLLM engine.
2. Tracks active and streaming requests.
3. Puts idle vLLM engines into sleep mode after a configurable timeout.
4. Transparently wakes a sleeping engine before forwarding the next inference request.
5. Serializes concurrent wake attempts so a request burst produces exactly one wake.
6. Exposes an internal **exclusive GPU lease** API for training/evaluation workflows.
7. Prevents inference from waking while a training job owns the GPU.
8. Drains inference and sleeps managed engines before granting a training lease.
9. Leaves inference sleeping when training finishes; the next inference request wakes it.
10. Emits Prometheus metrics and structured state-transition logs.

Kubani already has the right infrastructure primitives:

- Flux-managed vLLM deployments.
- K3s.
- NVIDIA GPU Operator.
- GPU time-slicing.
- DCGM metrics.
- Temporal.
- Traefik.
- NetworkPolicies.
- SOPS-managed secrets.

The broker's **runtime source code should not live in the Kubani repository**. Kubani's current repository boundary explicitly makes it an infrastructure/GitOps repository and moves first-party runtime code into separate workstreams. Kubani should only deploy a versioned broker image and own its Kubernetes configuration.

A recommended split is:

```text
X-McKay/kubani
  └── infrastructure/gitops/apps/vllm/
      ├── vLLM engine manifests
      ├── broker Deployment/Service/ConfigMap/RBAC
      ├── NetworkPolicies
      └── monitoring configuration

X-McKay/kubani-gpu-broker        # new runtime repo
  └── sleep-aware OpenAI proxy + GPU lease controller

X-McKay/<training-runtime>       # existing/new experiment runtime
  └── Temporal workflows + training job launcher
```

The system should be introduced in phases, with automated sleep disabled until sleep/wake has been qualified on the exact DGX Spark + vLLM + Qwen configuration.

---

# 2. Current Kubani Baseline

The current Kubani repository is intentionally infrastructure-only. Its README and repository-scope documentation define the repository as owning:

- host provisioning,
- K3s,
- Flux GitOps,
- cluster services,
- operational documentation,

while first-party runtime and application source are expected to be built and released elsewhere.

Current vLLM deployment characteristics relevant to this design:

- Main vLLM is deployed under `infrastructure/gitops/apps/vllm/`.
- Main engine currently uses:
  - `vllm/vllm-openai:v0.20.0-aarch64-cu130`
  - DGX Spark / GB10
  - Qwen3.6-35B-A3B-FP8
  - FP8 KV cache
  - FlashInfer
  - prefix caching
- Main model memory budget is configured at 55% of the Spark GPU-visible memory pool.
- Fast model is budgeted at 15%.
- Embeddings are budgeted at 10%.
- Combined inference budget is documented at 80%.
- The main, fast, and embeddings deployments currently have `replicas: 0`.
- GPU time-slicing advertises four logical `nvidia.com/gpu` resources from the single physical GPU.
- vLLM workloads target the `topology.kubani.io/usage-class: inference` node, which is currently `sparky`.
- Temporal is already installed as a Flux-managed cluster application.
- Traefik currently sends `llm.almckay.io` directly to the `llm-api` Service, which directly selects the main vLLM pod.
- The `vllm` namespace has default-deny ingress and egress policies plus explicit allowances.

This proposal preserves those choices but changes the request path so raw vLLM development endpoints are never publicly exposed.

---

# 3. Why a Broker Is Still Needed

vLLM supports Sleep Mode directly.

For online serving, current vLLM requires:

```bash
VLLM_SERVER_DEV_MODE=1
vllm serve ... --enable-sleep-mode
```

It exposes:

```text
POST /sleep?level=1
POST /sleep?level=2
POST /wake_up
GET  /is_sleeping
POST /collective_rpc
```

Level 1:

- discards KV cache,
- backs model weights in host memory,
- releases most CUDA/GPU allocations,
- is intended for returning to the same model quickly.

Level 2:

- discards weights and KV cache,
- frees more memory,
- is intended for model replacement or weight update workflows,
- requires a weight restoration/reload sequence before full inference resumes.

vLLM's Production Stack also has sleep-aware routing, but its current behavior is to avoid routing to a sleeping engine. A normal inference request to a sleeping engine is not itself an automatic wake operation; the documented example returns an error until `/wake_up` is called.

Therefore neither base vLLM nor the current Production Stack directly implements the desired policy:

```text
idle for N minutes
    ↓
automatically sleep
    ↓
new inference request arrives
    ↓
single-flight automatic wake
    ↓
forward original request
```

The broker supplies that missing policy layer.

---

# 4. Design Principles

## 4.1 Keep the hot path simple

The gateway should be a small reverse proxy, not another model-serving framework.

It should not:

- tokenize requests,
- inspect prompts unless required for routing,
- maintain conversation state,
- rewrite model outputs,
- perform inference,
- depend on Temporal for request-time behavior.

## 4.2 Separate request-time orchestration from long-running orchestration

Use:

- **GPU Broker** for millisecond-to-second request-time decisions.
- **Temporal** for minute-to-hour training/evaluation workflows.

Inference should continue to function even if Temporal is unavailable.

## 4.3 Treat the physical Spark GPU as a leased resource

Kubernetes GPU time-slicing shares a physical GPU but does **not** provide memory isolation or physical exclusivity.

Sleeping vLLM also does **not** return the pod's `nvidia.com/gpu` resource request to the scheduler.

Therefore:

> Kubernetes schedules the participants; the GPU Broker arbitrates physical ownership.

## 4.4 Fail closed for GPU ownership

If the broker is uncertain whether a training workload owns the GPU, it must **not wake inference**.

A false "GPU free" decision can produce OOMs, corrupted jobs, or model crashes. A false "GPU busy" decision merely delays inference.

## 4.5 State must be reconstructable

The broker should not require a database for correctness.

After restart it can reconstruct state from:

- vLLM `/is_sleeping`,
- Kubernetes Job/Pod state,
- a Kubernetes Lease,
- configuration.

Prometheus is for telemetry, not authoritative state.

---

# 5. Recommended Architecture

```text
                              ┌─────────────────────────┐
                              │ OpenAI-compatible client│
                              └────────────┬────────────┘
                                           │
                                      HTTPS /v1/*
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │     Traefik      │
                                  └────────┬─────────┘
                                           │
                                           ▼
                         ┌────────────────────────────────┐
                         │ Kubani GPU Broker / API Gateway│
                         │                                │
                         │ - OpenAI reverse proxy         │
                         │ - idle timer                   │
                         │ - request accounting           │
                         │ - sleep/wake state machine     │
                         │ - single-flight wake           │
                         │ - exclusive GPU lease          │
                         │ - Prometheus metrics           │
                         └───────────────┬────────────────┘
                                         │ internal only
                                         ▼
                               ┌────────────────────┐
                               │ vLLM Engine Service│
                               │  :8000             │
                               └──────────┬─────────┘
                                          │
                                          ▼
                               ┌────────────────────┐
                               │ vLLM on DGX Spark  │
                               │                    │
                               │ /v1/*              │
                               │ /sleep             │
                               │ /wake_up           │
                               │ /is_sleeping       │
                               └────────────────────┘


        ┌───────────────────┐
        │ Temporal Workflow │
        │ / Worker          │
        └─────────┬─────────┘
                  │
           acquire GPU lease
                  │
                  ▼
        ┌─────────────────────┐
        │ GPU Broker admin API│
        └─────────┬───────────┘
                  │
          drain + sleep engines
                  │
             lease granted
                  │
                  ▼
        ┌─────────────────────┐
        │ Kubernetes Training │
        │ Job on sparky       │
        └─────────┬───────────┘
                  │
            job completes
                  │
                  ▼
             release lease
```

---

# 6. Public and Internal Network Topology

## 6.1 Current topology

Currently:

```text
Traefik
   ↓
llm-api Service
   ↓
vLLM pod
```

That topology cannot safely expose sleep mode because enabling `VLLM_SERVER_DEV_MODE=1` enables development endpoints that vLLM explicitly says should not be exposed to users.

## 6.2 Proposed topology

Change to:

```text
Traefik
   ↓
llm-api Service
   ↓
gpu-broker
   ↓
llm-engine Service
   ↓
vLLM pod
```

Preserve the external service name `llm-api` to minimize migration impact.

Create a new internal service:

```text
llm-engine.vllm.svc.cluster.local:8000
```

Only the broker should need to call:

```text
/sleep
/wake_up
/is_sleeping
/collective_rpc
```

No Ingress should point to `llm-engine`.

---

# 7. State Model

Use two related state machines:

1. **Physical GPU ownership**
2. **Per-engine lifecycle**

## 7.1 GPU ownership states

```text
AVAILABLE
    │
    │ exclusive lease requested
    ▼
DRAINING
    │
    │ inference drained + engines sleeping
    ▼
TRAINING
    │
    │ lease released / workload finished
    ▼
AVAILABLE
```

Failure state:

```text
RECOVERING
```

Definitions:

### AVAILABLE

No exclusive batch/training lease exists.

Inference requests may wake engines.

### DRAINING

An exclusive workload has requested the GPU.

Behavior:

- stop accepting new inference work for the managed GPU,
- allow existing requests/streams to finish,
- sleep all required engines,
- verify sleeping state,
- only then grant the lease.

### TRAINING

An exclusive lease exists.

Behavior:

- never wake managed inference engines,
- inference receives a controlled temporary-unavailable response,
- Temporal may run GPU Jobs.

### RECOVERING

State is inconsistent or a sleep/wake transition failed.

Behavior:

- fail closed,
- do not launch a new exclusive job,
- do not wake inference until ownership is re-established.

---

## 7.2 Engine states

```text
UNKNOWN
AWAKE
SLEEPING_L1
SLEEPING_L2
WAKING
SLEEPING
ERROR
```

Typical inference cycle:

```text
AWAKE
  │
  │ idle timeout
  ▼
SLEEPING
  │
  ▼
SLEEPING_L1
  │
  │ next request
  ▼
WAKING
  │
  ▼
AWAKE
```

---

# 8. Request Path

## 8.1 Normal awake request

```text
request arrives
   ↓
GPU owner == AVAILABLE?
   ↓ yes
engine == AWAKE?
   ↓ yes
increment in_flight
   ↓
proxy request
   ↓
stream/full response completes
   ↓
decrement in_flight
   ↓
record last_activity
```

## 8.2 Request to sleeping engine

```text
request arrives
   ↓
GPU owner == AVAILABLE?
   ↓
engine sleeping?
   ↓ yes
acquire per-engine wake lock
   ↓
re-check state
   ↓
POST /wake_up
   ↓
poll /is_sleeping until false
   ↓
verify engine health
   ↓
mark AWAKE
   ↓
release wake lock
   ↓
proxy original request
```

All requests that arrive while one wake is in progress wait on the same single-flight operation.

Do **not** issue multiple `/wake_up` calls.

## 8.3 Request while training owns GPU

Default behavior:

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 30
Content-Type: application/json
```

Example body:

```json
{
  "error": {
    "type": "gpu_temporarily_unavailable",
    "message": "The inference GPU is temporarily allocated to an exclusive workload."
  }
}
```

Do not hold an HTTP inference request open for a potentially multi-hour fine-tuning run.

A short bounded wait is reasonable while state is `WAKING`; it is not reasonable while state is `TRAINING`.

---

# 9. Idle Sleep Policy

Recommended initial configuration:

```yaml
idle_timeout_seconds: 600
min_awake_seconds: 120
idle_check_interval_seconds: 10
idle_sleep_level: 1
wake_timeout_seconds: 120
```

## 9.1 What counts as activity

Count:

- chat completions,
- completions,
- embeddings if routed through the same broker,
- other inference endpoints.

Do not count:

- `/healthz`,
- `/readyz`,
- `/metrics`,
- broker admin calls,
- vLLM health probes.

## 9.2 Streaming requests

A streaming request remains in-flight until:

- the upstream stream completes,
- the client disconnects,
- the proxy cancels the upstream request.

Do not reset the idle clock merely because the first token was emitted.

## 9.3 Sleep eligibility

An engine may sleep only when:

```text
GPU owner == AVAILABLE
AND
engine == AWAKE
AND
in_flight == 0
AND
now - last_activity >= idle_timeout
AND
now - last_wake >= min_awake_duration
```

The broker tracks its own in-flight count, so it does not need to rely on a vLLM pause mode to drain normal idle traffic.

---

# 10. Exclusive GPU Lease

Training/evaluation workloads should never directly decide to sleep or wake inference.

They must acquire an exclusive lease from the broker.

## 10.1 API

Internal-only API:

```http
POST /internal/v1/gpu/leases
```

Request:

```json
{
  "owner": "fine-tune",
  "workload_id": "temporal-workflow-id",
  "sleep_policy": "training",
  "drain_timeout_seconds": 300
}
```

Response:

```json
{
  "lease_id": "01J...",
  "state": "granted",
  "holder": "fine-tune:temporal-workflow-id",
  "expires_at": "..."
}
```

Renew:

```http
POST /internal/v1/gpu/leases/{lease_id}/renew
```

Release:

```http
DELETE /internal/v1/gpu/leases/{lease_id}
```

Inspect:

```http
GET /internal/v1/gpu/state
```

## 10.2 Lease acquisition

```text
Temporal requests lease
     ↓
AVAILABLE?
     ├── no  → conflict / wait/retry
     └── yes
          ↓
       DRAINING
          ↓
block new inference
          ↓
wait for in_flight == 0
          ↓
sleep managed engines
          ↓
verify all required engines sleeping
          ↓
persist Lease holder
          ↓
TRAINING
          ↓
return lease token
```

A training Job must **not** be created before the lease is granted.

## 10.3 Lease release

```text
training Job completes
    ↓
Temporal releases lease
    ↓
broker verifies no GPU job remains for lease
    ↓
clear lease
    ↓
AVAILABLE
```

Recommended behavior:

> Do not automatically wake vLLM after training.

Leave it asleep. The next real inference request triggers wake-up. This avoids consuming GPU memory when no inference is waiting.

---

# 11. Kubernetes Lease

Use a native:

```yaml
apiVersion: coordination.k8s.io/v1
kind: Lease
metadata:
  name: sparky-gpu
  namespace: vllm
```

Purpose:

- survive broker process restart,
- prevent duplicate exclusive ownership,
- give operators a Kubernetes-visible ownership record,
- provide a future path to multiple broker instances.

Example holder identities:

```text
inference
train:workflow-abc123
eval:workflow-def456
```

The broker remains the only component allowed to change the lease.

Recommended heartbeat:

```yaml
leaseDurationSeconds: 180
renewEverySeconds: 60
```

A missing heartbeat **must not immediately wake inference**. Before recovering an expired lease, the broker should query Kubernetes for Pods/Jobs labeled with that lease ID.

Fail closed:

```text
Lease expired
   ↓
matching GPU Job still active?
   ├── yes → remain TRAINING
   └── no  → release/recover
```

---

# 12. Kubernetes GPU Time-Slicing Implication

Kubani currently advertises four logical GPU resources from the Spark's one physical GPU.

Important:

> vLLM sleep releases GPU memory but does not relinquish the pod's Kubernetes `nvidia.com/gpu` allocation.

Therefore the scheduler cannot infer physical availability from vLLM sleep state.

Recommended Kubani policy:

```text
4 logical GPU scheduling slots
├── persistent main vLLM pod
├── persistent fast-model pod
├── persistent embeddings pod
└── reserved batch/training slot
```

Even while inference pods are sleeping, they retain their logical slots. The fourth logical slot allows a training Job to schedule.

The **exclusive lease**, not time-slicing, guarantees that the other three workloads are inactive.

Add a validation rule/runbook check so long-lived GPU deployments never consume all four logical slots.

Do not increase time-slice replicas simply to solve coordination. More virtual slots increase accidental oversubscription risk.

---

# 13. DGX Spark Sleep Levels

The Spark's unified-memory architecture makes the distinction between sleep levels especially important.

## 13.1 Idle inference: Level 1

Recommended for ordinary idle periods:

```text
sleep(level=1)
```

Benefits:

- discards KV cache,
- vLLM releases CUDA allocations,
- preserves a host-side backing copy of model weights,
- fastest path back to the same model.

Use for:

```text
inference → 10 minutes idle → sleep → later inference
```

## 13.2 Training: configurable Level 1 vs Level 2

On a discrete-GPU system, moving weights to CPU RAM frees VRAM while retaining weights elsewhere.

On DGX Spark, CPU and GPU share physical LPDDR memory. A host-side backup therefore still consumes the same physical memory pool.

For large fine-tuning jobs, retaining a ~model-sized host backup can materially reduce available physical memory.

The broker should support:

```yaml
training_reclaim_mode: level1 | level2 | restart
```

### `level1`

Use when:

- the training workload fits with the host-backed inference weights still resident,
- fast inference restoration is more important than maximum memory reclamation.

### `level2`

Use when:

- maximum memory is needed,
- the wake/reload path has been fully qualified.

Level 2 discards model weights. Returning to inference requires a controlled restoration sequence, such as:

```text
wake weights allocation
    ↓
reload weights
    ↓
wake KV cache
```

vLLM exposes `collective_rpc("reload_weights")` for this class of workflow.

### `restart`

Safest fallback:

- fully terminate/restart the vLLM engine after exclusive training,
- slower than Sleep Mode,
- operationally simple,
- useful until GB10 sleep/wake is qualified.

Recommended initial policy:

```yaml
idle_reclaim_mode: level1
training_reclaim_mode: restart
```

Then graduate training to Level 2 only after hardware qualification.

---

# 14. Critical DGX Spark Qualification Gate

As of August 2026, upstream vLLM has open DGX Spark / GB10 sleep-mode issues, including wake failures.

One open report from July 27, 2026 documents:

- successful Level 1 sleep,
- reclaimed CUDA allocations,
- another CUDA process successfully using the GPU while vLLM slept,
- a native EngineCore crash on `/wake_up`.

Another earlier DGX Spark issue contains a wake failure in an FP8 KV-cache path.

The current Kubani main model uses:

```text
vLLM v0.20.0 aarch64 CUDA 13
Qwen3.6-35B-A3B-FP8
--kv-cache-dtype fp8
--attention-backend flashinfer
```

Therefore **automated sleep must be a feature flag**, not immediately enabled.

Start with:

```yaml
auto_sleep_enabled: false
```

Then qualify the exact deployed combination.

---

# 15. Qualification Test Plan

## 15.1 Level 1 cycle test

Run at least 100 cycles:

```text
deterministic inference
    ↓
record output
    ↓
sleep level 1
    ↓
verify /is_sleeping == true
    ↓
run independent CUDA allocation/compute
    ↓
wake
    ↓
verify /is_sleeping == false
    ↓
deterministic inference
    ↓
compare output / health
```

Track:

- sleep success rate,
- wake success rate,
- sleep latency,
- wake latency,
- memory before sleep,
- memory during sleep,
- memory after wake,
- process restart count,
- EngineCore deaths,
- inference correctness.

Acceptance:

```text
100/100 sleep/wake cycles succeed
0 EngineCore deaths
0 unexpected pod restarts
0 incorrect deterministic outputs
```

## 15.2 Concurrency test

Put model to sleep, then send:

```text
50 simultaneous inference requests
```

Assert:

- exactly one wake operation,
- all requests either succeed or receive a deterministic gateway timeout,
- no duplicate wake calls,
- no CUDA OOM.

## 15.3 Streaming test

Start a long streaming completion.

Allow the configured idle timeout to elapse.

Assert:

```text
engine remains awake while stream is active
```

Sleep may begin only after stream termination/disconnect.

## 15.4 Training coexistence test

```text
sleep inference
    ↓
launch a representative PyTorch fine-tuning-like allocation
    ↓
run forward/backward step
    ↓
complete job
    ↓
wake inference
```

Validate memory headroom and correctness.

## 15.5 Failure injection

Test:

- broker restart while engine awake,
- broker restart while engine asleep,
- broker restart during `WAKING`,
- vLLM process death,
- wake timeout,
- Temporal worker death,
- Temporal workflow retry,
- training Job failure,
- lease expiry with active Job,
- lease expiry with no Job,
- client disconnect during streaming.

---

# 16. Broker API

## 16.1 Public API

The public surface is the OpenAI-compatible proxy:

```text
/v1/*
```

No additional public control API is required.

## 16.2 Operational endpoints

```text
GET /healthz
GET /readyz
GET /metrics
```

## 16.3 Internal admin API

```text
GET    /internal/v1/state
GET    /internal/v1/engines
POST   /internal/v1/engines/{engine}/sleep
POST   /internal/v1/engines/{engine}/wake
POST   /internal/v1/gpu/leases
POST   /internal/v1/gpu/leases/{id}/renew
DELETE /internal/v1/gpu/leases/{id}
```

Manual sleep/wake endpoints are operational escape hatches and should not be exposed through Ingress.

---

# 17. Broker Configuration

Example:

```yaml
server:
  listen: 0.0.0.0:8080

gpu:
  lease_name: sparky-gpu
  lease_namespace: vllm
  lease_duration_seconds: 180
  lease_renew_seconds: 60

engines:
  main:
    base_url: http://llm-engine.vllm.svc.cluster.local:8000
    public_models:
      - Qwen3.6-35B-A3B-FP8
    sleep_enabled: true
    idle_timeout_seconds: 600
    idle_sleep_level: 1
    wake_timeout_seconds: 120

policies:
  auto_sleep_enabled: false
  min_awake_seconds: 120
  training_reclaim_mode: restart
  drain_timeout_seconds: 300
  inference_during_training: reject

proxy:
  connect_timeout_seconds: 10
  request_timeout_seconds: 0
  wake_queue_timeout_seconds: 180
```

`request_timeout_seconds: 0` means the broker must support arbitrarily long streaming requests and should use separate connect/read policies rather than a short global HTTP timeout.

---

# 18. Broker Implementation

Recommended v1 stack:

```text
Python 3.12+
FastAPI / Starlette
httpx.AsyncClient
Pydantic Settings
prometheus-client
kubernetes-asyncio
uv
pytest
pytest-asyncio
respx or fake upstream server
```

Python is sufficient because the broker is mostly asynchronous network I/O and state coordination.

A later Rust/Axum rewrite is possible if proxy throughput becomes material, but is unnecessary for the initial Spark deployment.

Suggested source tree:

```text
kubani-gpu-broker/
├── pyproject.toml
├── Dockerfile
├── src/
│   └── kubani_gpu_broker/
│       ├── app.py
│       ├── config.py
│       ├── api/
│       │   ├── openai.py
│       │   ├── admin.py
│       │   └── health.py
│       ├── broker/
│       │   ├── state.py
│       │   ├── idle.py
│       │   ├── lease.py
│       │   └── recovery.py
│       ├── engines/
│       │   ├── base.py
│       │   └── vllm.py
│       ├── proxy/
│       │   └── streaming.py
│       ├── kubernetes/
│       │   ├── leases.py
│       │   └── workloads.py
│       └── telemetry/
│           ├── metrics.py
│           └── logging.py
└── tests/
    ├── unit/
    ├── integration/
    └── fake_vllm/
```

---

# 19. Core Synchronization Logic

Use one lock per engine for wake/sleep transitions plus a global GPU ownership lock.

Conceptual logic:

```python
async def ensure_awake(engine):
    if gpu_owner != AVAILABLE:
        raise GPUUnavailable()

    if engine.state == AWAKE:
        return

    async with engine.transition_lock:
        # Double-check after acquiring the lock.
        await engine.refresh_state()

        if engine.state == AWAKE:
            return

        if gpu_owner != AVAILABLE:
            raise GPUUnavailable()

        engine.state = WAKING

        try:
            await engine.wake()
            await engine.wait_until_awake()
            engine.state = AWAKE
        except Exception:
            engine.state = ERROR
            raise
```

Request accounting:

```python
async def proxy_request(request):
    await ensure_awake(engine)

    async with engine.inflight():
        return await stream_to_vllm(request)
```

Idle monitor:

```python
async def idle_loop():
    while True:
        await sleep(check_interval)

        if not auto_sleep_enabled:
            continue

        if gpu_owner != AVAILABLE:
            continue

        for engine in engines:
            if engine.should_idle_sleep():
                await sleep_engine_if_still_idle(engine)
```

The actual implementation must re-check all predicates while holding the transition lock.

---

# 20. Temporal Integration

Temporal should orchestrate the durable training lifecycle.

The broker should **not** launch fine-tuning jobs itself.

Recommended workflow:

```text
FineTuneWorkflow
  1. validate experiment
  2. acquire_gpu_lease
  3. create Kubernetes Job
  4. monitor Job
  5. collect artifacts
  6. run evaluation
  7. register accepted model / adapter
  8. release_gpu_lease in finally
```

Pseudo-code:

```python
@workflow.defn
class FineTuneWorkflow:
    @workflow.run
    async def run(self, spec):
        lease = await workflow.execute_activity(
            acquire_gpu_lease,
            spec,
            start_to_close_timeout=timedelta(minutes=10),
        )

        try:
            job = await workflow.execute_activity(
                create_training_job,
                {"spec": spec, "lease_id": lease.id},
                start_to_close_timeout=timedelta(minutes=2),
            )

            result = await workflow.execute_activity(
                wait_for_training_job,
                job,
                start_to_close_timeout=timedelta(hours=12),
                heartbeat_timeout=timedelta(minutes=2),
            )

            return result

        finally:
            await workflow.execute_activity(
                release_gpu_lease,
                lease.id,
                start_to_close_timeout=timedelta(minutes=2),
            )
```

Use the Temporal workflow ID as the idempotency key when acquiring the lease.

Every training Job receives labels:

```yaml
metadata:
  labels:
    kubani.ai/gpu-lease-id: "<lease-id>"
    kubani.ai/workflow-id: "<workflow-id>"
    kubani.ai/workload-type: "fine-tune"
```

This lets the broker recover ownership state after crashes.

---

# 21. Training Job Scheduling

A training Job should target Spark:

```yaml
spec:
  template:
    spec:
      runtimeClassName: nvidia
      nodeSelector:
        topology.kubani.io/usage-class: inference
      tolerations:
        # Corrected on import: sparky's taint is nvidia.com/gpu=true:NoSchedule
        # since the 2026-08-16 control-plane migration.
        - key: nvidia.com/gpu
          operator: Equal
          value: "true"
          effect: NoSchedule
      containers:
        - name: trainer
          resources:
            limits:
              nvidia.com/gpu: "1"
```

Because the GPU is time-sliced, that `1` is a logical scheduling token, not a physically isolated GPU.

The training worker must obtain a lease before creating this Job.

---

# 22. Recovery Semantics

## 22.1 Broker starts

On startup:

1. Read the `sparky-gpu` Lease.
2. Query active Kubernetes Jobs carrying `kubani.ai/gpu-lease-id`.
3. Query each managed vLLM `/is_sleeping`.
4. Reconstruct state.
5. Only then mark `/readyz` healthy.

## 22.2 Wake fails

If `/wake_up` fails:

```text
WAKING → ERROR
```

Then:

- stop forwarding requests,
- increment a recovery metric,
- return 503,
- rely on configured recovery strategy.

Recovery strategies:

```yaml
wake_failure_strategy: manual | restart
```

Recommended initial behavior on Spark:

```yaml
wake_failure_strategy: restart
```

The safest implementation is for Kubernetes/vLLM health supervision to replace a bad engine. If broker-triggered pod restart is added, its RBAC should be narrowly scoped and should be a later feature.

## 22.3 Training Job disappears

If lease exists but:

```text
no matching Job
AND lease heartbeat expired
```

the broker may recover to `AVAILABLE`.

If a matching GPU Job is still running, remain `TRAINING` regardless of stale heartbeat.

## 22.4 Broker loses Kubernetes API

Fail closed for exclusive ownership transitions.

Existing awake inference may continue, but:

- do not grant training leases,
- do not reclaim an uncertain expired lease,
- do not wake if an exclusive lease may still exist.

---

# 23. Observability

Kubani already has DCGM/Prometheus GPU observability. Add broker-specific metrics.

Recommended metrics:

```text
kubani_gpu_broker_state
kubani_gpu_broker_engine_state{engine}
kubani_gpu_broker_inflight_requests{engine}
kubani_gpu_broker_sleep_total{engine,level,result}
kubani_gpu_broker_wake_total{engine,result}
kubani_gpu_broker_sleep_duration_seconds{engine,level}
kubani_gpu_broker_wake_duration_seconds{engine}
kubani_gpu_broker_idle_seconds{engine}
kubani_gpu_broker_lease_active
kubani_gpu_broker_lease_acquire_duration_seconds
kubani_gpu_broker_training_blocked_requests_total
kubani_gpu_broker_recovery_total{reason}
kubani_gpu_broker_upstream_errors_total{engine,type}
```

Useful dashboards:

### Inference lifecycle

- awake/sleeping timeline,
- wake count,
- wake p50/p95/p99,
- request rate,
- in-flight requests,
- idle periods.

### GPU lifecycle

Overlay:

- broker GPU owner,
- DCGM utilization,
- GPU-visible memory,
- training Job state.

Expected visual pattern:

```text
Inference AWAKE ─────┐
GPU memory high      │
                     ▼
Inference SLEEPING ─────────
GPU memory lower
                     │
Training TRAINING ──────────
GPU utilization high
                     │
Training completes   ▼
SLEEPING ───────────────────
                     │ next request
                     ▼
AWAKE ──────────────────────
```

Structured logs should include:

```text
request_id
engine
previous_state
new_state
lease_id
workflow_id
operation
duration_ms
reason
```

---

# 24. Security

## 24.1 Never expose raw vLLM dev endpoints

`VLLM_SERVER_DEV_MODE=1` is required for Sleep Mode control endpoints.

Therefore:

- raw `llm-engine` is ClusterIP-only,
- no Ingress points to it,
- Traefik points only to the broker,
- broker forwards only legitimate inference paths on its public listener.

## 24.2 Separate public and admin listeners

Preferred:

```text
:8080 public OpenAI proxy
:8081 internal admin/metrics
```

Only `:8080` is reachable from Traefik.

The Temporal worker can reach `:8081`.

## 24.3 NetworkPolicy

Add explicit policies:

```text
Traefik → broker public port
broker → vLLM engine :8000
Temporal worker → broker admin port
Prometheus → broker metrics
DNS as required
```

Do not permit public ingress to raw engine pods.

The current namespace-wide egress isolation means broker-to-engine egress must be explicitly allowed.

## 24.4 RBAC

Broker:

```text
get/list/watch Lease
create/update/patch Lease
get/list/watch Jobs
get/list/watch Pods
```

No ability to create arbitrary Jobs.

Temporal training worker:

```text
create/get/list/watch/delete Jobs
get/list/watch Pods
```

scoped to a dedicated training namespace where practical.

Secrets:

- internal admin bearer token can be SOPS-managed,
- no Hugging Face token should be exposed to the broker unless it actually needs it.

---

# 25. Kubani GitOps Changes

Recommended directory changes:

```text
infrastructure/gitops/apps/vllm/
├── namespace.yaml
├── model-config.yaml
├── deployment.yaml                 # main vLLM
├── engine-service.yaml             # NEW: raw internal vLLM
├── broker-config.yaml              # NEW
├── broker-deployment.yaml          # NEW
├── broker-service.yaml             # NEW/public llm-api
├── broker-serviceaccount.yaml      # NEW
├── broker-role.yaml                # NEW
├── broker-rolebinding.yaml         # NEW
├── gpu-lease.yaml                  # NEW
├── ingress.yaml
├── fast-model-...
├── embeddings-...
└── kustomization.yaml
```

The exact file split can be adjusted to Kubani conventions.

---

# 26. Main vLLM Manifest Changes

Add:

```yaml
env:
  - name: VLLM_SERVER_DEV_MODE
    value: "1"
```

and:

```text
--enable-sleep-mode
```

Conceptually:

```yaml
args:
  - |
    exec vllm serve "$LLM_MODEL_PATH" \
      --served-model-name "$LLM_MODEL_NAME" \
      --host 0.0.0.0 \
      --port 8000 \
      --enable-sleep-mode \
      --gpu-memory-utilization "$LLM_GPU_MEMORY_UTILIZATION" \
      --max-model-len "$LLM_MAX_MODEL_LEN" \
      --max-num-batched-tokens "$LLM_MAX_NUM_BATCHED_TOKENS" \
      --kv-cache-dtype fp8 \
      --attention-backend flashinfer \
      --enable-prefix-caching \
      --enable-auto-tool-choice \
      --tool-call-parser qwen3_coder \
      --reasoning-parser qwen3
```

Once sleep mode is the idling mechanism, the main deployment should normally remain:

```yaml
replicas: 1
```

rather than scaling to zero between uses.

Until qualification is complete, the broker can run in transparent-proxy mode while leaving sleep disabled.

---

# 27. Service Migration

Create raw engine Service:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: llm-engine
  namespace: vllm
spec:
  selector:
    app: vllm
  ports:
    - name: http
      port: 8000
      targetPort: http
```

Change `llm-api` to select the broker:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: llm-api
  namespace: vllm
spec:
  selector:
    app: gpu-broker
  ports:
    - name: http
      port: 8000
      targetPort: 8080
```

Existing Ingress can continue targeting:

```text
llm-api:8000
```

This preserves the external hostname and client configuration.

---

# 28. Broker Deployment Sketch

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gpu-broker
  namespace: vllm
spec:
  replicas: 1
  selector:
    matchLabels:
      app: gpu-broker
  template:
    metadata:
      labels:
        app: gpu-broker
    spec:
      serviceAccountName: gpu-broker
      containers:
        - name: broker
          image: ghcr.io/x-mckay/kubani-gpu-broker:<pinned-version>
          ports:
            - name: public
              containerPort: 8080
            - name: admin
              containerPort: 8081
          env:
            - name: CONFIG_PATH
              value: /etc/gpu-broker/config.yaml
          volumeMounts:
            - name: config
              mountPath: /etc/gpu-broker
              readOnly: true
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: "1"
              memory: 512Mi
      volumes:
        - name: config
          configMap:
            name: gpu-broker-config
```

No GPU resource should be requested by the broker.

---

# 29. Multiple Models

Do not solve all models in the first release.

Recommended sequence:

### Phase A

Manage only:

```text
main Qwen vLLM
```

### Phase B

Add:

```text
fast model
embeddings
```

The broker configuration can already support an engine registry.

Longer term:

```yaml
engines:
  main: ...
  fast: ...
  embeddings: ...
```

Each engine gets:

- independent idle timeout,
- independent sleep support,
- independent wake lock,
- independent health state.

The physical GPU lease remains global.

---

# 30. vLLM Production Stack: Use or Not?

Current vLLM Production Stack has useful sleep-aware routing and exposes sleep/wake operations through its router.

However, the documented behavior for a request to a sleeping engine is still effectively:

```text
sleeping engine → do not route / return unavailable
```

rather than:

```text
request → transparently wake → serve request
```

It also does not supply Kubani's training ownership policy.

Two possible designs are therefore:

## Option A — custom thin broker

```text
Traefik → Kubani broker → vLLM
```

Advantages:

- smallest operational change,
- exact desired semantics,
- integrates directly with Temporal leases,
- preserves existing vLLM manifests,
- easy to understand.

**Recommended.**

## Option B — Production Stack + Kubani policy controller

```text
Traefik
   ↓
Kubani wake/lease gateway
   ↓
vLLM Production Stack router
   ↓
vLLM engines
```

Advantages:

- richer multi-engine routing ecosystem.

Disadvantages:

- extra layer,
- larger operational footprint,
- still requires custom wake/training policy.

For the current single-Spark homelab, Option A is simpler.

---

# 31. Rollout Plan

## Phase 0 — hardware qualification

- add sleep flags manually,
- no automatic idle sleeping,
- run DGX Spark qualification suite,
- determine safe Level 1 behavior,
- determine whether Level 2 is safe,
- record wake latency and memory behavior.

Exit criterion:

```text
sleep/wake behavior is demonstrably reliable on exact production configuration
```

## Phase 1 — transparent broker

Deploy broker with:

```yaml
auto_sleep_enabled: false
exclusive_leases_enabled: false
```

Move `llm.almckay.io` behind broker.

Validate:

- streaming,
- tool calling,
- reasoning fields,
- errors,
- throughput,
- TTFT,
- request cancellation.

Exit criterion:

```text
broker is transparent relative to direct vLLM
```

## Phase 2 — manual sleep/wake

Enable internal manual operations.

Validate state reconstruction and recovery.

## Phase 3 — idle auto-sleep

Enable:

```yaml
auto_sleep_enabled: true
idle_timeout_seconds: 600
idle_sleep_level: 1
```

Observe for several days.

## Phase 4 — Temporal GPU lease

Add:

- Kubernetes Lease,
- admin lease API,
- Temporal acquire/release activities,
- training Job labels,
- training rejection behavior.

Initially use:

```yaml
training_reclaim_mode: restart
```

or Level 1 if memory permits.

## Phase 5 — deep reclaim

Only if qualification succeeds:

```yaml
training_reclaim_mode: level2
```

Add the weight reload path.

## Phase 6 — fast model and embeddings

Move remaining Spark models under the same ownership system.

---

# 32. Acceptance Criteria

The implementation is complete when all of the following hold.

## Request behavior

- An awake model serves requests normally.
- An idle model sleeps after the configured inactivity period.
- A request to an idle sleeping model wakes it transparently.
- Concurrent requests cause exactly one wake operation.
- Streaming requests prevent idle sleep until they finish.
- Health checks do not keep models awake.

## Training behavior

- Training cannot start before inference is drained.
- Training cannot start before required inference engines are sleeping.
- Inference cannot wake while a training lease exists.
- Training Job labels include the lease ID.
- Lease release occurs in Temporal `finally` logic.
- A failed Temporal worker does not create unsafe simultaneous inference/training ownership.
- After training, vLLM may remain asleep until actual inference demand occurs.

## Failure behavior

- Broker restart reconstructs state safely.
- Wake failure produces controlled 503s rather than forwarding into a broken engine.
- Lease uncertainty fails closed.
- Active training prevents stale-lease recovery.
- No raw vLLM development endpoint is publicly routable.

## Observability

- Every state transition is logged.
- Sleep/wake duration is measured.
- Lease owner is visible.
- Inference rejection during training is counted.
- Broker state can be correlated with DCGM GPU utilization/memory.

---

# 33. Recommended First Implementation

The first useful implementation can stay intentionally small.

Build:

```text
kubani-gpu-broker
```

with:

1. one engine (`main`),
2. one replica,
3. transparent `/v1/*` streaming proxy,
4. in-flight accounting,
5. Level 1 manual sleep/wake,
6. single-flight wake,
7. idle timer behind a feature flag,
8. Kubernetes Lease,
9. training lease API,
10. Prometheus metrics.

Do **not** initially build:

- training preemption,
- dynamic model loading,
- multi-GPU scheduling,
- queue persistence,
- Redis/Postgres state,
- multiple broker replicas,
- semantic routing,
- automatic model promotion.

Those can be added once the core ownership protocol is proven.

---

# 34. Recommended Default Policy

After qualification:

```yaml
policies:
  auto_sleep_enabled: true

  # Interactive inference.
  idle_timeout_seconds: 600
  min_awake_seconds: 120
  idle_sleep_level: 1

  # Exclusive jobs.
  drain_timeout_seconds: 300
  inference_during_training: reject

  # Start conservatively on GB10.
  training_reclaim_mode: restart

  # Switch only after qualification.
  # training_reclaim_mode: level2
```

This gives the desired user experience:

```text
normal request
   ↓
Spark inference wakes automatically
   ↓
requests stop
   ↓
10 minutes
   ↓
inference sleeps
   ↓
Temporal experiment wants GPU
   ↓
broker confirms GPU ownership
   ↓
training runs
   ↓
training finishes
   ↓
GPU remains idle/free
   ↓
next OpenAI request
   ↓
inference wakes automatically
```

---

# 35. Implementation Order

A practical development order:

```text
1. Create broker repo and fake-vLLM integration tests.
2. Implement transparent streaming proxy.
3. Implement vLLM sleep driver.
4. Implement in-flight accounting.
5. Implement single-flight wake.
6. Implement idle state machine.
7. Implement Prometheus/state endpoints.
8. Add Kubernetes Lease support.
9. Add exclusive training lease API.
10. Integrate Temporal activities.
11. Add Kubani Flux manifests.
12. Move Traefik traffic through broker.
13. Run Spark qualification suite.
14. Enable auto-sleep only after qualification.
15. Add Level 2/deep reclaim only after separate qualification.
```

---

# 36. Source References

## Kubani

- Kubani repository:
  - https://github.com/X-McKay/kubani
- Repository scope:
  - `docs/infrastructure/repository-scope.md`
- vLLM main deployment:
  - `infrastructure/gitops/apps/vllm/deployment.yaml`
- vLLM model configuration:
  - `infrastructure/gitops/apps/vllm/model-config.yaml`
- vLLM service:
  - `infrastructure/gitops/apps/vllm/service.yaml`
- vLLM ingress:
  - `infrastructure/gitops/apps/vllm/ingress.yaml`
- GPU configuration:
  - `docs/infrastructure/configuration/gpu.md`
- Temporal HelmRelease:
  - `infrastructure/gitops/apps/temporal/helmrelease.yaml`

## vLLM

- Sleep Mode documentation:
  - https://github.com/vllm-project/vllm/blob/main/docs/features/sleep_mode.md
- vLLM Production Stack sleep/wake tutorial:
  - https://docs.vllm.ai/projects/production-stack/en/latest/use_cases/sleep-wakeup-mode.html
- vLLM Production Stack:
  - https://github.com/vllm-project/production-stack

## DGX Spark sleep-mode issues to track

- DGX Spark Level 1 sleep / wake EngineCore crash:
  - https://github.com/vllm-project/vllm/issues/50011
- DGX Spark sleep-mode / FP8 KV wake failure:
  - https://github.com/vllm-project/vllm/issues/39078

---

# 37. Final Recommendation

Implement a **small Kubani GPU Broker**, not a new general-purpose scheduler.

Keep its responsibilities narrowly defined:

```text
OpenAI proxy
+
idle sleep
+
transparent wake
+
exclusive GPU lease
```

Use Temporal above it for durable experiment orchestration and Kubernetes below it for process scheduling.

This cleanly separates:

```text
Flux/Kubani       → desired infrastructure state
Kubernetes        → process placement
GPU Broker        → physical GPU ownership + inference lifecycle
Temporal          → durable training/evaluation workflow
vLLM              → inference engine + memory sleep primitives
```

That architecture fits Kubani's current structure, minimizes new infrastructure, gives the Spark a single explicit owner at any point in time, and leaves room to extend the same broker to the fast model, embeddings, and future GPU nodes.
