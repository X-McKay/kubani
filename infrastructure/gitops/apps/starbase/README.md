# Starbase Phase 3 promotion bundle

This directory contains the accepted ADR 0008 render-and-promote bundle for
Starbase `0.1.0-rc.2`. It remains intentionally absent from the shared parent
`apps/kustomization.yaml`. The proposed Phase 4A desired state instead reaches
it only through the dedicated, inert `starbase-phase4a-foundation` path. The
retained Phase 3 validation and cluster checkpoint are in
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
object inventory, rendered bytes, and intended activation state.

The current supported rendering platform is `darwin-arm64`, recorded with
binary and package digests plus the PyYAML LibYAML implementation flag in the
lock. Linux CI toolchain recording and the separate trusted source-acquisition
job remain gated on the separately authorized read-only GitHub App identity.
Pull-request CI receives no Starbase credential. It verifies synthetic policy
tests and the committed bundle's digest, inventory, exact RBAC, workload and
network controls, locked images, zero-replica GitHub connector, and agreement
between the lock's activation intent and actual Flux references; it does not
claim to reproduce the private-source bundle yet.

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
from a digest of each migrator's complete ordered migration set, and records
the GitHub connector at zero replicas with no GitHub egress. The remaining
workloads and migrations are rendered for review but blocked from activation by
the deployment plan's runtime, identity, data, recovery, observability, and
capacity gates.

## Owned promotion follow-up

Owner: Al McKay

Status: open; hard blocker before merging an activation revision

The exact private-source regeneration check is deliberately not available to
untrusted pull-request code. Close this gate only when all of the following are
true:

- the dedicated GitHub App has been provisioned with verified, repository-only
  `contents:read` access;
- the supported Linux renderer toolchain identity has been recorded;
- trusted default-branch or privileged CI acquires the two private source
  revisions and proves byte-for-byte equality with this committed bundle
  without exposing its credential to pull-request code; and
- credential isolation, fork failure, and revocation have been exercised and
  retained as evidence.

Generating or reviewing these files does not authorize the GitHub App
credential, merging a Kubani activation change, reconciliation, migration
execution, secret provisioning, or cluster mutation. Updating the lock to the
proposed inert-foundation state keeps the root-of-trust record truthful; it does
not close this trusted-CI provenance gate.
