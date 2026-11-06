# Root-owned live Worker Versioning qualification

This is a reviewable execution plan, not executed evidence. Wait until the active
exclusive conformance batch is cleaned up. Root owns all merges, serial builds,
Flux changes, namespace configuration and Temporal mutations. No host capture,
engine/broker outage, global context change or privilege bypass is involved.
Initial adapters/templates are zetra PR67 and kubani PR373; operational CLI is
[zetra PR68](https://github.com/X-McKay/zetra/pull/68). Local evidence establishes
only the explicitly recorded test-service paths. Seven-day evidence remains open.

## Pins and private operator

Record two genuinely reviewed merged source/release versions A and B. Verify
installed modules against each exact source and the image RepoDigest before any
new Pod can poll; do not relabel an old pre-WORKER_POOL binary. A/B images must
both contain distinct-queue support; the operator image must contain PR68. Record
all existing legacy Deployment/Pod UIDs, imageIDs, queue routing and Schedule state.
The renderer's historical-image denylist is not provenance verification and does
not reject every newer but still pre-pool image; manual source equality is required.

Set actual values locally without printing credentials:

```sh
set -euo pipefail
export KUBECONFIG=/home/al/.kube/config
# Set VERSIONING_SOURCE_A/B (full merged commits), VERSIONING_IMAGE_A/B
# (published registry.almckay.io/platform/session-runner@sha256:...), and
# VERSIONING_LEGACY_IMAGE from verified installed source/pins.
VERSIONING_BUILD_A="b-${VERSIONING_SOURCE_A:0:12}"
VERSIONING_BUILD_B="b-${VERSIONING_SOURCE_B:0:12}"
test "$VERSIONING_BUILD_A" != "$VERSIONING_BUILD_B"
python infrastructure/scripts/ops/render-worker-versions.py \
  --runner-image "$VERSIONING_IMAGE_A" --source-commit "$VERSIONING_SOURCE_A" \
  --output /tmp/versioning-a-reviewed
python infrastructure/scripts/ops/render-worker-versions.py \
  --runner-image "$VERSIONING_IMAGE_B" --source-commit "$VERSIONING_SOURCE_B" \
  --include-operator --output /tmp/versioning-b-reviewed
kubectl kustomize /tmp/versioning-a-reviewed > /tmp/versioning-a-rendered.yaml
kubectl kustomize /tmp/versioning-b-reviewed > /tmp/versioning-b-rendered.yaml
```

Review concrete zero-replica manifests and policy halves. Stage A/B Deployments
with build-specific disjoint selectors in Flux, keeping legacy resources/pins,
ServiceAccounts, old queues and artifacts. NetPol additions are shared across
builds and must be referenced once, not duplicated in one Kustomization. Start
candidate A/B through separate reviewed replica changes; never restart a Flux
workload imperatively. Verify real same-node RWO mounts/ownership and harmless
concurrent write-once artifact access. A newly Ready Pod alone is not a poller.

Review/apply only the optional `operator.yaml` bundle as a bounded one-off Job.
It waits idle, has a one-hour deadline/backoff0, read-only inventory RBAC, existing
TLS/key projections and exact API/Temporal NetPols. It cannot mutate Kubernetes
workloads or read Secrets via API. Root may execute the following commands only
after binding VERSIONING_OPERATOR_POD to the single Ready Pod controlled by the
exact current Job UID `worker-versioning-operator-$VERSIONING_BUILD_B`; refuse
replacement/extra Pods. Verify operator module hashes against source and record
its UID/imageID. No secret contents enter receipts. The Job's evidence directory
is /tmp/versioning, mode0700; files are0600.

```sh
versioning_op() {
  kubectl --kubeconfig /home/al/.kube/config exec -n agent-platform \
    "$VERSIONING_OPERATOR_POD" -c operator -- \
    agent-worker-versioning --tenant tenant-test "$@"
}
versioning_op current --role sessions --pool legacy \
  --image "$VERSIONING_LEGACY_IMAGE" --output /tmp/versioning/legacy-sessions.json
versioning_op current --role cleanup --pool legacy \
  --image "$VERSIONING_LEGACY_IMAGE" --output /tmp/versioning/legacy-cleanup.json
```

Use a bounded wait for actual fresh Workflow AND Activity pollers, exact version,
Pod owner UIDs and imageIDs. Never set allow_no_pollers/ignore_missing_task_queues
or use an operator assertion as a replacement. Any guard failure stops rollout.
For every mutation below, exit3/uncertain stops subsequent actions; preserve its
pending journal and reconcile actual routing before preparing another operation.

## First governed version and real retained session

```sh
for VERSIONING_ROLE in sessions cleanup; do
  versioning_op prepare --role "$VERSIONING_ROLE" --build-id "$VERSIONING_BUILD_A" \
    --image "$VERSIONING_IMAGE_A" --output "/tmp/versioning/$VERSIONING_ROLE-a-plan.json"
  versioning_op promote --plan "/tmp/versioning/$VERSIONING_ROLE-a-plan.json" \
    --journal "/tmp/versioning/$VERSIONING_ROLE-a-journal.jsonl" \
    --output "/tmp/versioning/$VERSIONING_ROLE-a-result.json"
done
versioning_op current --role sessions --pool governed-v1 \
  --image "$VERSIONING_IMAGE_A" --output /tmp/versioning/current-a.json
```

Use the already signed Ready conformance-checkpoint fixture, agent mode/no grant.
Generate fresh UUID4 VERSIONING_SESSION_A and VERSIONING_RUN_A, then submit from
the same operator connection environment:

```sh
kubectl --kubeconfig /home/al/.kube/config exec -n agent-platform \
  "$VERSIONING_OPERATOR_POD" -c operator -- agent-session-submit \
  --tenant tenant-test --agent conformance-checkpoint --release "$VERSIONING_CHECKPOINT_RELEASE" \
  --session-id "$VERSIONING_SESSION_A" --worker-pool governed-v1 --max-boundaries 3 \
  --task "{\"checkpoint_case\":\"b\",\"run_id\":\"$VERSIONING_RUN_A\"}"
```

Record the returned exact workflow ID and its first run ID via DescribeWorkflow.
Require actual RUNNING, query status.boundaries=1 and a started/pending
run_boundary Activity before promotion; collect a passing history-receipt bound
to A. The fixture's caseb pauses generation1/boundary1 for120s after its real MCP
read, but normal workers do not forward its stderr stage marker. Do not invent a
read_complete observation or credit T23 coverage from this hold. Stop if the
workflow closes/times out before promotion; retain the failed attempt.

```sh
versioning_op history-receipt --role sessions --build-id "$VERSIONING_BUILD_A" \
  --image "$VERSIONING_IMAGE_A" --workflow-id "$VERSIONING_WORKFLOW_A" \
  --run-id "$VERSIONING_TEMPORAL_RUN_A" --output /tmp/versioning/a-before-b.json
versioning_op prepare --role sessions --build-id "$VERSIONING_BUILD_B" \
  --image "$VERSIONING_IMAGE_B" --output /tmp/versioning/sessions-b-plan.json
versioning_op promote --plan /tmp/versioning/sessions-b-plan.json \
  --journal /tmp/versioning/sessions-b-journal.jsonl --output /tmp/versioning/sessions-b-result.json
```

Cancel only that exact synthetic workflow after B promotion, using the root-owned
operator API. This intentionally closes CANCELLED rather than claiming a happy
fixture completion. Ordinary SessionWorkflow cancellation performs APS stop,
confirmed sandbox deletion and grant cleanup; no manual Pod deletion is needed.
Bind cancellation to both IDs and verify real server status and query results:

```sh
kubectl --kubeconfig /home/al/.kube/config exec -i -n agent-platform \
  "$VERSIONING_OPERATOR_POD" -c operator -- python - \
  "$VERSIONING_WORKFLOW_A" "$VERSIONING_TEMPORAL_RUN_A" <<'PY'
import asyncio,json,sys
from runner.worker import connect
from temporalio.api.workflowservice import v1 as api
async def main():
    client=await connect('tenant-test')
    workflow_id,run_id=sys.argv[1:]
    handle=client.get_workflow_handle(workflow_id,run_id=run_id)
    before=await client.workflow_service.describe_workflow_execution(api.DescribeWorkflowExecutionRequest(namespace='agents-tenant-test',execution={'workflow_id':workflow_id,'run_id':run_id}))
    assert before.workflow_execution_info.status==1
    await handle.cancel()
    for _ in range(150):
        info=(await client.workflow_service.describe_workflow_execution(api.DescribeWorkflowExecutionRequest(namespace='agents-tenant-test',execution={'workflow_id':workflow_id,'run_id':run_id}))).workflow_execution_info
        if info.status!=1:break
        await asyncio.sleep(1)
    else:raise RuntimeError('exact synthetic cancellation deadline')
    assert info.status==4
    status=await handle.query('status')
    assert status['state']=='CLEANED'
    assert status['cleanup']=={'stop':'OK','delete':'DELETED','grant':'OK'}
    print(json.dumps({'workflow_id':workflow_id,'run_id':run_id,'status':'CANCELLED','cleanup_confirmed':True}))
asyncio.run(main())
PY
versioning_op history-receipt --role sessions --build-id "$VERSIONING_BUILD_A" \
  --image "$VERSIONING_IMAGE_A" --workflow-id "$VERSIONING_WORKFLOW_A" \
  --run-id "$VERSIONING_TEMPORAL_RUN_A" --output /tmp/versioning/a-after-b.json
versioning_op replay --role sessions --build-id "$VERSIONING_BUILD_A" \
  --workflow-id "$VERSIONING_WORKFLOW_A" --run-id "$VERSIONING_TEMPORAL_RUN_A" \
  --output /tmp/versioning/a-replay.json
```

Independently verify exact sandbox absence and APS session/grant cleanup. Use an
operator source whose workflow source digests match retained A; replay against an
unrelated binary is not installed-source evidence. No raw history/payload is copied.

## B, future cleanup and rollback

Submit a fresh healthy checkpoint `checkpoint_case: control` to governed B, with
fresh UUIDs and the same signed release/max_boundaries3. Require COMPLETED, all
three boundaries, cleanup, exact B history-receipt and matching source replay.
Prepare/promote cleanup B separately; create a fresh Schedule plan and route only
its future action queue. Observe the next actual scheduled cleanup execution via
DescribeSchedule.info.recent_actions and DescribeWorkflowExecution: exact queue,
structured deployment B, real start time, completion and history-receipt. Measure
the unchanged five-minute cadence; do not reset, trigger early, pause/unpause or
widen the gate to manufacture a tick. Preserve all opaque inputs/options/state
and old legacy cleanup executions. Inspect raw server metadata only in memory.

For rollback, start a second caseb hold on B and collect its actual open B
history-receipt. Newly prepare retained A and invoke `rollback --plan ...` with a
new journal. It uses the same candidate/image/poller/CAS guard, never a bypass.
Cancel the exact held B workflow by the bounded procedure above, proving its
later cleanup tasks stay B; new healthy control submitted after rollback must
route A. Replay both closed exact histories and retain each worker. Roll back
future cleanup to a newly prepared retained cleanup version, or CAS-route its
future Schedule action to healthy legacy using a fresh Schedule plan. Existing
pinned histories must not migrate. Every failure/timeout remains in the report.

## Drain, retention and final signoff

Read `inspect-drain` for each no-longer-current build, with an unchanged bounded
observation deadline chosen from the pinned server's actual grace/refresh config.
Require actual DRAINED plus direct correlated closed runs; record empty visibility
as a limit, never drain proof. Record namespace retention configuration. Keep
compatible workers, queues, artifacts, certificates/codec access and closed-query
support through the required seven-day window. Re-run exact queries and matching
source replay at recorded intervals and at the end of the actual retention
window. Do not fast-forward time, shorten grace or replace elapsed observations
with an assertion. If history expires before the measured requirement, retain
that failure and resolve namespace policy with root; no seven-day pass is inferred
from configuration alone. The CLI always reports retirement_allowed=false and
provides no scale/delete action.

Copy only sanitized plans/journals/receipts/source hashes from /tmp/versioning,
run unchanged security/size hooks, and preserve run failures. Remove only the
exact temporary operator Job/Pod and its operator-only RBAC/policies after
archiving receipts; retain legacy and governed workers/policies required by
histories. Audit every submission/observer path before claiming universal Worker
Versioning: legacy-default callers remain legacy, and existing app-name-only
conformance observers do not qualify governed workers. Final integrated checks
must use exact current-version discovery and final installed pins. This plan's
local counterparts do not satisfy real Kubernetes, storage, cadence or seven-day
gates by themselves.
