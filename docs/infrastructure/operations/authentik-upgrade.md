# Authentik 2026.5 upgrade and recovery plan

Last reviewed: 2026-08-24

Owner and stop authority: Al McKay

Status: isolated rehearsal is merge-gated; live Authentik remains `2025.10.3`

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

## Stage A: isolated current-backup rehearsal

The resources under
`infrastructure/gitops/apps/authentik-upgrade-rehearsal/` are included in the
database Kustomization. Merging their exact revision authorizes one Job run; a
failed Job has zero retry and must not be deleted and retried.

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

Live promotion uses one reviewed GitOps merge per hop. This is intentionally
not collapsed into one PR: Flux would converge directly to the final desired
version and skip the intermediate releases that Authentik requires.

Before every hop:

1. Repeat API, etcd, Flux, node pressure/capacity, Authentik health/restarts,
   PostgreSQL health/connections/locks/storage, and ingress certificate checks.
2. Create and verify a fresh encrypted rig0 backup, record its exact filename,
   and prove an isolated restore. This is the pre-hop recovery point.
3. Confirm the previous version, chart, migration check, version-history tail,
   user/group/application/provider counts, and embedded outpost inventory.
4. Pre-pull the exact server digest on `asio` and `strix` because this cluster
   has previously experienced registry/CDN reachability failures.
5. Render the chart with the live values and verify the server, worker, and
   embedded outpost version contract.

For the migration-bearing hops, set the worker to zero and use a `Recreate`
server deployment strategy. That intentionally accepts a short homelab login
outage so no old server, rolling-update surge pod, or worker can compete for the
`AccessExclusiveLock`. Prefer the server on `asio`; restore one worker on
`strix` only after the final hop passes. Do not route Starbase login through the
instance during the ladder.

After every merge, wait for that exact Helm revision to finish before preparing
the next one. Verify:

- one server is Ready on the intended version and preferred node;
- built-in and external HTTPS health succeed;
- `ak migrate --check` exits zero and version history records the expected
  patch;
- no migration process, transaction, or waiting lock remains;
- the four Authentik object counts and embedded outpost inventory match;
- a local administrator login and one existing forward-auth application work;
- Flux, PostgreSQL, `asio`, and `strix` remain healthy and within headroom; and
- logs contain no migration inconsistency, authentication secret, or unexpected
  traceback.

At `2026.5.6`, restore the worker on `strix`, verify it matches the server, then
exercise the existing WebAuthn/OIDC, group-removal, deactivation, logout, and
refresh-revocation checks before activating the Starbase blueprint.

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

The rehearsal PR must contain:

- the rendered Job and NetworkPolicy;
- passing contract, manifest, secret, and shell checks;
- chart and image provenance/digests;
- the pre-merge cluster checkpoint; and
- a statement that merge starts the exact Job but does not change live
  Authentik.

Al McKay, as sole repository and cluster owner, may authorize the rehearsal by
merging the exact reviewed revision. Live promotion remains separately gated at
each hop. Final completion requires retained evidence for the rehearsal, all
five live versions, final identity journeys, capacity, and the tested recovery
path.
