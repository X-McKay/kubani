# Starbase Phase 5 pre-production core override

Date: 2026-08-31
Owner and approving authority: Al McKay
Status: prepared under the bounded Starbase pre-production acceleration cycle

## Purpose and scope

The first revision of this overlay repaired RC5's failed-closed Authentik
callback and proved one-step browser SSO, durable sessions, authenticated
snapshot/SSE, logout, and denial. Starbase main revision
`b3d54bc875c176dba766682a55d3bb2ca2801819` advances that verified baseline
with the accepted ADR 0011 native Observatory handoff plus the subsequently
merged operational hardening and telemetry. The directory name remains stable
so the existing Flux ownership boundary does not need an otherwise meaningless
path migration; Git history retains the original session-repair artifact.

This overlay still inherits the complete RC5 Phase 5 preview and changes only
the core container image and its descriptive activation annotations. The RC5
web, fixture, connector, and suspended migrator images remain byte-for-byte
pinned by the accepted promotion lock. Replicas, RBAC, Secret references,
NetworkPolicies, resource limits, placement, configuration, and migration
state do not change. Both live provider connectors remain at zero. The rollout
is therefore limited to replacing one observation-only core pod on `asio` or
`strix` while the synthetic fixture remains the only source.

## Temporary artifact exception

GitHub-hosted Actions are currently blocked before any step starts because the
account payment or spending limit prevents runner assignment. The ordinary
release workflow consequently cannot pass its exact-CI precondition. Under the
owner-authorized acceleration cycle, the single changed core image was instead
built locally from a clean exact main checkout using the repository's
digest-pinned Dockerfile for `linux/amd64` after exact-head source, race,
integration, deployment, image, security, Godot, and macOS package assurance.

The image carries source revision `b3d54bc875c176dba766682a55d3bb2ca2801819`
and pre-production version `preprod-b3d54bc8`. Pinned Trivy 0.70.0 reported
zero fixed HIGH/CRITICAL vulnerabilities and zero secret findings; a license
inventory was also retained locally. Because the repository owner does not
currently have a working normal release path, the exact Docker archive is
preloaded into the K3s containerd stores on both preferred runtime nodes
(`asio` and `strix`). The workload keeps the immutable reference
`sha256:68385b100f24f5a28738799bc3712d6322226760a75ded14c947afbc36533345`;
the overlay does not introduce a mutable tag or weaken the inherited pull
policy. Both nodes must resolve that exact digest through the CRI before merge.

Retained owner-only evidence:

- Docker archive SHA-256:
  `69cb6f63ad791f4d9b9e9bee1f46856fa7a385390897e9d4c85f9f3179c09275`
- Imported Docker manifest and workload digest:
  `68385b100f24f5a28738799bc3712d6322226760a75ded14c947afbc36533345`
- OCI config SHA-256:
  `f2d5ff788795bbdc6dcaa4022ae814af64330566bef06fb6b7a3aac6c99c24cb`
- Trivy security evidence SHA-256:
  `2a8e0838b826b293d9a390853dc55d4d2d69eb8a70c63de5d177e2b8eb37f1eb`
- Trivy license evidence SHA-256:
  `fd988fa29a9d0b93c8b1f377855d702e81e3b53e85ff61b732b747018bc268a6`

The initial local image-index value did not survive Docker-archive import as a
CRI-resolvable repository digest and was rejected before rollout. The digest
above is the imported Docker manifest digest observed from containerd. An exact
repository-digest alias was then created on each node and independently
resolved through `crictl`; both nodes reported config ID
`sha256:f2d5ff788795bbdc6dcaa4022ae814af64330566bef06fb6b7a3aac6c99c24cb`,
source revision `b3d54bc875c176dba766682a55d3bb2ca2801819`, `linux/amd64`, and
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

Acceptance additionally requires the packaged Observatory to complete its
browser-mediated Authentik handoff, authenticated snapshot and SSE behavior,
expiry or revocation reauthentication, truthful fallback labeling, and
credential-residue checks. Browser login/logout, durable synthetic
observations, stable PostgreSQL state, zero unexpected restarts, and an
out-of-band Osprey or Lifeboat check remain required. Any digest mismatch,
migration start, authorization bypass, provider access, database anomaly,
unhealthy node, failed reconciliation, or lost observation stops the rollout.

Rollback remains the prepared
`starbase-phase5-rc4-runtime-rollback` overlay or exact Git reversion to parent
revision `60a0c7267a3e28141fc469cecf18686f2e1a7a63`, selected according to the
existing RC5 runbook so completed migrations are never reintroduced as runnable
Jobs.
