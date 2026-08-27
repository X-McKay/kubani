# Starbase RC4 core migration activation

Date: 2026-08-27

Status: accepted and completed; evidence retained

## Objective and authority boundary

Run exactly one content-bound RC4 core migration Job after the inert RC4
promotion reconciled successfully. This change does not authorize the gateway
migration, a Starbase Deployment, a connector, GitHub access, a mutation
worker, or a sandbox worker.

The only executable-state change is:

- `starbase-system/starbase-core-migrate-67c24a8df537`:
  `spec.suspend: true` to `false`.

The Starbase-only Flux Kustomization also gains an exact health check for that
Job. Consequently, a failed, incomplete, or missing migration makes only
`starbase-foundation` NotReady and prevents later Starbase stages from being
called healthy. No other Kustomization depends on `starbase-foundation`.

## Immutable execution contract

| Field | Accepted value |
|---|---|
| Release | `0.1.0-rc.4` |
| Source revision | `e35ac44f5cea35b400d73bf94802b1a70e84585a` |
| Job | `starbase-core-migrate-67c24a8df537` |
| Execution digest | `sha256:67c24a8df537c619355ea8e062adf300a11feab774ba2401cd010e971318fce8` |
| Migration-set digest | `sha256:3a3b6224525f6db69bd680f0e3117ef19da183ef6c9865b74b74c53fc77a5f58` |
| Image | `ghcr.io/x-mckay/starbase/core-migrator@sha256:fad95f8fb51f709eb0798f96a13aaa91381141ccb31735972c31967594eee878` |
| Retry bound | `backoffLimit: 0` |
| Runtime bound | `activeDeadlineSeconds: 300` |
| Placement | required on `asio` or `strix` |
| Requests / limits | 25m / 250m CPU; 32 MiB / 128 MiB memory |
| Credential | `starbase-core-migration/database-url` only |

The pod cannot automount a Kubernetes token, runs as non-root with all
capabilities dropped and RuntimeDefault seccomp, has a read-only root
filesystem, and receives no provider authority. The Job has no completion TTL,
so a successful execution remains immutable evidence and cannot be garbage
collected and recreated by Flux.

The ordered migration set is:

1. `0001_initial.sql` —
   `sha256:dd8924aec9c52d3e4bc106f9501a52c92129cdd3d4a43745a614534abcc624a7`;
2. `0002_connector_fence_high_water.sql` —
   `sha256:e4b0ce3a5a72cd8bf9e985973ceecccad94335db54057ff24811acbd15e49817`.

Both rows already exist with these exact digests because the earlier RC2/RC3
staged migrations established the compatible schema before runtime rollback.
The three existing state tables and `connector_fence_high_water` are owned by
`starbase_core_migrator`; both state tables are empty. RC4 execution is
therefore an idempotence and successor-image validation, not authorization to
alter or backfill application state.

## Completed predecessor acceptance

PR #92 merged as `df7375dbc7be651929bc583e9054d2811cb7040a` at
`2026-08-27T11:44:13Z`. Flux converged all five Kustomizations to that exact
revision in dependency order. Post-reconcile acceptance confirmed:

- every Kustomization Ready at the merge revision;
- the old `starbase-kubani-observer` ClusterRole and ClusterRoleBinding absent;
- the two RC2 migration Jobs absent as expected after pruning;
- all retained RC2 evidence checksums valid;
- exactly three namespace-local observer Roles and three matching RoleBindings,
  each granting only namespaced `list` on pods, Deployments, DaemonSets, and
  StatefulSets to the Kubernetes connector ServiceAccount;
- both RC4 migration Jobs present, suspended, and never started;
- core and both connector Deployments at zero replicas;
- all live service, Certificate, Longhorn, PostgreSQL, Authentik, registry,
  Temporal, and active model probes passing; and
- no mutation, migration execution, or runtime activation during validation.

The final post-reconcile capacity checkpoint measured `asio` at 4% CPU / 30%
memory and `strix` at 5% CPU / 19% memory. Both remain preferred and have ample
headroom for this bounded 25m / 32 MiB request.

## Candidate preflight evidence

At `2026-08-27T11:50:15Z`, the live core Job was still suspended with no start
time, active pod, success, or failure. The gateway Job had the same inactive
state. Both retained the exact RC4 image, execution digest, required
`asio`/`strix` placement, and zero-retry contract.

