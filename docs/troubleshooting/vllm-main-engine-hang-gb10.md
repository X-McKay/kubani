# vLLM Main Engine Hang on GB10 (Xid 13 / silent stall)

**Status:** open — recurrence watch. First seen 2026-09-25.

## The one-line answer

If `https://llm.almckay.io/v1/models` answers but chat completions hang forever, the
vLLM **EngineCore is wedged in a CUDA kernel** while the API server (and therefore the
`/health` liveness probe) still reports healthy. Nothing restarts it automatically.
Recover by deleting the pod (the Deployment uses `Recreate`, so this is a clean restart):

```bash
KUBECONFIG=/home/al/.kube/config kubectl delete pod -n vllm -l app=vllm
KUBECONFIG=/home/al/.kube/config kubectl rollout status deployment/vllm -n vllm --timeout=15m
```

Do **not** use `kubectl rollout restart` here. It works by stamping a `restartedAt`
annotation on the pod template, and Flux reverts that on its next reconcile (≤10 min). On
2026-09-25 that killed the replacement pod 3 minutes into weight loading and started a second
one, doubling the outage. Deleting the pod leaves the spec untouched.

Expect roughly 5 minutes before ready (weight load + GDN/SSM kernel compile + FlashInfer
init). Then confirm with a real completion, not `/v1/models`:

```bash
curl -s -m 60 https://llm.almckay.io/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen3.6-35B-A3B-NVFP4","messages":[{"role":"user","content":"Say OK"}],"max_tokens":5}'
```

---

## How to recognise it

| Signal | Wedged engine | Healthy |
|---|---|---|
| `GET /v1/models` via broker or engine | 200 | 200 |
| `POST /v1/chat/completions` | hangs until client timeout, empty body | 1–5 s |
| `nvidia-smi` on sparky | ~96% util at ~19 W (spinning kernel, no work) | util tracks load, power rises with it |
| `/metrics` `vllm:num_requests_running` | stuck non-zero, never drains | rises and falls |
| Engine log `loggers.py` stats line | stops appearing, or shows `Avg generation throughput: 0.0 tokens/s, Running: N reqs` | every 10 s while busy |
| EngineCore process (`pid 300` in pod) | ~2% CPU, main thread in `futex_wait_queue`, all threads `S` | busy |
| Fast model (`llm-fast.almckay.io`) on the same GPU | still answers | answers |

The fast model working proves the GPU is not globally hung; only the main engine's CUDA
context is. The `/health` probe passing is exactly why this goes unnoticed.

---

## Incident record: 2026-09-25

Two incidents on `sparky` (NVIDIA GB10, driver 580.95.05, `vllm/vllm-openai:v0.27.1-aarch64-cu129`,
model `nvidia/Qwen3.6-35B-A3B-NVFP4`, `--moe-backend marlin --attention-backend flashinfer
--kv-cache-dtype fp8 --enable-prefix-caching --max-num-seqs 4`).

### 1. 20:25 UTC — GPU fault, self-recovered

- Kernel log on sparky: 48 groups of `NVRM: Xid 13, Graphics SM Warp Exception ... Out Of
  Range Address` across GPC 3 TPC 3–5, then `Xid 43, pid=<EngineCore>`.
- These were the **first Xid events on sparky in 30 days** (boot 2026-08-16).
- vLLM raised `EngineDeadError`, returned one HTTP 500, shut down cleanly (exit 0), kubelet
  restarted the container. Engine was serving 4 concurrent requests at the time.

### 2. 22:52 UTC — silent stall, no self-recovery

- Restarted engine served normally ~22:12–22:51 UTC.
- 22:51:52 generation throughput dropped 100 → 38 tok/s; 22:52:02 → 0.0 tok/s with
  `Running: 2 reqs`. No further stats lines, no error, **no Xid**.
- Discovered ~23:30 UTC during a routine health check. Every completion hung for the full
  client timeout; `/v1/models` and `/health` kept returning 200.
- Engine bypass (port-forward to `svc/llm-engine`) hung identically, ruling out the broker
  and Traefik.

Forensic copies of both container logs and the kernel Xid log were saved to
`~/kubani-forensics/vllm-2026-09-25/` on rig0. `py-spy` is not in the image, so no Python
stack of the wedged EngineCore was captured.

### Working hypothesis

Xid 13 "Out Of Range Address" is an illegal memory access inside a kernel — a software bug,
not hardware. The same buggy path plausibly explains the second incident as a spin instead of
a fault. Candidates, all experimental on this stack per vLLM's own startup warnings:

- Marlin weight-only NVFP4 fallback (`marlin.py:34`: "Your GPU does not have native support
  for FP4 computation").
- Mamba/GDN prefix caching in `align` mode (`config.py:638`: "support for Mamba layers is
  experimental").
- FlashInfer attention with fp8 KV under concurrency (both incidents had ≥2 requests running).

Not confirmed. If it recurs, capture `nvidia-smi -q`, the engine log tail, and the kernel log
before restarting, and note how many requests were running.

---

## Why the cluster did not heal itself

- **Liveness probe is `GET /health`.** In vLLM v1 that only proves the API server process
  is alive; it stayed 200 throughout the stall.
- **The gpu-broker only proxies.** It has `connect_timeout_seconds: 10` but no read/stall
  deadline, so it forwards the hang to clients rather than tripping.
- **No alerting.** Monitoring is parked at 0 replicas (see
  `docs/plans/` monitoring notes), so nothing watched `vllm:num_requests_running` or
  generation throughput.

## Follow-ups

- [ ] Add a generation-based watchdog: either a liveness probe that runs a 1-token
      completion with a deadline, or stall detection in the gpu-broker that restarts the
      engine when `num_requests_running > 0` and generation throughput is 0 for N minutes.
- [ ] Add `py-spy` (or equivalent) to the serving image so a wedged EngineCore can be
      stack-dumped before restart.
- [ ] Watch for recurrence. Two in one day after 33 days clean suggests a workload or input
      trigger; correlate the client traffic around 20:22 and 22:50 UTC.
- [ ] If it recurs, file upstream against vLLM v0.27.1 with the Xid 13 trace, GB10,
      NVFP4 + Marlin + FlashInfer config.

Related: `docs/plans/active/2026-08-16-vllm-gpu-sleep-wake-broker.md` (broker design;
level-2 sleep corrupts output on GB10 — unrelated to this hang, sleep was not involved).
