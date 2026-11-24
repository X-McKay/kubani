# Worker Versioning deployment and qualification plan

**Status:** implementation plan, not a rollout or qualification. Root/operator owns
execution after the active conformance batch ends. This change made only bounded
metadata reads and created/deleted one diagnostic Job. No worker, Schedule,
routing configuration or workflow was changed.

**Objective:** finish spec 10.6/14.4 worker versioning using the existing Python
SDK `PINNED` support on Temporal 1.29.1, without moving an existing business history
to a different build. Preserve the five-minute cleanup Schedule, confirmed Pod
deletion, existing service accounts/permissions and artifact storage.

## Evidence and current gap

[Read-only receipt](../../infrastructure/configuration/agent-runtime-platform-worker-versioning-readonly-2026-11-06.json)
records the 2026-11-06 19:41:37 UTC audit. The short diagnostic Job used the
existing harness mTLS mount, no service-account token, payload key, APS key or
artifact volume. It succeeded and was deleted. No credentials or workflow inputs
were output. The source script remains `/tmp/phase-b-versioning/audit.py`; its
SHA256 is recorded for reproduction, and the original RPC report remains
`/tmp/phase-b-versioning/temporal-readonly.json`.

| Read | Observed result | Limit |
| --- | --- | --- |
| Server/namespace | Temporal 1.29.1; namespace `agents-tenant-test`; seven-day history retention | Capability/read success is not promotion qualification |
| Worker Deployment API | List succeeds, empty; both expected Deployment describes return NOT_FOUND | No registered versioned workers yet |
| Queues | `sessions-tenant-test` and `cleanup-tenant-test` current `__unversioned__`; Workflow and Activity pollers present | SDK auto-generated poller build hash does not mean versioning is enabled |
| Queue stats | Both enhanced Workflow/Activity responses have zero-default approximate backlog and zero age | Approximate stats alone cannot prove no in-flight work |
| Running executions | Complete namespace listing has zero rows | Point-in-time, visibility-backed observation; must be refreshed during a controlled cutover |
| Cleanup Schedule | Unpaused, interval 300s, overlap SKIP, execution timeout 900s; no running actions; no version override | Next observed action 19:45 UTC; catchup setting 31536000s must remain intact |
| Kubernetes | One Ready session worker and one Ready reconciler on `strix`, zero restarts, image `d7950de` | Both `WORKER_BUILD_ID` values empty; image pin will change before execution |

`zetra/platform/runner/runner/worker.py::_deployment()` already constructs
`WorkerDeploymentConfig(use_worker_versioning=True,
default_versioning_behavior=PINNED)` when `WORKER_BUILD_ID` is nonempty. Both
worker roles use it. `ensure_reconciler_schedule()` only creates a missing
Schedule; it does not rewrite or unpause an existing Schedule. There is currently
no guarded promotion/drain operator, per-build Kubernetes inventory, or live
old/new routing evidence.

