---
name: inference-release
description: Use when changing how a model is served in the vllm namespace - bumping the vLLM image, adding or changing vllm serve flags (MoE/attention backend, cudagraph, KV dtype, max-num-seqs), editing model-config, adding or swapping a model - or when inference seems slower than it used to be, or when asked to benchmark TTFT, tok/s or sleep/wake latency.
---

# Inference Release

## Overview

Serving changes are released against measurements, not impressions. Every
change is benchmarked before and after with the same harness and profile, and
the comparison decides whether it stays. The full runbook is
`docs/infrastructure/inference/release-process.md`; read it before a release.

This measures the deployment (TTFT, ITL, tok/s, sleep/wake, stability), not
model answer quality.

## Workflow

0. **Capacity check** before the stage: `just capacity`. If any node is over
   its ceiling in `docs/infrastructure/cluster/capacity.md`, fix that first —
   a stage that lands on a node already past its ceiling is not a clean
   measurement and risks an eviction mid-rollout.
1. **Change record**: `docs/infrastructure/inference/releases/YYYY-MM-DD-<change>.md`
   from the template in the runbook. One variable per stage.
2. **Preflight** every new image, flag, flag value and optional package:
   `just inference-preflight <image> --module <pkg> --flag --<flag>=<value>`.
   This also pre-pulls the image onto sparky.
   - **Tag guidance**: on the GB10 (`aarch64`, sm_121), `v0.30.0-aarch64-cu129`
     cannot start — torch 2.14.0+cu130 paired with torchvision 0.28.0+cu129
     makes `vllm` die on import (`torchvision::nms does not exist`).
     `v0.30.0-aarch64` (cu130) is the tag that works and is also what
     unlocks FlashInfer GDN prefill on SM12x. Don't assume a cu129 tag is
     safe just because an older image used that convention.
   - **Preflight must fail on CLI crash, not report every flag missing.**
     If `vllm serve --help=all` itself crashes (wrong CUDA variant, broken
     import), `image_preflight.sh` reports every checked flag as
     `"NOT FOUND"` — that reads like "none of these flags exist" when the
     real problem is the CLI never ran. Treat a preflight where *every* flag
     comes back not found as `UNKNOWN (CLI failed)`, not as a flag-support
     verdict, and go straight to checking the image/CUDA variant instead of
     trying other flag spellings.
3. **Baseline** if `benchmarks/<profile>/BASELINE` is missing or its
   `meta.image`/`meta.args` don't match what is running:
   `just inference-bench <profile> baseline-<desc>`, then `just inference-promote`.
   - The perf client for v0.30+ is `vllm bench serve --save-result`, run from
     the engine image as the in-cluster Job (same mechanism as today's
     harness). **Caveat**: v0.30's own bench client counts client-side queue
     time inside TTFT, which the custom harness does not — never mix results
     from the two into the same comparison series. Keep `sleepwake` and
     `soak` in the custom harness regardless of which perf client is in use.
4. **Deploy one stage via GitOps**: fast model first for image changes, main
   model in an announced window. Wait for Ready and one real completion.
   - **Gateway path**: once the gateway fronts the engines (Phase 2+), bench
     through the gateway (`ai.almckay.io`) for gateway-affecting stages so
     the measurement matches what clients actually hit. For engine-only
     stages (a vLLM flag, an image bump before the gateway is in the path),
     bench through the broker as today — don't add gateway overhead to a
     measurement that isn't about the gateway.
5. **Measure**: `just inference-bench <profile> candidate-<desc>`, then
   `just inference-compare <profile> <result>`.
6. **Decide**: PASS means promote. WARN means the operator decides, and the
   reason is written down. FAIL means revert the commit. Record everything in
   the change record and commit the result JSONs.

If a stage wedges the engine mid-rollout, recover with
`just inference-restart <engine>` (`main` or `fast`) — never
`kubectl rollout restart` (Flux reverts it mid-load; see
`docs/troubleshooting/vllm-main-engine-hang-gb10.md`). Capture forensics
first with `just incident-capture <engine>` unless the stall is actively
blocking a maintenance window.

## Phase 1 gate reference (roadmap 9.4)

The decision reference for each Phase 1 stage — use these gates, not "pod is
Ready" or "`/health` is 200":

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

## Quick reference

| Situation | Action |
|---|---|
| Upstream says a flag or backend exists | Preflight it anyway. Optional extras such as `b12x` are not in the official image. |
| Image and flag change proposed together | Split them into two stages, each compared to the previous stage. |
| Gate fails in baseline too | Reported as pre-existing (WARN). Fix it separately. |
| Sleep/wake suite says the in-flight count is stuck | Broker counter leak. Restart that broker pod, then rerun. |
| Soak reports STALL | Engine wedge. Capture evidence per `docs/troubleshooting/vllm-main-engine-hang-gb10.md` (`just incident-capture <engine>`), then `just inference-restart <engine>`. |
| Something feels slow | `just inference-bench main drift-<date>` and compare it with the baseline. |

## Red flags: stop

- Benchmarking the candidate without a baseline on the current config.
- Sending load directly to an engine URL. The broker will sleep the engine and requests will hang.
- `kubectl rollout restart` on vllm. Flux reverts it mid-load. Delete the pod instead.
- Calling a change good because the pod is Ready or `/health` is 200. Neither
  shows that it serves, or serves fast.
- Skipping the soak on the main model. The GB10 stall only appears under sustained concurrency.
- Promoting a WARN without writing down why.
