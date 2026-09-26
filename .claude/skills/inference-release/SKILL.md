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

1. **Change record**: `docs/infrastructure/inference/releases/YYYY-MM-DD-<change>.md`
   from the template in the runbook. One variable per stage.
2. **Preflight** every new image, flag, flag value and optional package:
   `just inference-preflight <image> --module <pkg> --flag --<flag>=<value>`.
   This also pre-pulls the image onto sparky.
3. **Baseline** if `benchmarks/<profile>/BASELINE` is missing or its
   `meta.image`/`meta.args` don't match what is running:
   `just inference-bench <profile> baseline-<desc>`, then `just inference-promote`.
4. **Deploy one stage via GitOps**: fast model first for image changes, main
   model in an announced window. Wait for Ready and one real completion.
5. **Measure**: `just inference-bench <profile> candidate-<desc>`, then
   `just inference-compare <profile> <result>`.
6. **Decide**: PASS means promote. WARN means the operator decides, and the
   reason is written down. FAIL means revert the commit. Record everything in
   the change record and commit the result JSONs.

## Quick reference

| Situation | Action |
|---|---|
| Upstream says a flag or backend exists | Preflight it anyway. Optional extras such as `b12x` are not in the official image. |
| Image and flag change proposed together | Split them into two stages, each compared to the previous stage. |
| Gate fails in baseline too | Reported as pre-existing (WARN). Fix it separately. |
| Sleep/wake suite says the in-flight count is stuck | Broker counter leak. Restart that broker pod, then rerun. |
| Soak reports STALL | Engine wedge. Capture evidence per `docs/troubleshooting/vllm-main-engine-hang-gb10.md`, then delete the pod. |
| Something feels slow | `just inference-bench main drift-<date>` and compare it with the baseline. |

## Red flags: stop

- Benchmarking the candidate without a baseline on the current config.
- Sending load directly to an engine URL. The broker will sleep the engine and requests will hang.
- `kubectl rollout restart` on vllm. Flux reverts it mid-load. Delete the pod instead.
- Calling a change good because the pod is Ready or `/health` is 200. Neither
  shows that it serves, or serves fast.
- Skipping the soak on the main model. The GB10 stall only appears under sustained concurrency.
- Promoting a WARN without writing down why.
