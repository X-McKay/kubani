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

Both APS replicas must supply correlated allow/deny evidence. Timing uses
nanosecond timestamps: disable-to-observed-403 is a conservative upper bound
including log delivery, and the cancellation gate additionally requires both
replicas' 403s to be observed within one second of the cancellation request.
This is stricter than stop-to-403 alone. The report separately records the
actual APS stop event to a correlated HTTP 403 on that same replica, adding
one millisecond for truncated decision timestamps. Delays or missing evidence
fail qualification; model summaries, missing pods and transport errors never
count as 403s. T15 repeats with the same two warmed replicas.

The operator must independently delete the Policy after the Job, including on
crash or timeout, then confirm all test sessions are closed, trigger the ordinary
cleanup reconciler if needed, and confirm no conformance-b sandboxes remain.
Remove the temporary RoleBinding and Role. Check the Agent reconciliation
annotation, enabled state, release Ready/no-drift, policy digest and ConfigMaps
against the saved baseline; repair any failed restoration through the reviewed
GitOps source. A failed cleanup/restoration gate cannot be reported as a pass.

This fixture has no live qualification result until the reviewed images are
released and the operator runs the Job.