Read-only PostgreSQL catalog checks found exactly
`schema_migrations`, `state_journal`, `state_current`, and
`connector_fence_high_water` in `starbase_core`, all owned by
`starbase_core_migrator`. The ledger contained exactly the two expected rows and
digests. The three state/fence tables contained zero rows. The gateway schema
and one-row ledger were unchanged and `operator_sessions` contained zero rows.
PostgreSQL reported zero ungranted locks and zero idle-in-transaction sessions.

The `postgres-backup` CronJob was active on its daily schedule with no active
run. Its latest Job completed successfully at `2026-08-27T02:00:09Z`. A failed
June Job remains retained as historical failure evidence; it does not represent
the current backup result and was not deleted or hidden during this preflight.

Local validation passed all six Kustomize renders, whole-tree Secret controls,
and 63 promotion, Phase 4A, recovery, Authentik, and live-probe tests. Every
pre-commit security and lint hook passed. A Flux-equivalent server-side dry-run
admitted all 52 non-Secret foundation objects and the exact Flux health-gate
update without persistence. The post-dry-run service suite remained green at
merge revision `df7375d`; both live migration Jobs remained suspended and
never started. `asio` measured 3% CPU / 30% memory and `strix` 4% CPU / 19%
memory after the exercise.

## Fresh pre-merge gates

Before merge, all of the following must pass on the exact PR head:

1. repository validation, focused contract tests, security hooks, deterministic
   render, and `git diff --check`;
2. server-side dry-run of the complete Secret-free effective foundation using
   Flux-equivalent field ownership, with no persisted resource;
3. all Flux Kustomizations Ready and aligned, all nodes Ready and pressure-free,
   and all required live-service probes healthy;
4. PostgreSQL Ready, Longhorn healthy, and the latest scheduled encrypted
   backup successful;
5. zero ungranted locks and zero idle-in-transaction sessions;
6. exact two-row core migration ledger, four expected core tables, empty state
   tables, and all core tables owned by `starbase_core_migrator`;
7. unchanged one-row gateway ledger, zero operator-session rows, and gateway
   Job still suspended;
8. core Job still suspended with no start time, active pod, success, or failure;
9. core and both connector Deployments still at zero replicas; and
10. owner review and merge of the exact immutable revision.

If any invariant changes before merge, stop and re-evaluate rather than relying
on this checkpoint.

## Post-merge acceptance

Observe natural Flux reconciliation; do not manually unsuspend or replace the
Job. Stop immediately on unexpected placement, any retry, timeout, image or
migration digest drift, unexpected table/owner/row, gateway mutation, workload
start, dependency degradation, node pressure, or loss of observation.

Success requires:

1. one completed pod on `asio` or `strix`, zero restarts, zero failed attempts,
   and exit code zero;
2. the exact digest-pinned image and both exact migration-ledger rows;
3. exactly the four expected core tables with unchanged ownership;
4. zero rows in `state_journal`, `state_current`, and
   `connector_fence_high_water`;
5. unchanged gateway schema, ledger, and zero session rows;
6. gateway migration still suspended and all Starbase Deployments still zero;
7. all Flux, PostgreSQL, storage, Authentik, service, and preferred-node checks
   healthy at the exact merge revision; and
8. sanitized Job status, pod status, events, and available logs retained before
   any later cleanup.

Only after those checks pass may a separate gateway-migration candidate be
prepared.

## Recorded acceptance

PR #93 merged as `8616fdfb8e3df0cc0e286449c1213325c5436eae` at
`2026-08-27T13:29:11Z`. The Job ran exactly once on `asio` from
`13:29:14Z` through `13:29:19Z`, completed with exit code zero, and had zero
failed attempts or restarts. Every database, gateway-inactivity, zero-runtime,
Flux, service, storage, identity, and preferred-node acceptance invariant
passed. Sanitized status, events, and the exact available log are retained in
[`evidence/starbase-rc4-core-migration/`](evidence/starbase-rc4-core-migration/).

## Failure handling

A failed migration is retained for evidence. Do not delete/recreate it, add a
Flux force annotation, retry it, run SQL manually, activate the gateway, or
start a runtime. Preserve sanitized status, events, and logs and diagnose the
exact failure.

If diagnosis produces a corrected migrator release, commit the sanitized Job,
pod, event, and available-log evidence before that repair merges: its new
content-bound execution identity will replace and prune the failed Job during
reconciliation, and that pruning must be an expected, evidence-retained event.

Application rollback does not reverse schema. Because the accepted core schema
and ledger already match this release and contain no application rows, an RC4
failure should normally be handled by a reviewed forward repair of the
migrator or deployment contract. Shared PostgreSQL restore is not the default
response. Any cleanup or replacement requires its own evidence-bound review.
