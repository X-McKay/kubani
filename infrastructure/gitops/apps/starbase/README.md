# Starbase promotion bundle

This directory contains the accepted ADR 0008 render-and-promote bundle for
Starbase `0.1.0-rc.5`. It remains intentionally absent from the shared parent
`apps/kustomization.yaml`; Flux reaches it only through the dedicated, inert
`starbase-phase4a-foundation` path. That overlay holds core and the Kubernetes
connector at zero replicas, keeps the GitHub connector disabled at zero, and
suspends both migration Jobs. The retained original Phase 3 validation and
cluster checkpoint are in
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
`dac7bbd6b9739233e9141b7839e72cb57b278817` and the manifest derives the base
checkout `96c920472c29fcf7b536591fed4e363c34be36ff`. They must remain distinct
inputs; the base revision is always derived from the verified manifest. The
evidence manifest checksum is
`sha256:1c70f2c3412cee88c4790348fa6a5322881286c988b97132f6a5d0a617237265`.

The generated bundle pins all six accepted images and names both migration Jobs
from a digest of each complete ordered migration set and exact migrator
`repository@digest` reference. RC5's migration-source digests are byte-identical
to the completed RC4 evidence, so the successor Jobs remain suspended and are
not Flux health checks. A rebuilt migrator is not authority to replay an
unchanged production migration. The bundle records the GitHub connector at
zero replicas with no GitHub egress. The retained authority contract keeps
the Kubernetes observer from a cluster-wide role and binding to one exact
namespace-local `Role` and `RoleBinding` in each of `starbase-system`,
`starbase-connectors`, and `starbase-execution`. Each role may only list pods,
Deployments, DaemonSets, and StatefulSets in its own namespace. The promotion
generator rejects missing pairs, altered rules or subjects, unexpected
namespace-local RBAC, and every `ClusterRole` or `ClusterRoleBinding`.

Core, the Kubernetes connector, and migrations are rendered for review but
remain blocked from activation by the Phase 4A overlay and the deployment
plan's runtime, identity, data, recovery, observability, and capacity gates.

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
