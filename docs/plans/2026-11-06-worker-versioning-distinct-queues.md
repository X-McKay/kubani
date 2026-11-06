# Distinct worker queues: approved migration continuation

This supersedes the initial same-queue cutover proposal in
[kubani PR359](https://github.com/X-McKay/kubani/pull/359), while preserving its
historical read-only inventory. No live promotion or deployment is authorized by
these templates alone; root owns release and coordinated live operations under
the user's existing authorization. This is not a platform-completion claim.

The local Temporal1.29.1 experiment and initial adapters in
[zetra PR67](https://github.com/X-McKay/zetra/pull/67) support a separate
`governed-v1` pool. Historical SessionInput payloads default to `legacy`; existing
queues, workers, workflows, artifacts and queryable histories stay. A new version
never becomes current on an old unversioned queue. The current deployment is
resolved per exact role/pool/build, using Temporal routing plus a verified
Deployment -> ReplicaSet -> Ready Pod/image owner chain; an arbitrary Pod list is
not current-worker evidence.

| Role | Legacy queue | Governed queue | Governed Temporal deployment |
| --- | --- | --- | --- |
| Session | sessions-tenant-test | sessions-tenant-test-governed-v1 | session-runner-tenant-test-governed-v1 |
| Cleanup | cleanup-tenant-test | cleanup-tenant-test-governed-v1 | cleanup-reconciler-tenant-test-governed-v1 |

The inactive [templates](../../infrastructure/gitops/apps/agent-platform/worker-versions/README.md)
use different app labels and build-specific immutable selectors. Six matching
role/pool NetPol additions grant both halves of each path, while existing workers
retain their original policies. Shared RWO artifacts require same-node placement
with the retained legacy runner; storage migration is separate work.

Rollout sequence, owned by root:

1. Review/merge source, publish serially from merged main, and compare installed
   worker/operator modules to that source. Pin actual RepoDigest/build in rendered
   zero-replica manifests; validate selectors, identity, storage and both policy
   halves. No legacy image can be used as a governed candidate.
2. Add reviewed resources without replacing/deleting legacy Deployments. Start
   the governed candidate separately. Verify exact imageIDs, UIDs, configuration,
   rollout and both fresh Workflow/Activity pollers for each new role queue.
   Verify old workers and old unversioned queue pollers remain healthy.
3. Prepare and promote each governed Temporal deployment with fresh expected
   current/conflict token, no ramp, `allow_no_pollers=false` and
   `ignore_missing_task_queues=false`. Never reuse stale receipts or retry an
   uncertain write. Read back the exact version and verify actual new execution
   routing before directing governed submissions.
4. Change only future cleanup Schedule actions through the raw protobuf adapter,
   preserving opaque input/action options, five-minute/SKIP settings, state, memo
   and search attributes. Require exact prior queue, Schedule fingerprint and
   nonzero eight-byte conflict counter. Temporal1.29.1 acknowledges stale update
   signals but ignores them asynchronously: RPC success alone is not a pass.
   Verify exact post-update fields and a future governed cleanup execution.
5. Continue old in-flight workflows on old workers. Add exact role/pool/current
   version discovery to every affected conformance observer before using those
   observers to qualify restarts, captures, checkpoints or cleanup. Legacy
   submitters stay explicitly legacy; do not claim universal Worker Versioning
   until each submission path is migrated and separately verified.
6. Exercise pinned replay, version fencing and actual DRAINED/reachability status
   with retained builds. Empty workflow visibility, an operator assertion, or
   no recent poll is not proof that a worker can be retired. Retain every old
   history's compatible worker and query support through the required seven-day
   retention/query window; record server status and actual history replay.
7. Test rollback by changing future governed routing to a retained compatible
   build and, if necessary, CAS-routing future cleanup actions to healthy legacy.
   New routing never migrates existing pinned histories. Preserve their workers
   and artifacts until their own drain/retention checks pass.

Local evidence proves only queue separation, guarded adapter behavior, stale CAS
state refusal and Schedule field preservation on the owned test service. It does
not prove real Kubernetes network enforcement, installed-source rollout, replay,
production drain, seven-day retention, cleanup cadence or integrated acceptance.
All those gates remain open. No active Kustomization, legacy image pin, Schedule,
secret, AgentRelease, namespace, Role or production workload changes in this PR.
