# Authentik 2026.5 upgrade and recovery plan

Last reviewed: 2026-08-25

Last successfully exercised: 2026-08-25 04:52 UTC (isolated restored copy)

Owner and stop authority: Al McKay

Status: exact-fingerprint isolated repair and full upgrade ladder passed; the
versioned `v2` live preflight and isolated restore passed; PR #76 drained the
live server and worker at revision `3de25fa00f6ffadb32f1c3746d090b309ea85ecb`;
live Authentik remains `2025.10.3` with zero sessions; and one consolidated,
sequential live-migration change is under review

## Decision and scope

Kubani will attempt a controlled upgrade from Authentik `2025.10.3` to the
mature supported `2026.5.6` patch. It will not jump directly to the target and
will not adopt the newly released `2026.8.0` line during this change.

The accepted identity architecture does not change: Authentik remains the human
identity provider, workload identity remains Kubernetes-native, and Lifeboat
recovery remains independent of Authentik. This therefore does not require a
new Starbase architecture decision. It does reverse Kubani's operational pin,
so the rationale and recovery contract are recorded here and in the
[infrastructure decision record](../decisions.md).

The [official upgrade guidance](https://docs.goauthentik.io/install-config/upgrade/)
requires a database backup, forbids downgrade as a recovery method, requires
every calendar release to be visited in order, and requires the latest patch in
each release line before advancing. The
[2026.5 release notes](https://docs.goauthentik.io/releases/2026.5/) repeat the
sequential-upgrade and all-outposts requirements. Authentik's
[security policy](https://github.com/goauthentik/authentik/security/policy)
lists only `2026.5.x` and `2026.8.x` as supported on 2026-08-24. `2026.5.6` is
therefore the simplest mature supported target.

## Why the earlier hold can be revisited

The May hold correctly prevented another unbounded direct jump. Its upstream
issues are now closed, but their resolution does not make a direct jump safe:

- [`#21617`](https://github.com/goauthentik/authentik/issues/21617) was a direct
  unsupported `2025.10` to `2026.2` attempt. Maintainers required the missing
  `2025.12` hop.
- [`#19616`](https://github.com/goauthentik/authentik/issues/19616) documented
  `0056_user_roles` lock contention. Several operators succeeded by first
  running `2025.12.0`; a maintainer identified an `AccessExclusiveLock` blocked
  by another connection and recommended eliminating competing connections.

Kubani will therefore include the special `2025.12.0` hop, use one lifecycle
process during live migrations, and prove the exact sequence against a restored
copy before it can touch the live database.

## Observed starting state

The 2026-08-25 04:01 UTC checkpoint recorded:

| Gate | Evidence |
| --- | --- |
| Kubernetes | all four nodes Ready; API reachable |
| Flux | all Kustomizations Ready at `main@sha1:6b97be2d` |
| Authentik | chart/image `2025.10.3`; server 1/1 on `asio`, worker 1/1 on `strix`; built-in healthcheck passed |
| PostgreSQL | 1/1 on `strix`, zero restarts, 164 MiB Authentik database, zero waiting locks |
| Recovery source | `postgres-20260825-020000.sql.gz.enc`, 16,491,408 bytes; checksum and isolated restore passed at 02:52 UTC |
| Restored catalog | 10 databases, 25 roles, 345 application tables |
| Capacity | `asio` 3% CPU / 29% memory; `strix` 5% / 21%; `rig0` 0% / 19% |
| Authentik objects | 5 users, 2 groups, 3 applications, 3 providers, one embedded proxy outpost |

The lineage requires special care. `authentik_version_history` contains
`2024.10.4`, the failed direct `2026.2.2` attempt, and then `2025.10.3`.
`django_migrations` contains 651 applied rows, with rows written during the May
incident. The running `2025.10.3` image nevertheless reports no planned or
pending migrations and is healthy. We do not infer from that health that the
next migration is safe; the rehearsal must start from the current backup and
prove it.

## Exact upgrade ladder

The official chart repository does not publish the latest application patch
for every older line. The chart explicitly supports `global.image.tag` and
`global.image.digest`, so the live changes will pair the latest available chart
with the latest application patch where necessary.

| Hop | Helm chart | Application image | Purpose |
| --- | --- | --- | --- |
| 0 | `2025.10.3` | `2025.10.4` | reach the latest `2025.10.x` patch |
| 1 | `2025.12.0` | `2025.12.0` | execute the known-safe first crossing of migration `0056_user_roles` |
| 2 | `2025.12.4` | `2025.12.6` | reach the latest `2025.12.x` patch before advancing |
| 3 | `2026.2.3` | `2026.2.6` | visit the required `2026.2` release at its latest patch |
| 4 | `2026.5.6` | `2026.5.6` | reach the mature supported target |

Every image is digest-pinned in the rehearsal. Each live hop must resolve and
review the same immutable digest before merge. Kubani has only the embedded
proxy outpost, which runs as part of the core Authentik image; there is no
separate outpost deployment to drift from the server version.

The official Authentik chart index resolves chart `2026.5.6` to application
`2026.5.6` and archive SHA-256
`c14732299b5f54910ac40ff0f9a4b47a2905924b1381ab68b1f20c4eddc40eba`.
The downloaded archive matched that digest, and its templates confirm
`global.image.tag` plus `global.image.digest` produce the reviewed immutable
server and worker image reference. Before review, Rig0's container runtime
contained all five exact lifecycle digests and the pinned PostgreSQL verifier
digest.

## Stage A: isolated current-backup rehearsal

### First rehearsal result

PR #71 merged as revision `406e99161f1e0dc43cd4b0bf3b2e0306e02f4013`
at 2026-08-25 04:23 UTC. Flux applied that exact revision and started
`authentik-upgrade-rehearsal-v1-fedac5358865` on `rig0`. The fixed backup
restored successfully and `2025.10.4` became ready with no pending migrations.
The `2025.12.0` lifecycle then failed at `authentik_core.0056_user_roles`:
creating the user permission role required a null `group_id`, while the
physical `authentik_rbac_role.group_id` column still enforced `NOT NULL`.
The Job terminated `Failed/BackoffLimitExceeded` at 04:32 UTC without starting
any later version or verifier.

The failure was confined to the restored `emptyDir` database. At the terminal
checkpoint all nodes and Flux Kustomizations were Ready, live Authentik was
still 1/1 on `asio` with its worker 1/1 on `strix`, live PostgreSQL was 2/2 on
`strix` with zero waiting locks, and node utilization remained within the
preflight envelope. The failed Job and pod remain evidence and must not be
deleted or retried.

Before v2 can prune the failed resources, the complete Job/Pod YAML, events,
and all three started-container logs were retained on `rig0` under owner-only
directory `/home/al/kubani-evidence/authentik/2026-08-25-pr71/`. Every file is
mode `0600`, owned by `al:al`, and passed `gzip -t`. Integrity digests are:

| File | SHA-256 |
| --- | --- |
| `events.txt.gz` | `27f60693a4f6e3ebcf9a57da89d51198bbf0a7c9d5a27bbb292346d653868127` |
| `job.yaml.gz` | `d4ff0d22f4f6931164b243ef360d8d5848bab4325907d2ca202eb5812438bab5` |
| `pod.yaml.gz` | `813d2508909b477f5fa780e510044bdd04d51e3f18576124f6b41148a64f5427` |
| `restore-postgres.log.gz` | `9a2e32166fe0b7f2262b4aee5a67aa2a8a17e4a9b6daece68738694cafe73ed4` |
| `upgrade-2025-10-4.log.gz` | `ab737dfc1cd975d8a0238cc60ad0dff624604928bca3b2a670574e155c31ab95` |
| `upgrade-2025-12-0.log.gz` | `5112c91b95602a57e7a1b5c1ce0ed055af562a854fc1114757464f6f3ef0d199` |

The bundle may contain operational identifiers and is not copied into Git or
ordinary PR output. Preserve it until the live upgrade is complete and the
post-upgrade evidence has been accepted.

Read-only checks identified an exact history/schema mismatch in both the
backup and live database:

- RBAC `0008`, `0009`, and `0010` are recorded as applied while core `0056` is
  not;
- `authentik_rbac_role.group_id` exists and is non-nullable even though `0008`
  should have made it nullable;
- the obsolete `authentik_rbac_initialpermissions.mode` column exists even
  though `0009` should have removed it; its table contains zero rows;
- `authentik_core_user_roles` does not yet exist, consistent with `0056` not
  being applied; and
- there is one Role row, no duplicate Role names, and no waiting lock.

The earlier direct attempt used `2026.2.2`. That release's RBAC `0010`
migration did not depend on core `0056`, so Django could record or run the
group-field removal before the data migration that required it. Authentik
later added the missing dependency in
[`7af9e980792d`](https://github.com/goauthentik/authentik/commit/7af9e980792d).
That upstream defect explains the impossible `0010`-before-`0056` history. The
exact mechanism by which the physical older columns were restored while the
future marker remained is not proven, so the repair is guarded by observed
state rather than an assumed incident narrative.

### Second rehearsal: restored-copy repair

PR #72 merged as revision `5a8222de6bb98df46d4efafb8750925c3ee90e9b`
at 2026-08-25 04:45 UTC. Flux applied that exact revision and started
`authentik-upgrade-repair-rehearsal-v2-014a5e82b6d2` on `rig0`. The Job
started from the same fixed encrypted backup, proved the exact fingerprint
above, and then performed one transaction against the isolated loopback
database:

1. make `authentik_rbac_role.group_id` nullable, completing the missing
   physical effect of recorded migration `0008`;
2. remove the empty obsolete `authentik_rbac_initialpermissions.mode` column,
   completing the missing physical effect of recorded migration `0009`; and
3. delete exactly the premature `authentik_rbac.0010` history marker so patched
   `2026.2.6` can run it after core `0056`.

Any fingerprint mismatch or row-count change aborts and rolls back the whole
transaction. The lifecycle wrapper also fails immediately on migration startup
errors instead of allowing Authentik's internal router restart loop to consume
the full readiness window. Final verification requires core `0056` and RBAC
`0010` to each be applied exactly once, `group_id` to be absent at `2026.5.6`,
the identity/provider counts to remain unchanged, and zero waiting locks.

The repair completed transactionally and every lifecycle passed in order:
`2025.10.4`, `2025.12.0`, `2025.12.6`, `2026.2.6`, and `2026.5.6`. Every init
container and the terminal verifier exited zero. The Job completed `1/1` in
4m29s with:

```text
PASS: isolated Authentik upgrade reached 2026.5.6; users=5, groups=2, applications=3, providers=3, migrations=717, waiting_locks=0
```

The terminal checkpoint found all four nodes Ready, API and etcd healthy, and
all Flux Kustomizations Ready at the merge revision. Live Authentik remained
server 1/1 on `asio` and worker 1/1 on `strix`; live PostgreSQL remained 2/2
on `strix` with zero waiting locks. Node use was `asio` 4% CPU / 31% memory,
`rig0` 1% / 19%, `sparky` 0% / 56%, and `strix` 5% / 21%.

Complete Job/Pod YAML, events, and all lifecycle logs are retained owner-only
on `rig0` under
`/home/al/kubani-evidence/authentik/2026-08-25-pr72/`. The directory is mode
`0700`, every file is mode `0600`, every gzip passed integrity validation, and
the on-host SHA-256 values match the capture:

| File | SHA-256 |
| --- | --- |
| `events.txt.gz` | `4ed2edb3eaba4f768ba3443ff810f7b0c6a0010d5119c3b37aed713962b8ad87` |
| `job.yaml.gz` | `4c3a3667537f9d42988a957bb36394cffb947f2fc76a9d9040bc7e3960caa5d3` |
| `pod.yaml.gz` | `2cd531325682d2a403d310209c1117521d6ae8b3fd6eb7351b77c6b949816ac1` |
| `repair-migration-state.log.gz` | `fba05e58031ea94e041c8a97fd6521da5630f7bb191bbd12fe66ee498003ce34` |
| `restore-postgres.log.gz` | `42e8bd7a9a041637b98f13ccd7f2c1fd6e9f85fb628c3706c846bece8939f227` |
| `upgrade-2025-10-4.log.gz` | `70fbebce75873c504727da67cea6e30efbfcb94ce7a7a81f99e9c58004219bb2` |
| `upgrade-2025-12-0.log.gz` | `97117b70080c16da7a85c5ad3dc105dc12678775d8d2d0796ce0d2dcac123fa0` |
| `upgrade-2025-12-6.log.gz` | `48f5aea8612433c2f192b68fe567b23129db31d0f0c6c232182d8290f81a3beb` |
| `upgrade-2026-2-6.log.gz` | `a8225f49cff9a0e30bd3039682d440fa107564b6752878de78b0320450e4e029` |
| `upgrade-2026-5-6.log.gz` | `5dc64dd746170202a78609d5ac75e8730fba66735918a3dc48115f0e6cb4ff7c` |
| `verify-upgrade.log.gz` | `e0b15946a4c90cefec32ed1d7b3a8f5563eb0bb7410570c3454802b6038076fe` |

This is repair evidence only. It does not authorize the same SQL against the
live database. Live pre-upgrade alignment still requires its own exact diff,
fixed fresh backup and independently verified restore, explicit maintenance
window and destructive data-change approval, zero Authentik connections,
bounded lock and statement timeouts, and post-repair verification before the
first live version hop.

The resources under
`infrastructure/gitops/apps/authentik-upgrade-rehearsal/` are included in the
database Kustomization. Merging their exact revision authorizes one named Job
run; a failed Job has zero retry and must not be deleted and retried.

The Job:

- is pinned to `rig0` because the retained encrypted recovery volume is local
  to that node; this is a recovery-only exception to the `asio`/`strix`
  application placement preference;
- mounts the fixed backup and its checksum read-only;
- restores into a 2 GiB `emptyDir`, never the live PostgreSQL service;
- uses a restartable init sidecar listening only on pod loopback;
- runs the five digest-pinned Authentik lifecycle containers sequentially;
- creates a runtime-only rehearsal secret key instead of copying the live
  Authentik secret;
- has no service-account token and receives no Authentik credential;
- is selected by an empty ingress/egress NetworkPolicy. The database
  namespace's existing additive policy still permits DNS to cluster DNS, but
  no policy permits this label to connect to live PostgreSQL, the Internet, or
  any provider;
- has a one-hour deadline, no retry, bounded requests/limits, and no TTL so the
  completed pod and logs remain evidence; and
- fails if any version does not become HTTP-ready, has pending migrations,
  changes user/group/application/provider counts, regresses migration history,
  leaves a waiting lock, or fails to record `2026.5.6` as the final version.

### Merge and monitor procedure

Immediately before merge, repeat the cluster, Flux, node-capacity, Authentik,
PostgreSQL lock, and backup-freshness checkpoint. Stop if it differs materially
from the starting state.

After merge:

1. Confirm Flux observes the exact merged revision and the `databases`
   Kustomization remains Ready.
2. Resolve the single Job pod and confirm it is on `rig0` before following
   logs.
3. Inspect each init-container status in order. Do not restart, delete, or
   manually advance a failed container.
4. Record only the fixed backup name, container versions, pass/fail summaries,
   object counts, migration count, duration, placement, and resource health.
5. Repeat the full cluster checkpoint after every lifecycle container and after
   Job completion. Authentik and the source PostgreSQL must remain healthy.

Success is one completed Job whose final line begins `PASS: isolated Authentik
upgrade reached 2026.5.6`. This is migration-path evidence only; it does not
authorize the live upgrade.

On rehearsal failure, preserve the Job, all container logs, and status. Revert
the merge to prune the executable desired state only after evidence is saved.
The source database and encrypted backup need no rollback because both are
read-only to the Job.

## Stage B: live sequential promotion

### Live alignment and consolidated ladder

Live promotion uses three meaningful review boundaries: recovery evidence,
maintenance drain, and the irreversible migration. It does not create one PR
per calendar release. The third change still visits every required release in
one Kubernetes Job whose init containers execute strictly in order; changing
the HelmRelease directly is not used to express intermediate hops.

1. The preflight merge adds `authentik-live-preflight-v2`. It writes the fixed
   encrypted backup
   `authentik-live-alignment-v1-20260825.sql.gz.enc` to the retained Rig0
   volume, verifies its checksum and encrypted stream, restores it into a 2 GiB
   loopback-only PostgreSQL instance, and requires the restored migration,
   schema, version, lock, and identity-object fingerprint to exactly match live
   state. The fixed name is outside the ordinary daily-backup retention glob;
   it is retained until the `2026.5.6` post-upgrade evidence is accepted and
   removed only through a later reviewed cleanup.

   The initial `v1` attempt failed at 2026-08-25 11:42 UTC before connecting to
   PostgreSQL or creating a backup because the non-root process could not
   change permissions on the root-owned `/work` volume mount. The `v2` Job
   creates and owns `/work/runtime` instead. The failed Job had zero retries;
   the live fingerprint remained exact, no backup target existed, and the
   alignment Job remained suspended before the versioned retry was proposed.

   PR #75 merged as revision `a9e25dec8a587da228c560fe545bd09b1883fd22`
   at 2026-08-25 11:49 UTC. The `v2` Job completed on `rig0` with pod exit code
   zero. It created a 17,363,872-byte encrypted backup whose retained checksum
   and independent host-side SHA-256 both equal
   `73819ad68e0bc60e7888dfba0604b7cb9bdaa93b6f226f23fe02fe8e1362f00c`.
   The backup and checksum are mode `0600`. The isolated restore matched the
   exact live fingerprint with zero waiting locks. Afterward the live
   fingerprint remained unchanged, external Authentik readiness passed, all
   Flux Kustomizations were Ready on the merge revision, and node use remained
   within the preflight envelope.
2. The preflight gate staged `authentik-live-alignment-v1` suspended and bound
   it to the fixed backup and exact reviewed repair script.
3. PR #76 changed only the normal Authentik server and worker replicas to zero.
   At the post-merge checkpoint both Deployments had zero desired, ready, and
   available replicas; there were no Authentik pods or database sessions; all
   nodes and Flux Kustomizations were Ready; and node utilization remained
   within the reviewed envelope.
4. The consolidated migration change unsuspends the alignment Job and adds it
   to the `databases` Flux health checks. The `apps` Kustomization already
   depends on `databases`. Because dependency status can briefly reflect the
   prior reconciliation, the ladder also waits up to 15 minutes for the exact
   post-alignment fingerprint: it waits only while the exact pre-alignment
   fingerprint remains, and fails immediately on any third state. Alignment
   independently waits up to five minutes for **all** other connections to
   drain and repeats the check inside its transaction.
5. Alignment uses a transaction-scoped advisory lock, a five-second lock
   timeout, a 30-second statement timeout, the rehearsed exact fingerprint,
   unchanged domain-row counts, and exact postconditions. It has no retry. Any
   mismatch, timeout, connection, lock, checksum, or row-count change stops the
   migration and preserves evidence.
6. After alignment completes, `authentik-live-upgrade-ladder-v1` records an
   exact post-alignment baseline and runs `2025.10.4`, `2025.12.0`,
   `2025.12.6`, `2026.2.6`, and `2026.5.6` as sequential init containers. Each
   lifecycle must become loopback-ready and report no pending migrations before
   the next image can start. A terminal verifier requires the rehearsed 717
   migration rows, final version `2026.5.6`, unchanged counts for users, groups,
   applications, and providers, converged repaired migrations, zero other
   Authentik sessions, and zero waiting locks.
7. The same change advances the HelmRelease chart and immutable image to
   `2026.5.6` but deliberately leaves server and worker replicas at zero. Flux
   explicitly health-checks both the HelmRelease and live-ladder Job. A final,
   separately reviewed activation change restores normal workloads only after
   migration evidence is retained and accepted.

The alignment and ladder use namespace-local dedicated ServiceAccounts with
token automount disabled, run as non-root with read-only root filesystems and
dropped capabilities, and have bounded resources, deadlines, and zero retries.
The alignment Job has a 15-minute active deadline and its owning `databases`
Flux Kustomization has a 20-minute timeout. The ladder's 90-minute active
deadline covers its 15-minute alignment wait, five independently bounded
approximately 12-minute lifecycle readiness waits, and verification and
scheduling margin. The owning `apps` Flux Kustomization has a 100-minute
timeout, so Flux cannot time out either healthy Job before its Kubernetes
deadline. These are fail-closed upper bounds, not expected durations.
The ladder receives only the live Authentik secret key and its own PostgreSQL
password; it receives no bootstrap password, bootstrap token, provider token,
or Kubernetes API credential. Its selected NetworkPolicy permits only cluster
DNS and PostgreSQL TCP/5432. The lifecycle binds HTTP to pod loopback and has no
Internet route or provider access.

Both Jobs are pinned to `rig0`. Alignment requires the node-local retained
recovery volume. The ladder follows the exact rehearsal placement and, at the
2026-08-25 pre-review checkpoint, every pinned image was already present on
that node and memory use was 19%. This bounded maintenance exception avoids a
registry dependency and does not change the `asio`/`strix` preference for the
long-running server and worker restored by the activation change.

The migration merge is the irreversible live-data boundary. A Git revert is not
a rollback after either Job begins; recovery means restoring the fixed backup.

Immediately before merge, repeat API, etcd, Flux, node pressure/capacity,
PostgreSQL health/connections/locks/storage, exact backup checksum, workload
drain, and image-cache checks. After merge:

1. Confirm Flux observes the exact merged revision and resolves the alignment
   pod to `rig0`.
2. Follow the alignment status and sanitized log. Do not delete, retry, or
   manually bypass a failure.
3. Repeat the full cluster, capacity, database-session, and lock checkpoint
   after alignment and before the ladder starts.
4. Confirm the ladder pod resolves to `rig0`; inspect each init-container status
   in order and capture its pass/fail summary. No failed container is restarted
   or manually advanced.
5. Repeat the health/capacity/lock checkpoint after every lifecycle and after
   the terminal verifier. Stop if any node, Flux object, PostgreSQL workload, or
   invariant degrades.
6. Retain Job/Pod YAML, events, and sanitized logs owner-only on `rig0`, with
   checksums, before any later cleanup.

Success is both Jobs complete, the terminal line begins `PASS: live Authentik
upgrade reached 2026.5.6`, the HelmRelease is Ready at `2026.5.6`, normal
replicas remain zero, PostgreSQL has no waiting lock or stray Authentik session,
and all cluster/Flux health checks remain green. The final activation change
then restores one server on `asio` and one worker on `strix`, verifies matching
versions and built-in/external health, and exercises the existing WebAuthn/OIDC,
group-removal, deactivation, logout, refresh-revocation, forward-auth, and
embedded-outpost journeys.

## Stop, rollback, and contingency rules

Stop without retrying when any of the following occurs:

- the exact Git revision, backup, chart, image digest, node, or target differs;
- API, etcd, Flux, PostgreSQL, Authentik, `asio`, `strix`, or `rig0` degrades;
- backup age/checksum/restore is ambiguous;
- a migration exceeds its bounded window, waits on a lock, exits, or reports an
  inconsistency;
- user, group, application, provider, or outpost invariants change;
- more than one Authentik lifecycle process reaches the migration database; or
- a credential or plaintext backup content appears in retained output.

Authentik does not support downgrade. A Git revert alone is therefore not a
rollback after a migration starts. Recovery for a failed live hop is:

1. preserve pod, Helm, Flux, PostgreSQL lock/activity, and sanitized migration
   evidence;
2. suspend Authentik reconciliation and stop all Authentik workloads;
3. obtain explicit approval naming the failed hop and exact pre-hop backup;
4. restore that backup into the live Authentik database using the PostgreSQL
   recovery runbook;
5. restore the last known-good chart/image desired state;
6. resume Flux, reconcile, and repeat every pre/post health and identity check.

Do not fake migrations, manually alter tables, cancel a lock holder, drop the
database, restore data, or delete evidence as an improvised workaround. Those
are separate destructive actions requiring exact authorization.

## Evidence and sign-off

The migration PR must contain:

- the rendered Job and NetworkPolicy;
- passing contract, manifest, secret, and shell checks;
- chart and image provenance/digests;
- the pre-merge cluster checkpoint; and
- a statement that merge authorizes the exact live alignment and sequential
  ladder, leaves normal workloads at zero, and crosses the irreversible
  database boundary.

Al McKay, as sole repository and cluster owner, may authorize the consolidated
live migration by merging its exact reviewed revision. Final workload
activation remains a separate review boundary. Completion requires retained
evidence for the rehearsal, alignment, all five live lifecycle containers,
final identity journeys, capacity, and the tested recovery path.
