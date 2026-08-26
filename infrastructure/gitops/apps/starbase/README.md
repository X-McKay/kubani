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

The optional `rbac_profile` promotion input selects one exact renderer policy:

- omission means the backward-compatible `cluster-observer-v1` profile used by
  the retained `0.1.0-rc.2` bundle; it accepts exactly one named ClusterRole and
  one matching ClusterRoleBinding with the historical reviewed rules;
- `starbase-namespaces-v1` accepts exactly one list-only Role and RoleBinding in
  each of `starbase-system`, `starbase-connectors`, and `starbase-execution`,
  and rejects every ClusterRole and ClusterRoleBinding.

There is no auto-detection or permissive profile. New namespace-bounded release
inputs must select `starbase-namespaces-v1` explicitly, and generated locks
record that selection. Existing legacy locks without the field remain
verifiable only under the legacy default. An RBAC topology change therefore
changes the content-bound promotion input and requires a new generated bundle,
review, and rollout; it cannot silently widen an accepted release.

The current supported rendering platform is `darwin-arm64`, recorded with
binary and package digests plus the PyYAML LibYAML implementation flag in the
lock. Accepted Starbase ADR 0009 temporarily defers the Linux CI toolchain and
separate trusted source-acquisition job during bounded single-owner homelab
pre-production. Pull-request CI receives no Starbase credential. It verifies
synthetic policy tests and the committed bundle's digest, inventory, exact
RBAC, workload and network controls, locked images, zero-replica GitHub
connector, and agreement between the lock's activation intent and actual Flux
references. It does not independently authenticate or reproduce the private
Starbase source.

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

Status: deferred by accepted Starbase ADR 0009 until its first trigger or
2026-11-30; tracked as P1 debt

Al McKay accepted the bounded deferral on 2026-08-24. It is being versioned in
[Starbase PR #18](https://github.com/X-McKay/Starbase/pull/18), which must merge
before this activation PR. During the exception, the exact clean local
generation and verification evidence retained in the Phase 4A ledger is the
accepted compensating control. It is owner-controlled and not independent.

Before ADR 0009 expires or any of its trust-expansion triggers occurs, close
the deferred gate with all of the following:

- the dedicated GitHub App has been provisioned with verified, repository-only
  `contents:read` access;
- the supported Linux renderer toolchain identity has been recorded;
- trusted default-branch or privileged CI acquires the two private source
  revisions and proves byte-for-byte equality with this committed bundle
  without exposing its credential to pull-request code; and
- credential isolation, fork failure, and revocation have been exercised and
  retained as evidence.

The deferral does not cover the GitHub connector's separate provider identity
and does not authorize the promotion GitHub App credential, merging a Kubani
activation change, reconciliation, migration execution, secret provisioning,
or cluster mutation. Updating the lock to the proposed inert-foundation state
keeps the root-of-trust record truthful; ordinary CI still proves consistency,
not independent private-source provenance.
