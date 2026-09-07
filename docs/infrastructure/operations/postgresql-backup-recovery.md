# PostgreSQL rig0 backup and isolated-restore runbook

Last reviewed: 2026-08-24

Last successful exercise: 2026-08-25; corrected exact verifier restored the
current encrypted backup into an isolated PostgreSQL instance

Last attempted exercise: 2026-08-25; succeeded at merged revision
`aa892945e23c36d24101a22eae5a9e408e4193de`

Owner and stop authority: Al McKay

Status: development recovery exercise passed; encrypted credentials, bootstrap,
migrations, and workload activation remain separately gated

## Purpose and scope

This runbook creates and verifies the development recovery copy required before
any application may bootstrap databases on Kubani. The existing PostgreSQL instance
and its Longhorn volume run on `strix`; the recovery copy is a retained local
volume pinned to `rig0`.

This procedure covers a daily logical `pg_dumpall`, encrypted backup retention,
integrity verification, and restoration into an isolated ephemeral PostgreSQL
instance. It does not provide point-in-time recovery, PostgreSQL high
availability, protection from simultaneous `strix` and `rig0` loss, or a
production backup architecture.

## Recovery objectives and accepted development boundary

- Schedule and RPO objective: one successful copy every 24 hours at 02:00 UTC.
- Retention: the 14 most recent successful copies.
- Initial RTO objective: two hours from operator start to a verified logical
  restore. This remains unverified until the first exercise completes.
- Storage: a 2 GiB `local-path-retain` claim late-bound to `rig0`.
- Placement: backup and restore-verification pods require hostname `rig0`.
- Source impact: one bounded `pg_dumpall` connection with 50m CPU / 64 MiB
  memory requested and a 15-minute Job deadline.

At the 2026-08-24 preflight, the logical dump was 16,482,390 bytes and three
retained copies used approximately 48 MiB. `rig0` was Ready, had no pressure,
used 0% measured CPU and 19% memory, and reported 972,353,957,888 bytes of root
filesystem headroom. The 2 GiB request is therefore conservative, but these
measurements expire before every activation or restore exercise.

The copy is encrypted in-flight before it reaches `rig0` with AES-256-CBC,
PBKDF2-SHA256, a random salt, and 200,000 iterations. To avoid introducing a
second recovery secret during development, the current PostgreSQL administrator
credential is the encryption input. That value is passed only through the pod
environment and never appears in a command argument or log. This creates an
intentional coupling: credential rotation must retain access to the prior
SOPS-encrypted credential until every backup encrypted with it expires. Before
production, replace this with an independently recoverable backup key or a
managed backup system and re-exercise recovery.

## Desired-state controls

- `local-path-retain` preserves the provisioned volume if its claim is removed.
- The old `postgres-backup` claim on `strix` remains intact until the removal
  condition below is met.
- The active CronJob writes only encrypted `.sql.gz.enc` files plus SHA-256
  sidecars to `/backups/postgresql` on `rig0`.
- Writes use a partial file, decrypt-and-gzip validation, an atomic rename, and
  then a checksum sidecar. Pruning removes a backup and its checksum together.
- The isolated restore Job is content-digest named, has zero retries, cannot
  reach PostgreSQL, mounts the backup claim read-only, and is committed with
  `spec.suspend: true`.
- Both pods use a dedicated unprivileged ServiceAccount and neither mounts a
  Kubernetes service-account token.

The restore verifier initializes PostgreSQL only in a bounded `emptyDir` under
a runtime-unique bootstrap superuser, decrypts and restores the newest copy over
a Unix socket with TCP disabled, and checks that the known `authentik` database,
its user tables, and the restored `postgres` role exist. The unique bootstrap
identity prevents `pg_dumpall --clean` from attempting to drop the current
restore session. The verifier never writes to the source database or the backup
volume.

## Preconditions

Record UTC time, operator, exact Git revision, and results without retaining
secret values.

