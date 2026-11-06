# T15/T20 temporary qualification fixtures

These files are deliberately outside every Kustomization. The operator creates
and removes them for one explicit harness run. All test orchestration executes
inside the `agent-platform` harness Job (spec 15.4), using a signed, approved
`conformance-b` release containing `probe_revocation`.

Render `REVOCATION_RELEASE` in `rbac.yaml.in` to that exact release name. Confirm
its policy and pod-template ConfigMap names match the two named grants. The
temporary Role permits only the fixture Agent, release and Policy mutations;
the release image PATCH is always a server-side dry-run. It grants no Pod
mutation, exec, secret access, status write, or cluster-wide policy mutation.

Before starting, verify there are no conformance-b sandboxes and exactly two
Ready APS replicas. Apply the rendered Role/RoleBinding and `delete-hold.yaml`.
The Policy is initially inert. Add these harness arguments to the existing Job:

```text
--tests T15,T20
--revocation-fixture-release <reviewed-conformance-b-release>
--allow-revocation-mutations
```

The harness temporarily pauses Flux reconciliation on only conformance-b via
its resource annotation. It restores the exact original Agent spec and annotation,
waits for the release to become signed/Ready/no-drift, verifies the original
policy digest and ConfigMap content hashes, and requires a fresh successful
session. Concurrent fixture edits are errors and are never overwritten.

For T15 cancellation, the harness changes only the existing Policy's one rule
to match the exact test Pod name and UID, with its conformance-b label. The rule
only denies DELETE. Real workflow cancellation invokes the normal runner stop
and deletion activities concurrently. A matching Kyverno PolicyViolation Event,
a still-Running pod with no deletionTimestamp, and real gateway 403 responses
prove that the stop path revokes the active sandbox while deletion is denied.
The harness restores the inert rule in shielded cleanup and invokes the existing
trusted cleanup reconciler if needed; pod absence is a pass gate.

Both APS replicas must supply correlated allow/deny evidence. Disable timing
uses a conservative request-to-observation upper bound including log delivery.
For cancellation, the one-second gate starts at the first actual APS stop event,
not the workflow cancellation request; cancellation-to-observation latency is
reported separately. A later idempotent stop must not reset the clock. The
matching HTTP 403 must come from the first stop's replica, with one millisecond
added for truncated decision timestamps. If the first truncated decision
precedes the stop's precise timestamp, sampling continues for a later ordered
pair; missing or greater-than-one-second evidence fails. Both replicas still
need actual HTTP 403s, and the held Pod must remain Running through the measured
stop. T15 repeats with the same two warmed replicas. Model summaries, missing
Pods and transport errors never count as denials. Run 19's first-round failure
is historical and requires a new live report after the evaluator correction.

The operator must independently delete the Policy after the Job, including on
crash or timeout, then confirm all test sessions are closed, trigger the ordinary
cleanup reconciler if needed, and confirm no conformance-b sandboxes remain.
Remove the temporary RoleBinding and Role. Check the Agent reconciliation
annotation, enabled state, release Ready/no-drift, policy digest and ConfigMaps
against the saved baseline; repair any failed restoration through the reviewed
GitOps source. A failed cleanup/restoration gate cannot be reported as a pass.

This fixture has no live qualification result until the reviewed images are
released and the operator runs the Job.
