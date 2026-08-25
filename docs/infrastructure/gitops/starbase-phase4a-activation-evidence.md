# Starbase Phase 4A activation evidence

This ledger records evidence and decisions for the staged Kubani Phase 4A
activation. It complements
[`starbase-phase4a-preflight.md`](starbase-phase4a-preflight.md) and
[`postgresql-backup-recovery.md`](../operations/postgresql-backup-recovery.md).

## Gate status

| Gate | State | Evidence or blocker |
|---|---|---|
| Off-node encrypted backup | passed | Stage 1 evidence below |
| Trusted promotion regeneration | accepted bounded deferral | Starbase ADR 0009 accepts exact owner-local regeneration as non-independent evidence until its first trigger or 2026-11-30; Starbase PR #18 must merge first |
| Isolated restore | pending reviewed merge | exact Job `postgres-backup-restore-verification-v1-945bf4f5b132` |
| Fail-closed foundation | pending isolated restore | dedicated Flux Kustomization cannot become Ready until its exact restore health check passes |
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

Al McKay accepted Starbase ADR 0009 on 2026-08-24 to defer ADR 0008's separate
trusted private-source regeneration gate during bounded single-owner homelab
pre-production. The accepted decision is being versioned in
[Starbase PR #18](https://github.com/X-McKay/Starbase/pull/18), which must merge
before this activation PR. Local deterministic regeneration from exact clean
evidence revision `c966518b8c82e755664faa9c37bfd5854089f8a2` and source
revision `ab25087ec856be89d2e00f69f7d230d71cf5301a` verified the changed lock and
left the rendered workload bytes unchanged. This is owner-controlled,
non-independent evidence; ordinary CI does not authenticate the private source.

The original GitHub App, Linux toolchain, credential-isolation, fork-failure,
and revocation gate becomes mandatory again before ADR 0009's first trigger or
2026-11-30 expiry. The deferral does not waive any restore, cluster-health,
capacity, GitOps, rollback, identity, migration, or provider-authority gate.

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

The Stage 2 change places the exact restore health check on the dedicated
`starbase-foundation` Kustomization. Its matching activation-wave label and
generation check first require the databases Kustomization to apply the
unsuspended Job. The foundation may then apply its inert resources, but it
cannot become Ready or admit a later Starbase activation stage unless the
restore passes. A 25-minute Flux timeout covers the Job's 20-minute deadline
with a controller cushion. A failed restore does not freeze reconciliation of
unrelated Authentik, monitoring, vLLM, or Temporal resources. No Secret,
Authentik mutation, Certificate, Ingress, database bootstrap, migration, or
running Starbase Deployment is part of this tranche.

Repository validation before review:

- the full local inventory, secret scans, six Kustomize builds, 33 promotion,
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
- the databases Flux Kustomization applying the unsuspended Job while remaining
  independent of its result;
- the `starbase-foundation` Flux Kustomization applying only inert resources
  and becoming Ready only after exact Job completion;
- the ordinary apps Kustomization remaining Ready and able to reconcile;
- all Starbase Deployments remaining at zero and all Starbase Jobs remaining
  suspended; and
- no Authentik, Certificate, Ingress, DNS, Secret, or database mutation from
  the foundation.

Any failed or ambiguous check is a stop. Preserve the Job and logs and revert
the complete activation commit to resuspend the verifier, remove the health
check, and reconcile normal desired state. Re-suspending only the Job while
leaving the health check in place is not rollback: the suspended Job can never
complete, so `starbase-foundation` remains NotReady indefinitely. That partial
state is isolated from the ordinary apps tier, but no later Starbase gate may
advance from it.