1. Kubernetes API and etcd are Ready.
2. All Flux Kustomizations are Ready at the intended main revision.
3. PostgreSQL is Ready with no unexplained restarts, lock pressure, or storage
   warning.
4. `strix` and `rig0` are Ready and have no memory, disk, or PID pressure.
5. Fresh `kubectl top nodes` and kubelet filesystem evidence leave at least 2
   GiB plus normal operating headroom on `rig0`.
6. The existing local backup Job has a recent successful copy and is preserved
   until this exercise finishes.
7. The `postgresql-credentials` Secret reference exists. Do not read or print
   its value.
8. The rendered CronJob and verifier match the reviewed commit, all images use
   immutable digests, and repository validation is green.
9. An external observer and the ordinary Kubani administrative path remain
   available while the Jobs run.

Stop before mutation if any precondition fails or evidence is stale.

## Temporary freshness control while monitoring is disabled

Prometheus and Grafana are intentionally scaled to zero. Until independent
backup monitoring returns, Al McKay must perform this read-only check at least
once every 48 hours:

1. Inspect `CronJob/postgres-backup` in `database` and confirm its
   `lastSuccessfulTime` is less than 48 hours old.
2. List Jobs owned by that exact CronJob, resolve the newest successful Job, and
   inspect only that Job's status and logs.
3. Confirm the log contains `Encrypted backup and checksum written` and that
   the newest listed `postgres-YYYYMMDD-HHMMSS.sql.gz.enc` filename is less than
   48 hours old. The built-in decrypt-and-gzip proof must have completed before
   this line can be emitted.

Missing, ambiguous, or older evidence makes the backup **stale**. Block database
bootstrap and restore exercises, preserve the failed Job and existing copies,
and investigate without forcing a replacement run. Creating a transient backup
Job still requires the separate Stage 1 approval below. This temporary manual
control expires only after backup-completion and age monitoring is restored and
verified.

## Stage 1: produce the first rig0 copy

After the GitOps change is merged and Flux is healthy, the next scheduled run
will create the retained volume on `rig0`. If an earlier first copy is approved,
create one bounded Job from the reviewed CronJob and record its exact name:

```bash
kubectl create job -n database --from=cronjob/postgres-backup \
  postgres-backup-rig0-initial-YYYYMMDDHHMM
```

This is an explicitly audited transient operation, not desired-state drift; the
CronJob remains the owning template. Do not retry after a timeout until the Job
and backup directory are reconciled.

Verify:

1. The Job schedules only on `rig0` and completes once within 15 minutes.
2. PostgreSQL remains Ready and latency, locks, restarts, and storage stay
   normal.
3. The claim is Bound to a `local-path-retain` PV whose node affinity is
   `rig0` and whose reclaim policy is `Retain`.
4. Logs state only the encrypted size and filenames; no credential or SQL
   content appears.
5. One non-empty encrypted file and matching checksum exist, and the Job's
   built-in decrypt-and-gzip check succeeded.
6. `rig0` remains Ready and pressure-free with acceptable disk, CPU, and memory
   headroom.

## Stage 2: verify an isolated restore

Only after Stage 1 passes, submit a narrowly reviewed GitOps patch changing the
exact content-named restore Job from `suspend: true` to `false`. Do not recreate
the Job under a floating name or execute the script from an unreviewed local
copy.

The same review may add inert downstream resources when a dedicated Flux
health check makes successful restore completion an automatic prerequisite for
every later activation stage.
Those resources must be incapable of starting workloads or mutating identity,
databases, credentials, ingress, certificates, or DNS. Combining repository
changes does not combine operational gates: monitor and verify the restore
before accepting any downstream reconciliation.

Keep this restore health check isolated from shared platform readiness. A
failure must stop dependent application activation without preventing unrelated
Authentik, Temporal, monitoring, or other application reconciliation. Set the Flux health
timeout above the Job's 20-minute deadline.

