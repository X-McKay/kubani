# Starbase Phase 4A activation evidence

This ledger records evidence and decisions for the staged Kubani Phase 4A
activation. It complements
[`starbase-phase4a-preflight.md`](starbase-phase4a-preflight.md) and
[`postgresql-backup-recovery.md`](../operations/postgresql-backup-recovery.md).

## Gate status

| Gate | State | Evidence or blocker |
|---|---|---|
| Off-node encrypted backup | passed | Stage 1 evidence below |
| Isolated restore | pending reviewed merge | exact Job `postgres-backup-restore-verification-v1-945bf4f5b132` |
| Fail-closed foundation | pending isolated restore | dedicated Flux dependency is blocked by the databases health check |
| SOPS credentials | blocked | isolated restore and separate secret review required |
| Authentik integration | blocked | restore, foundation, and owner-path review required |
| Database bootstrap | blocked | restore, secrets, logging review, health, capacity, and go/no-go required |
| Migrations | blocked | successful database bootstrap required |
| Ingress and core | blocked | migrations, identity, network probes, and go/no-go required |
| Kubernetes connector | blocked | healthy core and connector-specific verification required |

## Stage 1: off-node encrypted backup

Authorization: Al McKay approved the bounded Stage 1 operation.

- Flux applied revision before and after:
  `main@sha1:fb9a35f9156f91b57bf1fd28adb982d63a91779b`.
- Manual Job from the reviewed CronJob:
  `database/postgres-backup-rig0-initial-202608242352`.
- Started `2026-08-24T23:54:03Z`; completed `2026-08-24T23:54:16Z`.
- Result: one successful pod, zero retries and restarts, 13 seconds.
- Placement: `rig0`, as required by the retained local volume contract.
- Artifact: `postgres-20260824-235406.sql.gz.enc`, 16,454,048 bytes, with a
  matching SHA-256 sidecar after built-in decrypt-and-gzip validation.
- Claim: `database/postgres-backup-rig0`, Bound to
  `pvc-ae2b39f5-8a1b-41a7-bac9-507fd3f41af0`, 2 GiB,
  `local-path-retain`, reclaim policy `Retain`, node affinity `rig0`.
- The legacy `database/postgres-backup` claim remained Bound and unchanged.
- PostgreSQL stayed Ready on `strix` with zero restarts. All nodes remained
  Ready and free of memory, disk, and PID pressure.
- `rig0` stayed at approximately 0% CPU and 19% memory; available filesystem
  capacity after the copy was 972,294,766,592 bytes.
- The expected CronJob-controller `UnexpectedJob` warning for a manually
  instantiated child was observed; the controller adopted the successful Job.
  The unrelated failed scheduled Job from 2026-06-14 predates this exercise.

Conclusion: the fresh encrypted copy is eligible for isolated restore testing.
It is not yet recovery-verified and does not authorize database bootstrap.

## Stage 2 pre-change checkpoint

Read-only observations at `2026-08-25T00:01:42Z`:

- Kubernetes API and etcd readiness passed.
- `asio`, `rig0`, `sparky`, and `strix` were Ready and free of memory, disk,
  and PID pressure.
- Node use was: `asio` 3% CPU / 29% memory, `strix` 4% / 21%, `rig0` 0% /
  19%, and `sparky` 1% / 56%.
- All Flux sources, Helm releases, and Kustomizations were Ready at
  `main@sha1:fb9a35f9`.
- PostgreSQL was Ready. No active pod was outside Running or Succeeded state.
- The exact restore verifier remained suspended and had not run.

The Stage 2 change places the inert Starbase foundation behind an exact Flux
health check for that verifier. If the restore is incomplete or fails, the
dedicated `starbase-foundation` Kustomization cannot apply it. The matching
activation-wave label and generation check prevent a stale Ready status from
admitting the new layer. No Secret, Authentik mutation, Certificate, Ingress,
database bootstrap, migration, or running Starbase Deployment is part of this
tranche.

Repository validation before review:

- the full local inventory, secret scans, six Kustomize builds, 32 promotion,
  dependency, and recovery tests, and required hook checks passed;
- changed-file YAML, secret, private-key, large-file, conflict, and policy
  hooks passed;
- the 45-resource foundation passed strict Kubernetes 1.34 schema validation;
- the rendered foundation contained zero runnable Starbase workloads;
- cached Trivy checks reported only the documented `export PGPASSWORD`
  ConfigMap heuristic; the script contains a variable name, not a value, and
  independent plaintext-Secret and secret scans passed;
- Actionlint, shell parsing, and `git diff --check` passed; and
- server-side dry-run under Flux's existing field-manager identity accepted
  the databases Kustomization, new foundation Kustomization, restore ConfigMap,
  and exact restore Job without persisting them.

A second read-only cluster checkpoint at `2026-08-25T00:08:11Z` found the API,
all nodes, Flux, and PostgreSQL healthy. `asio` remained at 3% CPU / 29% memory,
`strix` at 4% / 21%, and `rig0` at 0% / 19%. The restore Job remained suspended
with no active, successful, or failed pod. No cluster mutation occurred during
development or validation.

## Stage 2 acceptance evidence to record after merge

Before and after reconciliation, record API/etcd, Flux, PostgreSQL, node
pressure and use, `rig0` filesystem headroom, unexpected pods, and the exact
applied revision. Then record:

- restore Job start, finish, node, pod count, retries, restarts, and duration;
- checksum, decrypt, restore, and catalog-invariant success without names,
  SQL, hashes, or credentials in retained logs;
- confirmation that the backup volume mounted read-only and no connection
  reached the source PostgreSQL service;
- the databases Flux Kustomization becoming Ready only after Job completion;
- the `starbase-foundation` Flux Kustomization then applying the revision;
- all Starbase Deployments remaining at zero and all Starbase Jobs remaining
  suspended; and
- no Authentik, Certificate, Ingress, DNS, Secret, or database mutation from
  the foundation.

Any failed or ambiguous check is a stop. Preserve the Job and logs, revert the
activation commit to resuspend the verifier, reconcile the databases path, and
do not advance the foundation or later gates.
