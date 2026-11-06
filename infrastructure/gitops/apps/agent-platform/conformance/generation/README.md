# T21 separate fencing and confirmed-deletion qualification

These inactive templates implement the accepted T21 contract: stale-token fencing
and blocked deletion are separate tests. Replacement still requires confirmed
Pod deletion. None of these files is referenced by a Kustomization. This is
preparation, not live qualification evidence.

Use a verified digest-pinned runner containing zetra PR70 for both suspended Jobs.
Render `GENERATION_RUNNER_IMAGE`, a fresh UUID4 `GENERATION_RUN_ID`, and the exact
Ready releases `CONFORMANCE_RELEASE`, `GENERATION_PROBE_RELEASE` (conformance-b)
and `GENERATION_RECOVERY_RELEASE` (conformance-checkpoint). Both fixtures must
permit sessions without a delegated grant. Preserve Kubernetes `$(...)` expansion.
The temporary worker uses the existing tenant worker identity and artifact PVC;
its extra control permission is only GET. The harness has read-only observations
and no control writes, finalizer changes, Pod deletion or release mutation rights.
Existing harness log-read permissions remain required.

Root creates `agent-platform/conformance-generation-control` with only a `config`
field containing this JSON, with three distinct fresh UUID4 session IDs:

```json
{"version":1,"run_id":"RUN_UUID","tenant":"tenant-test","probe_release":"EXACT_PROBE_RELEASE","recovery_release":"EXACT_RECOVERY_RELEASE","queue":"conformance-generation-RUN_UUID","worker_image":"EXACT_DIGEST_PINNED_IMAGE","sessions":{"fence_only":"UUID1","blocked_deletion":"UUID2","recovery_control":"UUID3"}}
```

Pin the ConfigMap UID and exact configuration. Apply only the reviewed rendered
RBAC and suspended Jobs, activate the worker first, and verify its exact Job/Pod
UID, Ready container, installed image and unique queue before activating the
harness. Keep the ordinary five-minute cleanup Schedule, production workers and
APS replicas unchanged. No other fault batch or rollout may overlap this run.

Root must bind each stderr signal to the current exact harness Job/Pod/container,
run ID, case/session and stable worker UID. The signal is a coordination request,
not sufficient proof of the fault. Conditional control writes test the original
ConfigMap UID/resourceVersion and preserve `data.config` and all prior fields.

| Case | Root action and required evidence |
| --- | --- |
| `fence_only` | At `ready_fence_only`, append `command-fence_only` binding the signaled Pod and worker UIDs with action `fence_generation_2`. The trusted worker changes APS generation only. Both APS replicas must deny the same previously allowed fixed token while generation 1 remains Running; no replacement is provisioned. |
| `blocked_deletion` | At `ready_delete_for_recovery`, enter `runner.conformance_generation_operator.FinalizerGuard` with an isolated Kubernetes client configured with `retries=0`, the exact immutable Control, and signaled Pod/worker UIDs. It adds only `agentplatform.io/t21-conformance-hold`, reads it back, and appends the bound deletion command. The ordinary workflow must stop at `NOT_CONFIRMED` without generation 2. On `scheduled_delete_pending_remove_finalizer_now`, release the guard and verify actual scheduled deletion completion within the harness's unchanged 300-second bound. |
| `recovery_control` | At `ready_delete_for_recovery`, append `command-recovery_control` with action `delete_for_recovery`. No finalizer is added. The trusted worker confirms real 404 before ordinary recovery; generation 2 must complete all three boundaries. |

The command objects contain exactly `run_id`, `session_id`, `pod_uid`,
`worker_uid` and `action`. Root never fabricates worker receipts or successful
history. The harness records real Temporal activity events and correlated live
APS/gateway logs. Root removal timestamps are provenance only; elapsed cleanup
uses one harness monotonic clock, so root and worker hosts need not share a boot ID.

Before activation, root needs a separately reviewed, bounded coordinator that
keeps finalizer cleanup ownership through harness errors, ambiguous writes and
process termination. The FinalizerGuard's non-daemon expiry backstop has a maximum
720-second hold, retries exact-UID cleanup, and explicitly reports persistent
cleanup failure. Any expiry or operator error fails qualification even when
cleanup later succeeds. Never disable the backstop, pause the reconciler, trigger
an early Schedule tick or force generation 2 through blocked deletion.

In every exit path remove only this run's finalizer with exact UID/resourceVersion
conditions, preserving unrelated finalizers; independently confirm all three
workflows closed, all session Pods absent and two stable APS replicas. Keep the
worker available until cleanup is confirmed. Preserve raw failed reports and
operator receipts, then remove only these temporary Jobs, control ConfigMap and
four RBAC objects. Job deadlines are 3900 seconds; they do not relax the harness's
per-case 960-second observation and separate 240-second cleanup bounds, the
production deletion deadline, or the 300-second scheduled cleanup requirement.
