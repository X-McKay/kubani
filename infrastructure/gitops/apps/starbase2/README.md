# Starbase2 deployment preparation

Status: **inactive draft; not a deployable application release**.

This directory starts one PR for all Kubani changes needed by the fresh
Starbase2 installation. It is absent from the active apps aggregate. The sibling
[Flux manifest](../../flux-system/starbase2-kustomization.yaml) is also absent
from the Flux root and has `suspend: true`. Merging this preparation alone would
not create cluster resources. Do not manually apply it as a deployment shortcut.

## Prepared resources

- `starbase2-prod` namespace with restricted pod admission and ownership labels.
- Service account with automatic token mounting disabled and no RBAC grants.
- Default-deny ingress and egress limited to DNS, PostgreSQL and Temporal.
- Separate installation-owned ingress allowances on PostgreSQL TCP 5432 and
  the Temporal frontend TCP 7233. Existing dependency policies are untouched.

These five resources are extracted from Starbase2's deployment renderer after
the September 6 target preflight. The dependency rules passed server-side
dry-run; this does not demonstrate connectivity from a future workload.
No workload, image reference, Secret, migration Job or provisioning effect is
included. The prepared Flux owner disables pruning and orphans resources on
deletion, so a later suspension/removal cannot accidentally cascade into data
deletion. Permanent cleanup remains a separate, explicitly reviewed procedure.

## Complete in this same PR before activation

| Gate | Owner | Completion evidence |
|---|---|---|
| Image publication | Starbase2 release | Authorized publication, registry-resolved immutable Core/worker digests, successful node pulls |
| Placement | Operator + Starbase2 release | Native amd64 qualification on general nodes, or an explicit qualified arm64 placement exception; use topology labels |
| Exact release | Starbase2 release | Regenerated bundle, source/build provenance and checksums matching the published images; add stopped workload with `replicas: 0`, `accept_work: false` |
| Credentials | Kubani operator | SOPS-encrypted application/worker and pull credentials; migration owner identity separate from runtime |
| Fresh data | Kubani operator + Starbase2 | Ownership-checked new database/roles and Temporal namespace, one-shot migration outside automatic Flux reconciliation, runtime grants verified |
| Production recovery | Platform owner | Resolve the shared backup scope below and retain an isolated restore with measured recovery; record the accepted recovery objectives |
| Activation | Operator | Review exact diff, then deliberately wire the Flux owner, enable reconciliation, verify stopped resources, start closed, verify bounded work and recovery before admitting duties |

Keep this PR draft until its reviewed scope and gates are complete. Add follow-up
commits to this branch; do not split prerequisites into ad hoc deployment PRs.
Update the inactivity tests when activation is deliberately approved, replacing
them with tests of the stopped workload and its activation controls.

The current PostgreSQL [backup runbook](../../../../docs/infrastructure/operations/postgresql-backup-recovery.md)
describes development recovery, no PITR/HA, and a backup key coupled to the
administrator password. Production needs an independently recoverable key and
an isolated restore. A shared backup upgrade affects other applications and is
not included in this preparation; the platform owner must resolve its scope
before Starbase2 starts. No production recovery claim is made here.

## Installation and recovery procedure

Starbase2 owns executable setup, provisioning, migration, stop, rollback,
restore and permanent cleanup in its
[deployment playbook](https://github.com/X-McKay/Starbase2/blob/c5f38fd/docs/deployment.md).
At release freeze, pin this link and the rendered bundle to the final qualified
revision. Local SQLite records are development-only and are not imported.

The first workload is one private Core/worker pod using PostgreSQL and Temporal.
It has no public ingress or Kubernetes API identity. Live GitHub/cluster duties,
inference, repair sandboxing and graph memory are disabled for this release.
Temporal namespace isolation is not worker authentication; Web OIDC does not
authenticate gRPC clients. The private PostgreSQL link has no verified TLS.

To stop after a future activation, close submissions and reconcile the owning
Deployment to zero through this PR's GitOps path. Retain the DB, histories,
evidence and previous image digests. Rollback does not rewind data or histories;
restore requires reconciliation before accepting work. Permanent cleanup must
detach GitOps ownership, preserve verified backups and check installation labels
before removing data or either dependency policy. While this draft is inactive,
closing it requires no cluster teardown.

## Validation

Run `just test-starbase2-preparation`, `just validate-local`, and
`just pre-push-check`. The tests render the prepared boundary, enforce narrow
dependency access and confirm that active roots contain no Starbase2 resources.
The same focused test runs in GitHub PR CI.
