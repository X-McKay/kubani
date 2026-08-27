# Starbase RC4 inert promotion

Date: 2026-08-26

Status: prepared for review; no runtime activation authorized by this change

## Objective and boundary

Promote the published Starbase `0.1.0-rc.4` artifacts into Kubani's
content-bound GitOps bundle while preserving the existing inert Phase 4A
state. This change is a successor-artifact and least-privilege update. It does
not authorize a migration, start a Starbase Deployment, enable the GitHub
connector, or expose a new endpoint.

Flux already references the `starbase-phase4a-foundation` overlay. That overlay
must continue to enforce all of the following after this change:

- Starbase core: zero replicas;
- Kubernetes connector: zero replicas;
- GitHub connector: zero replicas and no GitHub egress;
- core and gateway migrations: suspended; and
- no mutation or sandbox workers deployed by this bundle.

## Immutable release inputs

| Input | Accepted value |
|---|---|
| Release | `0.1.0-rc.4` |
| Starbase source revision | `e35ac44f5cea35b400d73bf94802b1a70e84585a` |
| Merged evidence revision | `bbd7292d8960288600b96a021c298020af40a9d8` |
| Release manifest checksum | `sha256:ce26d2312e8d679d1516b8ed78550e871bd842ad708036d6e41d2cfd4470b817` |
| Rendered bundle checksum | `sha256:e60158421a8566f1ae79d66e289bbff776a2b3b7fc47c7a573baa882a8d7d01e` |
| Target platform | `linux/amd64` |

The release workflow completed successfully and published six digest-pinned
images with signatures, SPDX attestations, SLSA provenance, SBOMs, and zero
gated security findings. The evidence PR's existing exact-head CI completed
25 of 25 checks successfully and was merged without rerunning Actions.

## Authority contraction

RC4 removes the earlier `ClusterRole` and `ClusterRoleBinding`. The successor
bundle contains exactly one `Role` and one `RoleBinding` named
`starbase-kubernetes-observer` in each of:

- `starbase-system`;
- `starbase-connectors`; and
- `starbase-execution`.

The roles may only `list` pods and the `apps` resources Deployments,
DaemonSets, and StatefulSets in their own namespace. Every binding targets the
`starbase-kubernetes-connector` ServiceAccount in `starbase-connectors`.
Kubani's promotion generator now fails closed on missing or duplicate pairs,
altered rules, role references or subjects, unexpected Role identities, and
all cluster-scoped RBAC objects.

## Migration fencing

Migration Job identities now bind both the complete ordered SQL migration set
and the exact migrator image digest. This prevents a successor image with an
unchanged SQL set from colliding with an immutable completed Kubernetes Job.
The RC4 identities are:

- `starbase-core-migrate-e5629c02604b`; and
- `starbase-gateway-migrate-5856bef074b5`.

Both Jobs remain suspended and are absent from the foundation Flux health
checks. The prior RC2 completion evidence remains in the deployment ledger,
but it is not treated as acceptance of the RC4 execution identities. A later
migration activation must authorize one Job at a time, restore its exact health
check, observe completion, and verify schema ownership before proceeding.

## Verification and sign-off gates

Before merge:

1. Reproduce the bundle from clean, distinct evidence and source checkouts.
2. Verify the committed output and lock byte-for-byte.
3. Pass the focused promotion tests and full `validate-local` suite.
4. Render every affected Kustomization and confirm the effective Phase 4A
   replicas and migration suspension, not merely the unpatched base values.
5. Confirm the live API, etcd, Flux, storage, Authentik, PostgreSQL, active
   workloads, and all nodes are healthy.
6. Confirm current CPU, memory, taints, pressure, and allocated requests leave
   adequate headroom on preferred nodes `asio` and `strix`.
7. Review the exact diff and obtain owner sign-off on the immutable revision.

After merge and before any runtime activation:

1. Observe Flux reconcile the exact merged revision.
2. Confirm the old cluster-wide observer role and binding are absent.
3. Confirm all six namespace-local observer objects exist with the exact
   bounded contract.
