# Starbase Phase 4A activation evidence

This ledger records evidence and decisions for the staged Kubani Phase 4A
activation. It complements
[`starbase-phase4a-preflight.md`](starbase-phase4a-preflight.md) and
[`postgresql-backup-recovery.md`](../operations/postgresql-backup-recovery.md).

## Gate status

| Gate | State | Evidence or blocker |
|---|---|---|
| Off-node encrypted backup | passed | Stage 1 evidence below |
| Trusted promotion regeneration | accepted bounded deferral | Starbase ADR 0009 accepts exact owner-local regeneration as non-independent evidence until its first trigger or 2026-11-30; Starbase PR #18 merged as `68ac908f` on `2026-08-25` |
| Isolated restore | passed | corrected exact Job `postgres-backup-restore-verification-v1-e4deaaf32203` restored the current encrypted backup into an isolated PostgreSQL instance |
| Fail-closed foundation | passed | dedicated Flux Kustomization admitted the inert foundation only after the corrected restore completed |
| SOPS credentials | locally verified; not yet live-verified | five independently scoped encrypted Secret objects decrypt with the recovered off-cluster identity; merge and post-reconcile verification remain separately authorized |
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

## Stage 2 failed attempt and correction candidate

The merged revision `main@sha1:d5356873bc6b6e7e7247da1d1387afd63c89125d`
was observed by Flux before the verifier started. At `2026-08-25T01:09:08Z`,
the exact Job `postgres-backup-restore-verification-v1-945bf4f5b132` created one
pod on `rig0`. It exited once with code 1, zero restarts, and zero retries at
`2026-08-25T01:09:09Z`. The encrypted backup checksum and stream-integrity
check passed. PostgreSQL initialization did not begin because direct Kubernetes
`command` replacement bypassed the pinned Bitnami image entrypoint, leaving UID
1001 absent from the container identity database. The retained sanitized error
was `initdb: could not look up effective user ID 1001: user does not exist`.

The failure did not connect to or mutate source PostgreSQL. PostgreSQL remained
Ready on `strix` with zero restarts. All Starbase Deployments remained at zero,
all database bootstrap and migration Jobs remained suspended, and the ordinary
`apps`, `databases`, `flux-system`, and `infrastructure` Kustomizations remained
Ready. The dedicated `starbase-foundation` Kustomization became NotReady with
`HealthCheckFailed`, which is the intended fail-closed result. At the
`2026-08-25T01:10:28Z` checkpoint all four nodes were Ready and pressure-free;
`asio` used 4% CPU / 29% memory, `strix` 5% / 21%, and `rig0` 0% / 19%.

The proposed correction preserves the image's reviewed entrypoint, passes the
verifier script as arguments, and adds an explicit runtime-identity guard before
`initdb`. The content-bound replacement Job is
`postgres-backup-restore-verification-v1-e4deaaf32203`. Local execution against
the exact pinned image confirmed that the preserved entrypoint exposes UID 1001
through NSS and successfully initializes PostgreSQL. The live failed Job is the
evidence for the bypassed Kubernetes path; the local Podman runtime supplies
its own user mapping and cannot reproduce that missing-identity condition.
Merging the correction would create a new, unsuspended restore Job and therefore
requires a fresh cluster checkpoint and separate authorization; preparing or
reviewing this change does not authorize the rerun.

## Stage 2 successful corrected exercise

Al McKay merged the reviewed correction at
`main@sha1:aa892945e23c36d24101a22eae5a9e408e4193de` on
`2026-08-25T02:51:58Z`. Flux applied that exact revision. The content-bound Job
`postgres-backup-restore-verification-v1-e4deaaf32203` started on `rig0` at
`2026-08-25T02:52:42Z` and completed at `2026-08-25T02:52:49Z`. It created one
pod, exited 0, and had zero retries and restarts.

The Job selected the scheduled `2026-08-25T02:00:00Z` encrypted copy. Its
checksum and decrypt/gzip integrity checks passed, the isolated Unix-socket-only
PostgreSQL restore completed, and the catalog invariants reported 10 databases,
25 roles, and 345 Authentik application tables. The backup claim was mounted
read-only. The restore pod was selected by the namespace-wide DNS-only egress
policy and by no PostgreSQL allow policy, so it had no network path to source
PostgreSQL. From merge to verified completion was 51 seconds, within the
development two-hour RTO objective; the backup was 53 minutes old at completion,
within the 24-hour RPO objective.

Afterward, all Flux Kustomizations were Ready at the merged revision. PostgreSQL
remained 2/2 Ready on `strix` with zero restarts. All nodes were Ready and free
of memory, disk, and PID pressure. `rig0` remained at 0% CPU and 19% memory with
972,268,703,744 filesystem bytes available at `2026-08-25T02:53:33Z`. Core and
both connectors stayed at zero replicas; both migration Jobs stayed suspended;
no failed or pending pod remained. The old and new backup claims remained Bound.

### Retained `psql` output deviation

The successful restore pipeline used `psql --quiet`, but successful dump replay
still emitted non-secret `NOTICE` messages naming known databases and roles plus
sequence-result rows. Review found no credential, password hash, or plaintext
SQL in the retained log. The output did not affect restore integrity, source
isolation, or authorization, but it was noisier than this ledger's intended
minimal evidence standard.

Retain the Job and log as truthful exercise evidence; do not delete them to make
the record cleaner. Al McKay owns a normal-priority follow-up for the next
separately authorized restore-script revision and exercise: suppress successful
replay stdout and `NOTICE` output while preserving actionable stderr, add an
allowlist regression test for retained lines, and verify the resulting
content-named Job. The current unsuspended script must not be edited solely for
log cosmetics because a digest change would create and run a new Job without a
new restore authorization.

## Stage 3 encrypted-credential candidate

The next reviewed tranche adds exactly five SOPS-encrypted, workload-scoped
Secrets for database bootstrap, core runtime, gateway runtime, core migration,
and gateway migration. PostgreSQL TLS is disabled in the current HelmRelease,
so database URLs explicitly use `sslmode=disable` within the existing exact
NetworkPolicy boundary. Core and connectors remain at zero replicas and all
database Jobs remain suspended. Merge would provision credentials but would not
use them; it requires a fresh checkpoint, exact-revision authorization, SOPS
reconciliation evidence, and confirmation that no workload started.

Each file is encrypted to the repository's existing age recipient, and the
current Flux Kustomization successfully decrypts existing files for that same
recipient. On `2026-08-25`, the owner-protected age identity already retained
on `rig0` was copied to the operator workstation's gitignored `age.key` path
with mode `0600`. The identity's derived public recipient exactly matched
`.sops.yaml`, and all five candidate files decrypted locally to a discarded
output stream. No private key or decrypted Secret value was printed, retained
as evidence, committed, uploaded, or copied into this branch. The temporary
transfer copy was removed after installation, while the original recovery copy
on `rig0` was preserved.

This closes the off-cluster recoverability and local-ciphertext merge gate. It
does not prove live Flux application, authorize merge, or authorize credential
use. Merge still requires a fresh health and capacity checkpoint,
exact-revision authorization, SOPS reconciliation evidence, and confirmation
that no workload started. Do not retrieve or publish the live `sops-age`
Secret merely to repeat this verification.
