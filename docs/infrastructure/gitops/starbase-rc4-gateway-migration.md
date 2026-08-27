# Starbase RC4 gateway migration activation

Date: 2026-08-27

Status: prepared for review; merge is the exact-revision activation decision

## Objective and authority boundary

Run exactly one content-bound RC4 gateway migration after the RC4 core
migration completed and passed every acceptance invariant. This change does not
authorize a Starbase Deployment, connector, GitHub access, mutation worker, or
sandbox worker.

The only new executable-state change is:

- `starbase-system/starbase-gateway-migrate-c5de66b03eaf`:
  `spec.suspend: true` to `false`.

The Starbase-only Flux Kustomization gains an exact health check for that Job.
The completed core migration remains retained and health-gated. A failed,
incomplete, or missing gateway migration makes only `starbase-foundation`
NotReady; unrelated Kubani layers continue reconciling.

## Immutable execution contract

| Field | Accepted value |
|---|---|
| Release | `0.1.0-rc.4` |
| Source revision | `e35ac44f5cea35b400d73bf94802b1a70e84585a` |
| Job | `starbase-gateway-migrate-c5de66b03eaf` |
| Execution digest | `sha256:c5de66b03eaf0bf9dd2c7ab48421b702ef7fa405cd0272d0a03a450f9cb4ee74` |
| Migration-set digest | `sha256:38db198875781dd2d640358b1840ae28e7574dd4c87661e0a8bb0b2e8837d3f3` |
| Image | `ghcr.io/x-mckay/starbase/gateway-migrator@sha256:1b7acd8ae30dc79a9491e6ffc6b526d99ee69f8e3f8302b647e94d0c6c7473db` |
| Retry bound | `backoffLimit: 0` |
| Runtime bound | `activeDeadlineSeconds: 300` |
| Placement | required on `asio` or `strix` |
| Requests / limits | 25m / 250m CPU; 32 MiB / 128 MiB memory |
| Credential | `starbase-gateway-migration/database-url` only |

The pod cannot automount a Kubernetes token, runs as non-root with all
capabilities dropped and RuntimeDefault seccomp, has a read-only root
filesystem, and receives no provider authority. It has no completion TTL.

The sole migration is `0001_operator_sessions.sql` with digest
`sha256:e860af141ba5717dcf84020da9a5c1f18b841e34b9c9d3a5d3b95aec9b45e3b6`.
That exact ledger row and its two tables are already present from the accepted
predecessor migration. Both tables are owned by
`starbase_gateway_migrator`, and `operator_sessions` contains zero rows. RC4
execution therefore validates successor-image behavior and idempotence; it does
not authorize a session, backfill, or runtime write.

## Core predecessor acceptance

PR #93 merged as `8616fdfb8e3df0cc0e286449c1213325c5436eae` at
`2026-08-27T13:29:11Z`. The exact RC4 core Job ran once on `asio`, completed in
five seconds with exit code zero, and had zero failures or restarts. Its two-row
ledger, four tables, ownership, and empty state remained exact. Gateway state
was unchanged. All five Flux Kustomizations, services, storage, certificates,
PostgreSQL, Authentik, and nodes remained healthy; all Starbase Deployments
remained at zero.

The sanitized core Job, pod, events, and exact available log are checksummed in
[`evidence/starbase-rc4-core-migration/`](evidence/starbase-rc4-core-migration/).

## Pre-merge gates

Before merge, all of the following must pass on the exact PR head:

1. core execution evidence inventory and checksums;
2. repository validation, focused contracts, security hooks, deterministic
   render, and `git diff --check`;
3. Flux-equivalent server-side dry-run of the effective Secret-free foundation
   and exact Flux health-gate update, with no persistence;
4. all Flux Kustomizations aligned and Ready, all nodes Ready and
   pressure-free, and every required live-service probe healthy;
5. PostgreSQL and Longhorn healthy, current backup successful, zero waiting
   locks, and zero idle-in-transaction sessions;
6. accepted two-row core ledger, four owned tables, and zero core state/fence
   rows;
7. exact one-row gateway ledger, exactly two owned tables, and zero session
   rows;
8. gateway Job still suspended with no start, active pod, success, or failure;
9. core Job still Complete, every Starbase Deployment still zero, and no
   provider or mutation activation; and
10. owner review and merge of the exact immutable revision.

## Post-merge acceptance

Observe natural Flux reconciliation. Stop on unexpected placement, retry,
timeout, image or migration digest drift, unexpected table/owner/row, core
mutation, workload start, dependency degradation, node pressure, or loss of
observation.

Success requires:

1. one completed gateway pod on `asio` or `strix`, zero restarts and failed
   attempts, and exit code zero;
2. the exact image, execution digest, and one-row gateway ledger;
3. exactly two gateway tables with unchanged ownership and zero session rows;
4. unchanged core tables, two-row ledger, ownership, and zero state/fence rows;
5. both migration Jobs Complete and all Starbase Deployments still zero;
6. all Flux, PostgreSQL, storage, Authentik, service, and preferred-node checks
   healthy at the exact merge revision; and
7. sanitized Job, pod, event, and available-log evidence retained before any
   later release or cleanup can prune the execution.

Only after these checks pass may a runtime activation candidate be prepared.

## Failure handling

Retain a failed gateway Job for evidence. Do not retry, delete/recreate,
force-replace, run SQL manually, activate a runtime, or alter core state.
Preserve sanitized status, events, and logs and diagnose the exact failure.

If a corrected migrator release is required, commit its predecessor evidence
before the repair merges; the corrected content-bound identity will replace and
prune the failed Job. Prefer reviewed forward repair. Shared PostgreSQL restore
is not the default response while both accepted schemas contain no application
rows.
