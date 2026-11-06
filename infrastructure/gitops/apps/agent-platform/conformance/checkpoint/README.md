# T23 temporary checkpoint qualification

These templates are inactive, suspended, and absent from every Kustomization.
They require the reviewed T23 harness/worker runner image and the signed
`conformance-checkpoint` v0.1.1 (or later corrected) fixture. The failed v0.1.0
release is historical and must not be reused. The exact v0.1.1 release
`conformance-checkpoint-2026-11-06-66f46e84` is staged unapproved in
`apps/agents/tenant-test/conformance-checkpoint`. Its asset checksums and policy
digest match the published release. Verify all release attestations, then
separately approve after SignatureVerified and NoDrift. This directory grants no
approval.

The worker runs the ordinary SessionWorkflow and activities, with test-only
observed barriers on a unique queue. The harness runs in agent-platform under
`conformance-harness`; it only reads evidence and patches the one exact control
ConfigMap. The temporary worker runs under the existing `session-runner` identity
and deletes only its bound Pod name/UID after a gate-specific command, then
confirms HTTP 404. No production queue, tenant NetworkPolicy or cluster policy changes.

Use the same new digest-pinned runner image for the production runner/reconciler,
temporary worker and harness before an exclusive batch. Both templates require
`CHECKPOINT_RUNNER_IMAGE`, `CHECKPOINT_RELEASE` and `CHECKPOINT_RUN_ID` to be
rendered explicitly; an old image lacking T23 is not a valid substitute. The
worker and harness remain on the database node because the artifact PVC is RWO.
Only the worker mounts it writable. The harness mounts Temporal TLS, the tenant
payload key, tmp and read-only artifacts; no APS/backend key is mounted.

The operator prepares a fresh ConfigMap named
`agent-platform/conformance-checkpoint-control`. Its only initial data key is
`config`, containing JSON:

```json
{"version":1,"run_id":"RUN-UUID","tenant":"tenant-test","agent":"conformance-checkpoint","release":"SIGNED-READY-RELEASE","queue":"conformance-checkpoint-RUN-UUID","sessions":{"control-before":"UUID1","a":"UUID2","b":"UUID3","c":"UUID4","d":"UUID5","e":"UUID6","control-after":"UUID7"}}
```

Generate every UUID with `uuid.uuid4()`; all seven session IDs must be distinct.
The run ID must equal the worker's `agentplatform.io/checkpoint-run` label. The
control UID and exact config are pinned throughout; replacing or editing them
fails the run. Render the three `.yaml.in` files into a separate local directory
by replacing only their three `${CHECKPOINT_*}` placeholders. Preserve the
Kubernetes `$(CHECKPOINT_RELEASE)` container argument expansion. Inspect the
rendered image/release/identity and suspension before applying anything.

The operator creates the exact Role/RoleBindings and ConfigMap, applies the two
suspended Jobs, starts the worker, and waits for its one Pod to be Ready with zero
restarts. Start the harness only after the production and test worker imageIDs
match and no other conformance batch is active. The harness validates the signed
release and invokes seven exact sessions: healthy control, five faults, healthy
control. It does not edit an Agent, release, Deployment, Secret or NetworkPolicy.

The five gates are before exec; after the real MCP read but before `.done`; after
`.done` and activity completion before snapshot; after a real first storage chunk;
and after boundary 1 checkpoint acceptance before boundary 2 exec. Before authorizing
a kill, the harness requires matching in-flight Temporal history and completed
read evidence where applicable. Every completed MCP transport is correlated across
APS, gateway and capture by unique nonempty decision ID; control traffic is not
counted as tool reads. The report retains checkpoint hashes, stage observations,
partial-copy bytes, exact UID deletion receipts and repeated-read counts.

A pass requires all five faults, both healthy controls, complete evidence,
confirmed normal cleanup for every session and no test Pod left. Local tests and
manifest staging do not claim a live T23 pass. Preserve failed/partial reports;
use a new control object/run/session IDs for any new attempt.

The operator independently cleans up after success, failure, timeout or harness
crash. Cancel any still-running exact bound workflows while the temporary worker
is available, wait for ordinary cleanup, and use the normal trusted reconciler
if needed. Confirm no bound sandbox remains, then delete the temporary worker and
harness Jobs, ConfigMap and both Role/RoleBindings. Never remove a finalizer,
rewrite status, or force replacement to manufacture success.
