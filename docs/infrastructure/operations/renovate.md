# Renovate

Renovate runs in **PR-only mode**: `renovate.json` at the repo root sets
`"automerge": false` everywhere, so every dependency update — a Helm
chart, a container image, a GitHub Action, a Python dependency — arrives
as a PR for review, never applied directly. `"dependencyDashboard": true`
keeps a single open issue listing pending and rate-limited updates;
`"prConcurrentLimit": 5` caps how many open PRs Renovate keeps in flight
at once so the PR queue stays reviewable.

## What it watches

| Manager | Scope | Config |
|---|---|---|
| `flux` | `HelmRelease`/`HelmRepository` objects under `infrastructure/gitops/` | `managerFilePatterns` set explicitly — Renovate's flux manager has no default file pattern for a non-standard layout like this repo's |
| `kubernetes` | Container image references in plain manifests under `infrastructure/gitops/` | Same reason: the kubernetes manager matches nothing until `managerFilePatterns` is set |
| `github-actions` | `.github/workflows/` | Default file matching, no extra config needed |
| `pep621` / `pip_requirements` | `pyproject.toml` (this repo's Ansible/tooling dependencies) | Default file matching |

`packageRules` groups Helm chart and its repository together, and groups
plain-manifest image bumps by workload name, so one logical upgrade is one
PR instead of two separate ones landing out of order. Every PR carries the
`renovate` label.

## The vLLM image rule

`vllm/vllm-openai` tags carry an architecture/CUDA-variant suffix that is
not cosmetic — `v0.30.0-aarch64-cu129` fails to import on this hardware
while `v0.30.0-aarch64` (CUDA 13) is the tag that actually works (see
`docs/infrastructure/inference/release-process.md`'s preflight section).
A default semver-style update could just as easily propose `-cu129` as
`-aarch64`, since both parse as "a version of the same image." The
`packageRules` entry for `vllm/vllm-openai` uses [Renovate's regex
versioning scheme](https://docs.renovatebot.com/modules/versioning/regex/)
with a `compatibility` capture group around the suffix:

```
regex:^v?(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)(?<compatibility>-aarch64(?:-cu\d+)?)$
```

Per that doc, "a proposed Renovate update will never change the specified
compatibility value" — so Renovate still proposes `v0.30.0-aarch64` →
`v0.31.0-aarch64`, but never proposes swapping the suffix itself.

## Digest pinning is off

`"pinDigests": false` — this repo pins images by CI sha tag or a specific
version tag (see `.claude/rules/gitops.md`'s image tag rule and the
service skeleton's `deployment.yaml` comment), not by digest. Renovate's
digest-pinning preset is not part of `config:recommended` by default, and
this file makes the choice explicit so a future edit does not silently
turn it on.

## Before merging a vLLM image PR

Run `just inference-preflight <image>` against the proposed tag before
approving. Renovate proves the tag exists and matches the version pattern;
it does not prove the image actually starts on this hardware or has the
flags the current `model-config` needs — that is exactly what preflight
checks, and exactly why it fails loudly on a CLI crash (see the inference
release process). Merging a vLLM image PR still goes through the [platform
release process](release-process.md) as its own change — Renovate opening
the PR does not skip preflight, baseline, canary, or soak.

## Review cadence

Renovate PRs are reviewed weekly — see the [maintenance
calendar](maintenance-calendar.md). A PR sitting unreviewed past that is
the dependency dashboard issue's job to surface, not a reason to
auto-merge it.

## Related documentation

- [Inference release process](../inference/release-process.md) — preflight before a vLLM image PR merges
- [Maintenance calendar](maintenance-calendar.md)
- `.claude/rules/gitops.md` — the image tag rule this config enforces
