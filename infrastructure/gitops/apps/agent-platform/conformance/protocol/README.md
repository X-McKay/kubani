# T25 protocol fixture qualification

The signed `conformance-protocol/v0.1.0` release is approved under
`apps/agents/tenant-test/conformance-protocol/`. Its Agent and AgentRelease are
semantically identical to the release assets, whose SHA256SUMS were checked.
Both tenant signer declarations pin its exact release-workflow/tag identity.
The controller verified all five attestations and `NoDrift` at 2026-11-06
17:31:51 UTC. Staging was kubani#336; approval followed in a separate change.

`../../workloads/conformance-protocol-job.yaml` is a manual template, outside
every Kustomization. Applying it starts a run. It pins runner `d7950de`, with
the T25 harness and worker memory audit. Confirm the tenant runner and cleanup
reconciler use the same digest before applying the Job.
The release must be approved, signed, Ready and drift-free. Run the batch
exclusively with no other tenant sessions or worker rollouts: process-wide
memory samples cannot establish this gate when another session overlaps.

The harness uses the normal Temporal client certificate and tenant payload key.
Its new tenant Role permits only `get` on this exact release and `list` on Pods
to confirm cleanup. Existing namespace-local `conformance-harness` permissions
already allow worker Pod discovery and log reads in `agent-platform`; no extra
worker privilege is added. T25 adds no Pod writes, exec, Secret API reads or
status writes. It does not mount the artifacts PVC or model backend key.

The Job selects only T25 with an explicit fixture Agent/release and a
1,800-second session timeout. It runs eleven sessions: a healthy control, then
each of five actual wire faults followed by another healthy control. The hang
uses the production 290-second deadline through all three generations; allow
roughly twenty minutes for the batch and retain the complete report. The Job's
3,600-second active deadline leaves room for normal cancellation and cleanup.

Qualification requires trusted Temporal checkpoint/delete/fence ordering,
confirmed cleanup and pod absence, stable worker identity/restarts, and complete
bounded RSS/high-water/cgroup evidence. Local tests and a signed release do not
establish a live T25 pass. After a crash or deadline, verify workflow closure and
cleanup convergence through the ordinary reconciler before recording the outcome.

The first live qualification is [run 20](../../../../../../docs/infrastructure/configuration/agent-runtime-platform-phase-b-qualification.md#run-20-protocol-faults-and-bounded-worker-memory-first-qualify-t25),
2026-11-06 17:52:15–18:13:40 UTC: eleven sessions and all 191 checks pass,
including real 290-second hang deadlines, confirmed recovery ordering, bounded
RSS/high-water and zero worker restarts. Its exclusive rollout hold is released.
