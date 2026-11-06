# T17: explicit APS outage and restoration

This is an exclusive operator-controlled qualification. The harness has read-only
Kubernetes permissions and never scales the APS. The operator helper deliberately
scales the shared APS from two replicas to zero, then restores it. Wait for other
conformance sessions and the exclusive T25 run to finish before using it.

The signed `conformance-b/v0.1.2` release is
`conformance-b-2026-11-06-5928c578`. Its asset checksums are verified; staging keeps
`approval.approved: false`. Before approval, require controller-produced
SignatureVerified=True with all five expected `verifiedSigner.attestations`,
and PolicyDrift=False with reason NoDrift. Approval is a separate reviewed
change retaining the operator identity and ticket. Then require Ready=True.

The manual `../../workloads/conformance-fail-closed-job.yaml` is suspended and
excluded from all Kustomizations. It pins combined runner `d7950de`, including
zetra#50. Align worker/reconciler images to the same digest before launching.
It mounts only Temporal credentials,
the payload key, the read-only artifact PVC and temporary storage. It carries no
backend key or projected IdP/APS assertion credential.

Apply `rbac.yaml` manually. It adds only named Deployment/Endpoints/receipt
ConfigMap reads in agent-platform and get on the exact fixture release in
tenant-test; existing Pod/list/log grants remain. No harness principal gains
scale, patch, exec, status or Secret rights. The receipt ConfigMap is created by
the operator helper, outside Flux, and its UID is pinned for the entire run.

The following commands are examples for the operator. Always supply the explicit
kubeconfig; the helper never changes the current context. Choose a fresh 16-hex
marker and an unused local state path. Keep that file until restoration is verified.

```sh
python infrastructure/scripts/ops/t17_aps_outage.py prepare \
  --kubeconfig /absolute/path/to/kubeconfig \
  --marker 0123456789abcdef --state /tmp/t17-0123456789abcdef.json
```

`prepare` reads the original APS Deployment UID, spec digest, replica count and
exact Flux reconcile annotation, writes a 0600 recovery file, and creates fresh
`conformance-aps-outage-control`. It refuses an existing receipt ConfigMap; archive
and remove the prior run's receipt explicitly before beginning another run.
It does not pause Flux or scale. Render the Job marker to exactly this value,
verify the new runner digest and approved fixture, apply the Job, then explicitly
unsuspend it. Start the operator control loop:

```sh
python infrastructure/scripts/ops/t17_aps_outage.py run \
  --kubeconfig /absolute/path/to/kubeconfig \
  --state /tmp/t17-0123456789abcdef.json
```

`run` pins the Job UID and its owned Pod UID, verifies the exclusive T17 selection
and marker, and waits for the harness's `baseline_ready` phase. It then disables
Flux reconciliation **only for the APS Deployment** using its annotation, with
a UID JSONPatch test and atomic storage resourceVersion precondition, and
requests zero replicas with an expected-replica test. The fresh receipt schema is
`t17-v2`: `pause`, `down`, `up`, and `resume` are append-only phases. Each records
start/acknowledgement nanoseconds and the before/after resourceVersion, generation,
replica count and SHA256 of the compact JSON reconcile-annotation scalar (or null).
The original generation and annotation digest are pinned at preparation. No raw
annotation enters the shared receipt. After 12 seconds of observed empty
Pods/Endpoints, it restores two replicas and waits for `replicas_restored` before
restoring the original Flux annotation and appending `resume`.

Annotation updates also advance Deployment generation: run27 observed
6→7→8→9→10 for baseline/pause/down/up/resume. The updated harness requires those
exact recorded transitions, including the final resume generation and annotation
hash, without assuming equal resourceVersions between phases (status updates
advance them). An originally disabled annotation produces explicit pause/resume
no-ops. Every phase retains its actual response evidence; a read overlapping a
mutation may match only an adjacent recorded state. Run27's original failure is
retained; it is not retroactively reclassified. Deploy the matching v2 runner
before another qualification. Old v1 local state is accepted only for restoration,
never a new `run`. Receipt fields and object identities cannot be replaced silently.

The helper's finally path handles exceptions, Ctrl-C, SIGTERM and SIGHUP. Replica
and Flux-annotation restoration are attempted independently, with fresh identity,
spec and resourceVersion checks before bounded retries. Only the API server's
exact optimistic-lock Conflict for this Deployment is retried, at most three
attempts. Each attempt reads and checks the object again. Generic invalid-request,
admission, authorization, timeout and unknown failures are not retried. The helper
sets the previously read resourceVersion in the patch so storage reports a stale
version as Conflict; a JSONPatch resourceVersion test instead yields a generic
invalid request that cannot safely identify a concurrency conflict.

Safe status/reason/category, operation and attempt metadata are retained in the
local state file's `operation_errors`; raw stderr, submitted objects and captured
output are not retained or printed. Those diagnostics do not add a successful
scale receipt. A lost PATCH response or missing receipt never permits fabricating
successful evidence. Even if the
receipt is lost, configuration restoration is attempted first. Unrelated spec,
UID, replica-count or Flux-annotation changes are not overwritten. A successful
`restored` result means the original desired configuration was observed; actual
Ready Pods/Endpoints and valid traffic remain separate harness/operator checks.
After process death or a failed restoration, use the preserved local state:

```sh
python infrastructure/scripts/ops/t17_aps_outage.py restore \
  --kubeconfig /absolute/path/to/kubeconfig \
  --state /tmp/t17-0123456789abcdef.json
```

Confirm APS two Ready replicas, expected Endpoints, exact original Flux annotation,
no leftover sandbox and Job completion independently. Retain the report and local
operator receipt. Remove only this run's manual Job, receipt and temporary RBAC
once evidence is retained. The helper does not delete those records automatically.

T17 requires exactly five requests per second for 180 seconds by default. The signed
probe pins one agent token with enough lifetime and records every real response,
without retries or bodies. Starting one second after the scale-down **request**,
every request must return 403 until scale-up starts, including during shutdown.
Timeouts, dropped requests, log gaps and scheduling gaps fail. Final evidence
requires a stable observed zero-Pod/empty-Endpoint window, two new Ready APS Pod
UIDs, successful recovery traffic, one gateway response per trace, and confirmed
session cleanup. Synchronize operator, observer and sandbox clocks. Local tests,
staging or a successful restore do not establish a live T17 pass.