4. Confirm core and both connectors remain at zero replicas and both new
   migration Jobs remain suspended.
5. Repeat cluster health, capacity, Flux, PostgreSQL, Authentik, and storage
   observations and record the result.

No time-based soak gate starts from this inert promotion. Runtime activation
will be staged separately and will repeat the health and capacity checks before
and after each cohort.

## Pre-merge cluster checkpoint

Read-only checkpoint: `2026-08-27T03:53:26Z`

- Kubernetes API, etcd, and every reported readiness hook passed.
- `asio`, `strix`, `rig0`, and `sparky` were Ready and schedulable. Only
  `sparky` carried the expected GPU taint; it remains outside the preferred
  Starbase placement set.
- Measured use was `asio` 4% CPU / 30% memory and `strix` 5% CPU / 19% memory.
- Allocated requests were `asio` 1,425m CPU / 830 MiB memory and `strix`
  1,555m CPU / 1,144 MiB memory. Both preferred nodes retained ample headroom
  for an inert reconcile and later one-replica staged activation.
- All five Flux Kustomizations were Ready and aligned at
  `main@sha1:c037b78c6c674a35c24d2bff3ec5d6537e8c622f`.
- All non-completed pods were Running and ready; all three Longhorn volumes and
  all 11 Certificates were healthy.
- PostgreSQL, Redis, FalkorDB, Qdrant, the registry, Authentik, Temporal, and
  both active model endpoints passed their read-only probes. The embeddings
  endpoint remained intentionally inactive.
- Existing Starbase core and both connector Deployments were still at zero
  replicas. The RC2 core and gateway migrations and the boundary probe were
  retained as successful completed Jobs.
- The old `starbase-kubani-observer` `ClusterRole` and
  `ClusterRoleBinding` were still present. Their removal and replacement with
  namespace-local authority is an explicit post-reconcile acceptance check.

The repository's Flux validator was corrected to evaluate retained Kubernetes
Jobs by their `Complete` condition rather than a nonexistent `Ready` condition.
The complete read-only `post-reconcile-validate` gate then passed, including
the independent live-service probe suite.

The first independent server-side dry-run correctly refused to take fields
owned by Flux's `kustomize-controller` and correctly rejected raw SOPS metadata
that only exists before Flux decryption. No object was persisted. A scoped
Flux-equivalent server-side dry-run then excluded the seven encrypted Secret
source documents, used the controller field-manager with conflicts forced in
dry-run only, and admitted all 52 remaining resources. Encrypted Secret shape,
ciphertext, recipient, plaintext-leak, and live Flux decryption checks passed
through their dedicated gates.

The post-dry-run checkpoint at `2026-08-27T03:56:14Z` again passed every live
service probe. Flux remained Ready and unchanged at `c037b78...`; all Starbase
Deployments remained at zero. Measured use was `asio` 3% CPU / 30% memory and
`strix` 4% CPU / 19% memory. This confirms the admission exercise was
non-persistent and had no observed capacity impact.

## Failure handling and rollback

Stop before merge if deterministic regeneration, validation, health, capacity,
or review fails. A failed local render has no cluster effect.

If the merged inert promotion fails to reconcile, suspend only the affected
Starbase Kustomization if needed to stop retries, revert the exact promotion
commit through Git, and reconcile the reviewed rollback. Do not manually edit
managed resources as the primary recovery path. Confirm Flux returns Ready and
the prior inert state is restored.

Because this change keeps every runtime replica at zero and migrations
suspended, application data rollback is not expected. If any workload starts
or migration runs unexpectedly, treat that as a stop condition: scale the
affected Starbase workload to zero through the emergency procedure, suspend
the Starbase Kustomization, preserve events and logs, and investigate before
resuming GitOps.

## Deferred items

This promotion does not close the accepted ADR 0009 trusted-regeneration
deferral. The dedicated GitHub App, independent Linux regeneration, and
credential-isolation exercises remain tracked for the first trust-expansion
trigger or the accepted deadline. They do not grant runtime or deployment
authority in the meantime.