The deployed server's pinned source supports `build_id`, `conflict_token`,
`ignore_missing_task_queues` and `allow_no_pollers` on
`SetWorkerDeploymentCurrentVersion`. Use the current Worker Deployment API,
not the retired `SetCurrentDeployment` API. SDK 1.34.0 exposes the required raw
RPCs even though its Client has no high-level Worker Deployment handle.
[Temporal 1.29.1 frontend implementation](https://raw.githubusercontent.com/temporalio/temporal/v1.29.1/service/frontend/workflow_handler.go)
and [its API dependency](https://raw.githubusercontent.com/temporalio/temporal/v1.29.1/go.mod)
confirm this wire contract; test it against the pinned server before production
promotion.

## Constraints and initial migration

Temporal's first Current Version receives subsequent tasks for existing
unversioned workflows. Leaving old unversioned pollers running does not preserve
those histories. Therefore the first migration requires a controlled empty-work
window, not merely a rolling image update.
[Official migration semantics](https://docs.temporal.io/production-deployment/worker-deployments/unversioned-to-versioned-migration).

The existing Kubernetes selectors contain only role app label and tenant. Adding
a build label only to new Pods does **not** make the old selectors disjoint, and
an existing Deployment selector is immutable. During the initial quiet window,
remove the two old Deployment objects after graceful stop and recreate workers
with per-build names/selectors. Preserve the PVC and all identities. Do not use
orphan/adoption operations, a misleading app label, or force selector replacement
while a history is running. Pre-render and validate both forward and rollback
manifests before entering this window.

Subsequent versions coexist on the same Temporal queues. Keep stable Temporal
Deployment names `session-runner-tenant-test` and
`cleanup-reconciler-tenant-test`, but use Kubernetes names such as
`session-runner-tenant-test-ce7c06b-48ef7c54e41b`. Selectors must include the
existing app/tenant labels **and** `agentplatform.io/worker-build` with the same
immutable build ID. Bound the label/name lengths and reject an already-recorded
build ID pointing to a different full image digest. Record the full image and
source revision in annotations/inventory; shortened IDs are labels, not image
integrity checks. No deployment reuses a build ID for changed code.

The session workers share the existing Longhorn RWO artifact PVC. RWO allows
multiple Pods on its one attached node; it is not a multi-node storage design.
Keep both versions on the same exact verified database node/attachment (`strix`
at audit), check requested resources and available headroom for coexistence,
and fail preparation if the database label matches multiple nodes without an
explicit same-node placement constraint. Reconciler workers retain their
existing emptyDir/no-artifact behavior. Preserve the 60-second graceful shutdown.
This does not fix the single-node artifact availability gap or replace the
spec's eventual S3 storage.

## Smallest implementation batch

### 1. Guarded Temporal operator in ZetRA

Create `platform/runner/runner/worker_versioning.py` and
`platform/runner/tests/test_worker_versioning.py`; add invocation and receipts to
`docs/platform-playbook.md`. Reuse the existing mTLS environment. Metadata reads
must not require the payload-decryption key. Default command is `inspect`.

- `inspect --tenant tenant-test`: bounded get-system-info, namespace, both queue
  types, Worker Deployment/current/ramping/version details, Schedule and paginated
  open-execution metadata. Emit allowlisted JSON and hash conflict tokens; never
  output payloads, certificates, keys or arbitrary API error bodies. Missing or
  capped pages are incomplete, not zero.
- `prepare --deployment NAME --build-id ID --image IMAGE@sha256:...`: require an
  exact accepted namespace/name, Kubernetes role/build/image mapping, healthy
  matching Pods, fresh Workflow **and** Activity pollers, expected task queues,
  no unexpected ramp, and immutable build mapping. Produce a reviewable snapshot
  containing current version and conflict-token hash. No mutation.
- `promote --deployment NAME --build-id ID --expected-current ID_OR_UNVERSIONED
  --expected-conflict-sha256 HASH --receipt PATH`: reread immediately, require the
  expected state/token hash, then call SetWorkerDeploymentCurrentVersion with the
  **actual nonempty conflict token**, `build_id=ID`,
  `ignore_missing_task_queues=False`, `allow_no_pollers=False`. No flags may bypass
  those guards. Reject empty build ID for normal promotion. On stale state,
  conflict, timeout or missing poller, stop; read back to reconcile a lost response
  before any further mutation. Never blindly retry a timed-out promotion.
- `drain --deployment NAME --build-id OLD`: read-only until retirement is separately
  invoked. Require old is neither Current nor Ramping, fresh server DRAINED state,
  complete open-history listing/direct descriptions and empty queue work. Output
  a retirement receipt; this command must not scale Pods or delete versions.
- A separate, explicit initial-cutover operation owns Schedule pause/restoration.
  Preserve the entire described Schedule and use UpdateSchedule with its current
  conflict token to change only `state.paused`; PatchSchedule has no CAS field.
  Reread and verify exact action/spec/policies unchanged. Restore original paused
  state only after successful current/poller verification or full rollback; on
  failure keep an actionable receipt and perform independent restoration steps.
  Do not automatically unpause on a broken routing state. Never change the
  Schedule action to a fixed old version, trigger/backfill missed actions, or
  rewrite its five-minute interval/catchup/overlap policy.

First tests are negative guards: incomplete pagination, old pollers, wrong image,
wrong namespace/role, missing Activity poller, unexpected ramp, missing/stale
conflict token, server CAS rejection, accepted mutation with lost reply, response
redaction, and concurrent Schedule configuration change. Add positive protobuf
serialization assertions for `build_id` and both false bypass fields. Exercise
real Temporal 1.29.1 in an isolated local test service for registration, guarded
promotion and sticky/pinned history behavior; local unit tests alone are not
live deployment qualification.

### 2. Kubani per-build manifests and operator runbook

Update only the workload resource organization beneath
`infrastructure/gitops/apps/agent-platform/workloads/` and its Kustomization;
add `worker-versions/<build-id>/{sessions,reconciler}.yaml` plus a reviewed
inventory/runbook. Move the shared artifact PVC to its own retained resource so
removing one version cannot prune storage. Preserve all current mounts, resource
requests, identities, network labels, node locality and probes. Version pins are
immutable digest references paired with nonempty build IDs. Keep old versions in
Git until draining is proved. Add `tests/test_worker_versioning_manifests.py` for
pairwise-disjoint selectors, common queue/deployment mapping, pinned image/build
consistency, no empty IDs, PVC retention and same-node placement constraints.

Prepare a bounded operator-owned Flux reconciliation pause/restoration receipt
for the initial two-Deployment replacement. Preserve the original Flux annotation
value and exact object UID/spec/RV guards; no broad suspension or persistent
out-of-Git scaling. Stage future version manifests before promotion so pollers
can register as inactive. Maintain a version inventory with current, draining
and retained rollback candidates; Kubernetes readiness is not Temporal current.

### 3. Initial cutover, performed by root after review

1. Wait until no conformance batch is active. Close the submission window for
   `submit.py`, all conformance adapters and any external caller using this
   namespace; inventory callers before claiming exclusivity. Do not cancel or
   terminate existing workflows. Retain exact workflow IDs/run IDs from the
   previous batches and directly describe them, supplementing visibility reads.
2. Just after a successful scheduled cleanup action, capture the exact Schedule
   and pause it with CAS. Wait for all running Schedule actions and business
   histories to close normally. Require complete repeated open listings, direct
   descriptions of known active runs, no sandbox Pods or held cleanup work, and
   no Workflow/Activity queue backlog. Unknown callers or incomplete evidence
   abort the migration while the old workers continue serving.
3. With the Schedule held and submissions closed, reread the evidence immediately
   before replacing the old broad-selector Deployments. Create both version-A
   role Deployments using the exact image already qualified by the current batch.
   Verify same-node PVC attachment and healthy matching fresh pollers. The new
   workers register inactive until explicit promotion.
4. Promote cleanup A, then sessions A using fresh separate conflict tokens and
   both server protections. Verify Worker Deployment current versions and queue
   routing. If the second promotion fails, do not open submissions or resume the
   Schedule; reconcile actual routing and use the pre-reviewed rollback procedure.
5. Restore the original Schedule state before its next five-minute action. Verify
   its next naturally scheduled execution uses cleanup A with PINNED behavior
   and completes. If the planned window cannot fit between scheduled actions,
   abort before stopping old workers; do not silently widen the cleanup interval.
6. Open submissions and run one ordinary signed conformance session. Preserve
   history, assigned Deployment/build, matching worker Pod image/UID and normal
   cleanup evidence. This establishes the initial production configuration;
   keep the rollout gate open until coexistence is exercised below.

Initial rollback is distinct from a future version rollback. Before any versioned
history has started, a failed cutover may restore the two exact unversioned
Deployment manifests and set routing back to unversioned only via a separately
reviewed explicit operation, fresh conflict tokens and real old pollers. Once a
versioned history exists, retain its versioned worker until it closes; never use
an unversioned rollback to move that history. Restore the original Schedule only
when the selected routing is healthy. No workflow reset/repin/termination is part
of rollback.

### 4. Coexistence, promotion, rollback and drain qualification

For the next real build B (or an explicitly named same-image qualification build),
start disjoint B Deployments while A remains Current. Bind their exact images and
fresh pollers in a receipt. Run a signed, bounded long-enough ordinary session on
A; observe its real assigned deployment/build, then promote sessions B. Continue
the existing A history across another actual boundary and normal completion on
A, while a new session starts/completes on B. Capture history and actual activity
worker identities, not labels alone. Preserve confirmed-deletion/cleanup checks.

Exercise cleanup-role versioning independently: an existing bounded reconcile
execution remains pinned to cleanup A while a later naturally scheduled execution
starts on cleanup B. Keep its Schedule cadence/action unchanged. If an ordinary
cleanup execution finishes too quickly to overlap promotion, add a dedicated
bounded test workflow on an isolated qualification queue first; do not inject a
production cleanup delay or claim overlap from two sequential runs. Production
cleanup-role overlap remains open until real evidence exists.

Rollback Current from B to retained A using fresh expected-current/CAS checks and
fresh A pollers. A new session must use A; an already-running B history must
finish on B without repinning. Restore intended Current afterward and retain B
until it drains. Test failed/no-poller and stale-token promotions in the isolated
Temporal service, not by intentionally removing all production pollers.

Retire a former version only after server DRAINED, complete corroborating history
reads, no pending queue work, and a fresh drainage check after the routing change.
Do not replace this with a fixed sleep: the server's visibility/grace/refresh
windows delay status. Keep image/manifests available for rollback and closed-
history query/replay needs throughout the observed seven-day retention period;
scale-to-zero eligibility and metadata/image deletion are separate decisions.
[Official draining and closed-history query guidance](https://docs.temporal.io/production-deployment/worker-deployments/worker-versioning/sunset-and-gc).

## Review and completion evidence

Review especially the initial unversioned-history exclusion, selector migration,
Schedule CAS/restoration, timeout-after-promotion recovery, full image/build
mapping, PVC attachment locality and old-worker retention. A different actor's
concurrent change must stop the operator, never be overwritten by restoration.

Retain sanitized before/after queue/current/poller receipts, exact manifest/source
and image digests, Schedule original/restored hashes, histories proving A/B
assignment/continuation, worker Pod UID/image inventory, all cleanup results and
elapsed cutover window. Rerun relevant existing conformance after deployment.
Document an explicit failure if any proof is missing; read-only capabilities,
unit tests or readiness do not qualify live routing.

This closes the worker-deployment gap in spec 10.6/14.4 only after those live checks.
It does not independently qualify the full delegated/human T18 gate, S3 storage,
production HA, T29 node capacity, T2a's 100-start requirement or T27 host capture.
