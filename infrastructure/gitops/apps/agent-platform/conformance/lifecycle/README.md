# T24 temporary lifecycle qualification

The signed `conformance-lifecycle/v0.1.0` Agent and exact release
`conformance-lifecycle-2026-11-06-7c39c4a9` are staged unapproved under
`apps/agents/tenant-test/conformance-lifecycle`. Published asset checksums and the
canonical policy digest match. Verify all attestations and NoDrift before a
separate approval. The fixture performs no model or network calls; its ordinary
model capability has a one-token daily/session budget.

Every template here is absent from Kustomizations. The temporary worker Deployment
has zero replicas and the harness Job is suspended. Root owns activation, every
Kubernetes fault and independent restoration. The worker and harness receive only
`get` on the exact control ConfigMap; neither can write its gates or receipts.
The harness gets exact fixture reads, APS Deployment/Endpoint reads and Pod reads,
with no Secret, exec, scale, approval or status-write grant. It mounts only its
Temporal TLS identity, tenant payload key, a projected APS-audience identity and
tmp. Only the ordinary worker mounts the artifact PVC.

Prerequisites and preparation:

1. Finish any other qualification batch. Deploy reviewed matching APS, runner and
   reconciler images containing the lifecycle observer, orphan-grant cleanup and
   independent monotonic deadline fix. Use that same digest-pinned runner image
   for the temporary worker and harness. The ordinary five-minute reconciler
   Schedule and production workflow/timers must remain unchanged.
2. Integrate both exact environment entries from `observer-env-patch.yaml.in` in
   the APS workload as part of that reviewed image rollout. It is a dormant
   strategic-merge snippet, not a standalone Deployment or an active patch.
   Require both APS replicas Ready. The observer authenticates only
   `system:serviceaccount:agent-platform:conformance-harness` for
   `tenant-test/conformance-lifecycle`; it returns presence/TTL metadata, never
   credentials or cleanup writes.
3. Render `${LIFECYCLE_RUNNER_IMAGE}`, `${LIFECYCLE_RELEASE}` and a fresh UUIDv4
   `${LIFECYCLE_RUN_ID}` in the three workload/RBAC templates. Preserve Kubernetes
   `$(LIFECYCLE_RELEASE)` expansion. Verify identities, namespace, zero replicas
   and suspension before applying. Worker placement is the database node because
   its artifact PVC is RWO. The temporary Deployment must keep the same image,
   pod template and ReplicaSet owner UID through a worker-loss case.
4. Root creates `agent-platform/conformance-lifecycle-control` with only `config`
   initially. Use exact JSON below, the same runner image/run ID as the templates,
   and eight distinct fresh UUIDv4 session IDs. The raw config and original
   ConfigMap UID are pinned throughout.

```json
{"version":1,"run_id":"RUN-UUID","tenant":"tenant-test","agent":"conformance-lifecycle","release":"conformance-lifecycle-2026-11-06-7c39c4a9","queue":"conformance-lifecycle-RUN-UUID","worker_image":"registry.almckay.io/platform/session-runner:COMMIT@sha256:DIGEST","sessions":{"success":"UUID1","aps_down":"UUID2","finalizer":"UUID3","worker_kill":"UUID4","terminate":"UUID5","cancel":"UUID6","activity_crash":"UUID7","retry_exhaustion":"UUID8"}}
```

Apply the temporary RBAC and inactive workloads. Start one temporary worker and
wait for Ready, then start only this exclusive harness. The worker runs the
ordinary SessionWorkflow on the unique bound queue. Its added gates wait at real
activity heartbeats; outcomes and history are not fabricated.

Genuine grant authorization, minting and deposit are separate prerequisites.
On each stderr `grant_required`, root deposits a genuine refresh-backed grant
for the exact actor `agent-tenant-test-conformance-lifecycle` and announced
session. Publish `grant-<case>` immediately as
`{"session_id":"SESSION","handle":"gh_OPAQUE"}`. The normal reconciler can clean
an unused grant before its workflow exists, so prepare each grant just in time.
Only the opaque handle is approved workflow metadata: never put human access or
refresh tokens in this ConfigMap, logs, reports or templates. The harness must
observe genuine grant/vault presence, current access, a refresh-backed vault and
more than 600 seconds of remaining TTL before a fault. Empty or invented state
cannot qualify cleanup.

Root alone appends control values using conditional updates that pin the original
UID, resourceVersion and exact `data.config`; preserve unrelated/prior fields.
A fault receipt may only gain `restored_at`. On `baseline_ready`, follow the exact
case before appending `release-<case>-boundary1` as
`{"session_id":"SESSION","stage":"boundary1","generation":1}`:

| Case | Root action and required independent restoration |
| --- | --- |
| `success`, `retry_exhaustion` | Release boundary 1; observe ordinary success or bounded recovery exhaustion. |
| `aps_down` | Pin APS UID/spec/original replicas and Flux annotation. Pause only this Deployment, scale 2→0 conditionally, observe empty Pods/Endpoints, then release. At `cleanup_recorded_restore_fault_now`, restore exact replicas/annotation and two Ready replicas. Ordinary scheduled reconciliation must finish cleanup. |
| `finalizer` | Add only `agentplatform.io/conformance-lifecycle` to the exact sandbox UID, preserving other finalizers, then release. Wait for actual `NOT_CONFIRMED` deletion plus independent stop/grant cleanup; remove only this finalizer conditionally and require HTTP 404. |
| `worker_kill` | Release boundary 1. At `cleanup_waiting_kill_exact_worker`, delete only the exact temporary worker Pod UID. Require its HTTP 404 and a Ready same-image replacement with the same ReplicaSet owner; real activity retries must complete cleanup. |
| `terminate`, `cancel` | The harness terminates or cancels its own exact workflow after baseline; no release key or Kubernetes fault is needed. Hard termination must be followed by ordinary scheduled cleanup. |
| `activity_crash` | At baseline, delete the exact temporary worker Pod UID without releasing boundary 1. Observe the real heartbeat timeout, confirmed sandbox deletion before generation replacement, checkpoint restoration and same-image worker recovery. |

For APS/finalizer/worker faults, append `receipt-<case>` with exactly
`session_id`, `fault` (case name), `target_uid` and `started_at` (Unix seconds just
before the action). Append `restored_at` only after observed restoration. Targets
are the original APS Deployment UID, sandbox UID or temporary worker UID. The
harness independently verifies faults; receipts alone cannot pass a test.

Cleanup has a hard ten-minute qualification bound. The independent local clock
starts before held-state baseline reads and fault notification, and includes all
final receipt/404 reads. Remote timestamps cannot shorten it. Initial grant/vault
expiry must remain later than final cleanup. Expected evidence includes genuine
held state, actual activity outcomes, scheduled workflow/run provenance where
required, no generation/vault/grant/pending state, and HTTP 404 for every Pod.
The four required faults and supplemental cases must all pass. This batch does
not qualify the production eight-hour business timer.

Root must independently restore APS configuration and remove only its own test
finalizer in finally/trap handling, even if the harness times out, fails or dies.
The read-only harness cannot undo these faults. Keep the worker and ordinary
reconciler available until every bound workflow and sandbox is closed/absent.
Retain failed/partial reports; then remove the temporary worker Deployment, harness
Job, control ConfigMap and these three Role/RoleBinding pairs. Confirm two Ready
APS replicas and the exact original Flux annotation. New attempts require fresh
run, control and session identities. Staging and local tests claim no live T24 pass.
