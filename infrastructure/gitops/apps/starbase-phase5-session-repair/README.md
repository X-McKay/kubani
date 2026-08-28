# Starbase Phase 5 pre-production session repair

Date: 2026-08-28
Owner and approving authority: Al McKay
Status: prepared under the bounded Starbase pre-production acceleration cycle

## Purpose and scope

RC5 reconciled successfully but its first live Authentik callback failed closed
with HTTP 503 `session-unavailable`. The absent refresh credential was encoded
as SQL `NULL` against the existing non-null ciphertext column. Starbase main
revision `1bd99e93d3c1467b14b479086fd14a4cf5f0c2a5` contains the minimal repair
and through-the-callback PostgreSQL regression coverage.

This overlay inherits the complete RC5 Phase 5 preview and changes only the
core container image. The RC5 web, fixture, connector, and suspended migrator
images remain byte-for-byte pinned by the accepted promotion lock. Replicas,
RBAC, Secret references, NetworkPolicies, resource limits, placement,
configuration, and migration state do not change. Both live provider
connectors remain at zero.

## Temporary artifact exception

GitHub Actions run 33216431942 completed all nine substantive source jobs, but
all sixteen container-matrix jobs failed before runner assignment with no
runner, steps, or logs. The ordinary release workflow consequently cannot pass
its exact-CI precondition. Under the owner-authorized acceleration cycle, the
single changed core image was instead built locally from a clean exact main
checkout using the repository's digest-pinned Dockerfile for `linux/amd64`.

The image carries source revision `1bd99e93d3c1467b14b479086fd14a4cf5f0c2a5`
and pre-production version `preprod-1bd99e93`. Pinned Trivy 0.70.0 reported zero
HIGH/CRITICAL vulnerabilities and zero secret findings; a license inventory was
also retained locally. Because the repository owner does not currently have a
working registry publication path, the exact Docker archive is preloaded into
the K3s containerd stores on both preferred runtime nodes (`asio` and `strix`).
The workload keeps the immutable reference
`sha256:3194aae4c5728ef9814a3d3307fbceecc6c886f1c412c2b431e78fd3971dff17`;
the overlay does not introduce a mutable tag or weaken the inherited pull
policy. Both nodes must resolve that exact digest through the CRI before merge.

Retained owner-only evidence:

- Docker archive SHA-256:
  `8b5411e7afe59ae089153104692af00cd12623a940a7f82f1ddb96ffc31fd23a`
- Imported Docker manifest and workload digest:
  `3194aae4c5728ef9814a3d3307fbceecc6c886f1c412c2b431e78fd3971dff17`
- OCI config SHA-256:
  `12721709e58071f43c8b81305f556b7799bcab5b12b873df98efc54e84fceb2d`
- Trivy security evidence SHA-256:
  `99e69ba9fb65a57aca84eabd246a009537781de602b202a4171ab391ff678aac`
- Trivy license evidence SHA-256:
  `a897169f495b11e73d01ab54d0de2b563abbab7394a9b7a4323bd4874d5cb4a5`

The initial local image-index value did not survive Docker-archive import as a
CRI-resolvable repository digest and was rejected before rollout. The digest
above is the imported Docker manifest digest observed from containerd. An exact
repository-digest alias was then created on each node and independently
resolved through `crictl`; both nodes reported config ID
`sha256:12721709e58071f43c8b81305f556b7799bcab5b12b873df98efc54e84fceb2d`,
source revision `1bd99e93d3c1467b14b479086fd14a4cf5f0c2a5`, `linux/amd64`, and
non-root user `65532:65532`.

This image is not a formal release candidate and makes no production,
signature, SBOM-attestation, or SLSA-provenance claim. It may be used only for
this reversible, observation-only homelab preview. A signed successor produced
by the ordinary release workflow must replace it before the acceleration cycle
expires or any production transition begins.

## Activation, verification, and rollback

Merge changes the Starbase Flux path to this overlay and lets Flux reconcile
naturally. Immediately before merge, require healthy nodes and Flux, fresh
capacity on `asio` and `strix`, the archive imported on both nodes, exact CRI
digest resolution, suspended migration Jobs, zero live provider replicas,
public readiness, and unauthenticated API denial. Repeat the health, capacity,
identity, migration, provider, readiness, and denial checks after Flux applies
the merge. Remove only the temporary transferred archives after a verified
import; retain the imported image during the bounded acceptance and rollback
window.

Acceptance additionally requires an Authentik session to complete login without
a second prompt, authenticated session/snapshot/SSE behavior, logout
invalidation, durable synthetic observations, stable PostgreSQL state, zero
unexpected restarts, and one successful Osprey run. Any digest mismatch,
migration start, authorization bypass, provider access, database anomaly,
unhealthy node, failed reconciliation, or lost observation stops the rollout.

Rollback remains the prepared
`starbase-phase5-rc4-runtime-rollback` overlay or exact Git reversion to parent
revision `60a0c7267a3e28141fc469cecf18686f2e1a7a63`, selected according to the
existing RC5 runbook so completed migrations are never reintroduced as runnable
Jobs.
