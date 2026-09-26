# Inference Release and Change Process

Every change to how a model is served goes through this process: a new model, a
new vLLM image, or a changed vLLM flag or `model-config` value. The goal is to
know the expected serving performance before a change, to prove the change did
not make it worse, and to be able to detect later degradation against a known
reference.

It measures the **deployment**, not the model's answer quality: time to first
token, inter-token latency, decode and aggregate throughput, sleep/wake
latency, and stability under sustained load.

Claude runs this through the `inference-release` skill
(`.claude/skills/inference-release/SKILL.md`).

## Tooling

| Command | What it does |
|---|---|
| `just inference-preflight <image> [--module m] [--flag --x=y]` | Pre-pulls the image on the inference node. Reports vLLM, torch and FlashInfer versions. Fails if a required Python module or serve flag/choice is missing from that build. |
| `just inference-bench <profile> <label> [bench args]` | Runs the benchmark as an in-cluster Job next to the engine and writes `benchmarks/<profile>/<UTC>_<label>.json`. Exits non-zero if a gate fails. |
| `just inference-compare <profile> <result.json>` | Diffs a result against the profile's promoted baseline. Verdict is PASS, WARN or FAIL (exit 1 on FAIL). |
| `just inference-promote <profile> <result.json>` | Makes a result the profile's baseline. |

The scripts live in `infrastructure/scripts/inference_bench/`. Profiles (`main`,
`fast`) and regression thresholds are in `profiles.json`. Changing a profile
invalidates comparisons, so re-baseline in the same PR.

### What a run measures

All load goes through the gpu-broker, the same path clients use. Direct engine
load is unsafe: the broker sees the engine as idle, sleeps it, and requests to
a sleeping engine hang.

| Suite | Measures | Gates |
|---|---|---|
| `perf` | Per scenario: TTFT p50/p95, ITL p50/p95, e2e p50/p95, per-request decode tok/s, aggregate output tok/s. Scenarios cover short prompts, 8k/32k prefill, prefix-cache hits, and concurrency up to `--max-num-seqs`. Output length is pinned with `ignore_eos`, and prompt lengths are calibrated against the live tokenizer. | `perf.no_errors` |
| `sleepwake` | Level-1 sleep through the broker admin API, then transparent wake on a request. Records sleep time and wake-to-first-token time over 3 cycles. | `all_cycles_completed`, `output_sane_after_wake` (catches weights not being restored on wake) |
| `soak` | Sustained load at max concurrency for `--soak-seconds` (default 900). A request that goes silent for 60 s is a stall, which is the GB10 EngineCore wedge. | `soak.no_stalls`, `soak.no_errors` |

The result records the image, the vLLM serve flags, `model-config`, the engine
pod and node, the repo commit and the Flux revision. A number is never separated
from the configuration that produced it.

### Verdicts

`compare.py` checks each metric in its "worse" direction: `*_ms` getting higher,
`*_tps` getting lower. Defaults in `profiles.json`:

- **FAIL**: 25% or more worse, or a gate that passed in the baseline now fails.
- **WARN**: 10% or more worse, a metric has disappeared, or a gate fails in both
  baseline and candidate (a pre-existing defect).
- A change must also exceed `min_abs` (2 ms or 2 tok/s) to count, so jitter on
  very fast paths is ignored.

Run-to-run noise on this hardware is a few percent. If a WARN sits close to the
threshold, re-run the candidate before deciding.

## The process

### 1. Change record

Copy the template below to `docs/infrastructure/inference/releases/YYYY-MM-DD-<change>.md`.
Before touching anything, state what changes, why, the expected effect, the
rollback, and the stages.

**Change one variable per stage.** An image bump and a kernel-backend change go
in separately, each measured against the previous stage's result. Otherwise a
regression cannot be attributed to either one.

### 2. Preflight the candidate (no production impact)

- Confirm the tag exists for arm64. The node is a GB10: `aarch64`, sm_121.
- `just inference-preflight <image> --module <optional pkg> --flag --<flag>=<value>`
  for every new flag, choice and optional package. Upstream docs describe
  what a flag does, but only a preflight shows whether this particular image
  build actually includes it.
- The preflight leaves the image cached on the node, so both the rollout and a
  rollback avoid a multi-GB pull.

### 3. Baseline

- Needed when the profile has no `BASELINE`, or its baseline was taken on a
  different image, flags or config than what is running now. Compare
  `meta.image` and `meta.args` to decide.
- Run on the current production config, and make sure no other GPU work is
  running (fine-tuning, the other engine under load):
  `just inference-bench <profile> baseline-<desc>`
- Promote it with `just inference-promote <profile> <result>`.

### 4. Stage the rollout: fast model first, then main

- **Image changes** go to the `fast` profile first. It shares the image and
  sleep mode with the main model, which makes it a cheap canary for image
  pulls, startup, and sleep/wake. It runs `--enforce-eager` and is dense, so
  it proves nothing about MoE kernels, CUDA graphs, or FP8 KV.
- **Main-model changes** happen in a maintenance window: announce it, and
  expect about 5 minutes of downtime per restart (Recreate strategy, weight
  load plus kernel compile).
- Deploy through GitOps: one commit per stage, with the prior value in the
  commit message. After Flux applies it, wait for the pod to be Ready and one
  real completion to succeed before benchmarking.
- If you need to recover a wedged engine, delete the pod. Never use
  `rollout restart`, which Flux reverts mid-load (see
  `docs/troubleshooting/vllm-main-engine-hang-gb10.md`).

### 5. Measure and decide

```bash
just inference-bench <profile> candidate-<desc>
just inference-compare <profile> docs/infrastructure/inference/benchmarks/<profile>/<result>.json
```

| Verdict | Action |
|---|---|
| PASS | Keep it. Promote the result to be the new baseline, and record it in the change record. |
| WARN | The operator decides. Write down why in the change record before promoting. |
| FAIL | Revert the stage's commit, confirm the rollback with a real completion, and record what failed. |

Paste the `compare` output and the verdict into the change record, and commit
the result JSON files along with it.

### 6. Watch for degradation after release

Re-run the benchmark and compare against the current baseline:

- after any cluster change that touches the inference node (driver, K3s, GPU
  operator, kernel);
- when users report slowness;
- monthly otherwise, as `just inference-bench main drift-YYYYMM`.

Drift runs are never promoted. If one shows a WARN or FAIL, the platform has
changed underneath the deployment, and that needs investigating.

## Change record template

```markdown
# <YYYY-MM-DD> <change title>

**Status:** planned | in progress | released | rolled back
**Profiles affected:** main | fast
**Window:** <when main-model restarts happen>

## Change
| | Before | After |
|---|---|---|
| Image | | |
| Flags | | |
| Config | | |

## Why
<problem this solves, evidence, upstream refs>

## Risks and rollback
<known issues; rollback = revert commit <sha>, prior image cached on node: yes/no>

## Stages
1. Preflight: `<command>` → <result>
2. <profile>: <change> → verdict <PASS/WARN/FAIL>, result `<file>`
...

## Results
<compare output per stage>

## Decision
<kept / reverted, and why; baselines promoted>
```
