# Starbase inactive Phase 3 promotion bundle

This directory contains the accepted ADR 0008 render-and-promote prototype for
Starbase `0.1.0-rc.2`. It is intentionally absent from the parent
`apps/kustomization.yaml`, so Flux does not see or reconcile any object here.
The retained validation and cluster checkpoint are in
[`docs/infrastructure/gitops/starbase-phase3-inactive-bundle.md`](../../../../docs/infrastructure/gitops/starbase-phase3-inactive-bundle.md).

The authoritative inputs are:

- `promotion-input.json`: Kubani-owned target constraints and the immutable
  release-manifest evidence identity;
- the clean Starbase evidence checkout at the recorded evidence revision; and
- the clean Starbase base checkout at the source revision derived from that
  manifest.

`rendered.yaml` and `promotion-lock.json` are generated evidence. Never edit
them directly. The lock binds the manifest, source revision, six signed image
digests, base tree, target input, renderer, exact local rendering toolchain,
object inventory, rendered bytes, and intended inactive activation state.

The current supported rendering platform is `darwin-arm64`, recorded with
binary and module digests in the lock. Linux CI toolchain recording and the
separate trusted source-acquisition job remain gated on the separately
authorized read-only GitHub App identity. Pull-request CI runs only synthetic
unit tests; it receives no Starbase credential and does not claim to reproduce
the private-source bundle yet.

Generate or verify from clean authenticated checkouts:

```sh
just starbase-promotion-generate /path/to/evidence-checkout /path/to/source-checkout
just starbase-promotion-verify /path/to/evidence-checkout /path/to/source-checkout
```

For this release, the evidence checkout is
`c966518b8c82e755664faa9c37bfd5854089f8a2` and the manifest derives the base
checkout `ab25087ec856be89d2e00f69f7d230d71cf5301a`. They must remain distinct
inputs; the base revision is always derived from the verified manifest.

The generated bundle pins all six accepted images, renames both migration Jobs
from their migration-content digests, and records the GitHub connector at zero
replicas with no GitHub egress. The remaining workloads and migrations are
rendered for review but blocked from activation by the deployment plan's
runtime, identity, data, recovery, observability, and capacity gates.

Generating or reviewing these files does not authorize the GitHub App
credential, adding this directory to a Flux aggregate, merging a Kubani change,
reconciliation, migration execution, secret provisioning, or cluster mutation.