Verify:

1. The verifier schedules only on `rig0` and the backup claim remains read-only.
2. It completes once within 20 minutes with zero retry.
3. Its logs report checksum success, isolated restore completion, and positive
   database/role counts without names, SQL, hashes, or credentials.
4. No connection reaches the source PostgreSQL service from the verifier.
5. Source PostgreSQL, Flux, `strix`, and `rig0` remain healthy.
6. Record elapsed restore time and compare it with the two-hour RTO objective.

Keep the completed Job as immutable evidence until a reviewed follow-up removes
it. It intentionally has no TTL, because automatic deletion would cause Flux to
recreate and rerun an unsuspended desired Job.

### Successful replay-log limitation

The 2026-08-25 successful exercise retained non-secret database and role names
from PostgreSQL `NOTICE` messages and sequence-result rows from successful dump
replay. It retained no credential, password hash, or plaintext SQL. This does
not invalidate the restore result, but it exceeds the intended minimal evidence
surface.

Do not edit the current unsuspended verifier merely to clean its logs: changing
the content digest creates a new Job and therefore requires a new restore
authorization. Al McKay owns the normal-priority correction at the next
authorized verifier revision. Suppress successful replay stdout and `NOTICE`
messages while preserving stderr failures, add a regression test that allows
only the expected summary lines, and re-exercise the resulting exact Job before
claiming the limitation resolved.

The original Stage 1 execution evidence was recorded with the Starbase
activation and was removed with its decommission on 2026-09-06.

Rollback is the complete activation-commit revert. Merely re-suspending the Job
while retaining a dependent health check leaves that Kustomization NotReady
forever because a suspended Job cannot complete. Preserve the failed Job and
logs before reverting.

## Stop and abort conditions

Stop without retrying when:

- Flux, Kubernetes API, PostgreSQL, `strix`, or `rig0` becomes unhealthy;
- `rig0` develops disk, memory, or PID pressure;
- the pod schedules on another node;
- a dump, encryption, checksum, decryption, gzip, initialization, restore, or
  catalog check fails;
- a Job reaches its deadline, starts a second pod unexpectedly, or has an
  ambiguous result;
- plaintext SQL, a credential, or password hash appears in storage or retained
  logs; or
- the reviewed revision, target, identity, or recovery path changes.

Preserve the failed Job, logs, and encrypted partial-state metadata needed for
diagnosis. Do not print or copy backup contents into an issue or PR.

## Rollback and forward recovery

Before the first successful `rig0` copy, revert the CronJob to the old
`postgres-backup` claim. Preserve the new claim and any retained PV until an
operator confirms it contains no required evidence; do not delete storage as a
troubleshooting step.

After a successful copy but before restore verification, revert scheduling to
the old claim if necessary and keep both copies. Fix the verifier forward; do
not weaken checksum, encryption, isolation, or catalog checks to obtain a pass.

After restore verification, continue both recovery paths until at least three
consecutive daily `rig0` backups succeed. Then a separate reviewed change may
remove the old CronJob claim from desired state. Confirm its exact PV and data
retention decision before deletion. A `Retain` PV released from its claim must
be deliberately recovered or erased; it is not automatically garbage.

## Evidence required to close the Phase 4A gate

- exact merged Git revision and Flux applied revision;
- pre/post API, Flux, PostgreSQL, `strix`, and `rig0` health;
- pre/post node use, pressure, and `rig0` filesystem headroom;
- successful backup Job identity, duration, encrypted size, checksum result,
  PVC, PV, node, and reclaim policy;
- successful content-named restore Job identity, duration, catalog invariant
  result, and confirmation of source isolation;
- achieved RPO and RTO;
- retained old-copy status and its removal condition; and
- Al McKay's go/no-go decision for the subsequent database bootstrap.

Until all evidence exists, the Phase 4A recovery gate remains blocked.
