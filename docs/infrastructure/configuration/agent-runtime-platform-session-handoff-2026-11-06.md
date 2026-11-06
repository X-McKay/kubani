# Agent Runtime Platform session handoff — 2026-11-06

Checkpoint after run 31, approximately 20:15 UTC. This document supersedes stale
session-state notes, including `/tmp/phase-b-next/ROOT-PICKUP.md`. Read it before
resuming the older general handoff. No qualification Job or sandbox remains
active. APS was independently verified at two Ready replicas. No host capture ran.

## Scope and remaining count

The user authorized completing the platform end to end, including necessary PR
merges, image releases and AgentRelease approvals. The original T26 request and
runs 10–12 documentation are complete. This is not a platform-completion claim.

For the current homelab platform scope, **16 tracked work items remain**: the
14 conformance gates below, Worker Versioning, and final integrated regression
and documentation signoff. This is a work-item count, not an estimate of PRs or
hours. T2 includes the required T2b residual measurement. Enterprise qualification
on other clusters and per-agent production quality T30 are additional scope.

| Item | Missing evidence / next action |
| --- | --- |
| T2 | Complete 100-start T2a ordering plus unpoliced-namespace negative; record T2b residual measurement. Existing Phase A report has only ten starts. |
| T27 | Fix missing-capture reporting and strict TLS-alert classification; publish corrected fixture; coordinate operator host capture during exact T4. |
| T28 | Existing report proves preflight digest refusal, not automatic controller repair within 60 seconds. Verify implementation and run the full requirement. |
| T29 | Finish bounded performance harness and measurements, including node coverage, snapshots, recovery and 20-session saturation. |
| T12 | Agent-mode coverage passes; delegated and optional native-exchange configurations still need evidence. |
| T13 | Daily-budget persistence across both gateway replacements; original and first retry attempts failed. Use a separately reviewed retry2 identity, preserving spent ledgers. |
| T14 | Delegated principal/session/decision correlation and JWT-free logs. |
| T21 | Resolve contradiction with confirmed deletion before replacement, then qualify generation fencing. |
| T23 | Deploy exact stateless-MCP fanout evidence fix and run all five checkpoint faults plus two controls. |
| T24 | Run all cleanup-failure cases with genuine refresh-backed grants; signed lifecycle fixture is Ready. |
| T10a | Prove the pinned Keycloak delegation contract and every wrong variant. Reconcile old A/B wording with the spec's later documented requester=actor decision. |
| T10 | Genuine delegated identity plus allowed/forbidden Kubernetes impersonation. |
| T16 | Revoke synthetic Alice's consent and measure denial within 300 seconds. |
| T18 | Delegated smoke session, report artifact, full cleanup. |
| Worker Versioning | Finish and qualify guarded promotion, routing, retained legacy workers, replay/drain and rollback. |
| Final signoff | Audit every spec requirement, rerun relevant integrated regressions on final pins, reconcile docs and record remaining limitations. |

T1/T3 and partial T28 evidence are historical; do not treat their old “Phase A
passed” wording as proof of the expanded current specification. T30 is explicitly
per-agent production readiness, not platform acceptance.

## Persisting user decisions and boundaries

- Use `KUBECONFIG=/home/al/.kube/config`; repositories live under `/home/al/git`,
  GitHub organization `X-McKay`; work through `gh`.
- Necessary merges, releases and AgentRelease approvals are authorized. Do not
  re-ask for these routine rollout steps. Publish from merged main, verify
  installed/source equality, pin RepoDigests, and wait for Flux/readiness.
- Agent release tags must be serial: ARC dind has OOMed during concurrent builds.
  Stage exact release assets unapproved; verify signature, all five attestations
  and NoDrift; approve in a separate PR.
- Never `kubectl rollout restart` Flux workloads; delete exact Pods where needed.
  SOPS-only secrets. Never print credentials/JWTs/private keys or read pod secrets.
  One-off Jobs, logs and exec in the specified platform/test namespaces are allowed.
- Brokers were retained. The vLLM API-key/capture rollout completed, with T6/T7
  passing. Main auto-sleep is off; fast auto-sleep remains 120-second level 1;
  leases are off. Broker PR5 merged; kubani PR242 closed and superseded by PR276.
- Prior downtime authorization applied to that rollout. No further engine/broker
  outage is needed now; ask before a new action taking one down.
- **Latest exact Keycloak approval:** user approved optional `delegation:client`
  on `agent-cli`, and two distinct Users/delegate permissions restricted to
  synthetic Alice, for `agent-tenant-test-conformance` and
  `agent-tenant-test-conformance-lifecycle`. This resolves the earlier automatic
  approval rejection for these exact objects only. No other users/actors granted.
- **Host work is deferred:** user said “lets continue and revisit this in a few
  hours.” Do not automatically restart T2a/T27 host captures. They agreed to run
  reviewed terminal commands later; coordinate readiness before launching a gate.
- This session's kernel `no_new_privs` blocks sudo even with escalation. Do not
  bypass via privileged Pods, Docker host mounts or repurposing the attestor.
- T21 decision remains open: test wording asks for generation 2 while generation
  1 deletion is finalizer-blocked, but §10.1 requires confirmed deletion before
  replacement. Recommend preserving that invariant and separating stale-token
  fencing from blocked-deletion behavior; obtain the user's contract decision.
- **Use Sol sub-agents to parallelize independent work cost effectively.** The
  user explicitly requested this for the next session. Give narrow tasks and
  isolated checkouts, avoid duplicate full-suite runs, and keep one owner for live
  operations and serial release publication.

## Current deployed baseline

Kubani main was `a1f85d4c` before this handoff branch. Zetra merged main remains
`ce7c06b`; runner, cleanup and all seven manual runner Jobs share its published
image. APS and deterministic budget backend use `e79bb04` (backend AMD64).
Exact immutable digests are in the committed workload manifests; verify actual
Pod imageIDs before another exclusive batch. No production images from open
PR62/PR63 have been deployed.

Approved Ready fixtures include conformance v0.1.7 (`88b05a89`), B v0.1.2
(`5928c578`), checkpoint v0.1.1 (`66f46e84`), lifecycle v0.1.0 (`7c39c4a9`),
budget-day-retry v0.1.0 (`5bfba9a0`), and transport v0.1.0 (`524739da`).
Their full AgentRelease names/digests are under `apps/agents/tenant-test/`.
The intentionally unsigned negative fixture must never be used as a valid agent.

## Results that must remain intact

| Run | Result and significance |
| --- | --- |
| 13 | T26 passed after fixing stale installed runner code; seed support and workspace-only restore retained. |
| 17 | T9a/T9b/T22 passed, 50 checks. |
| 19 | T20 passed; historical T15 failure preserved. |
| 20 | T25 passed, 11 sessions and 191 checks; actual wire faults/hangs and bounded worker memory. |
| 21 | Nine ordinary tests passed, 115 checks: exact T4, authentic T5, T6/T7/T8/T11, agent-mode T12, full T19, T26. |
| 22 | T15 passed, 38 checks; actual Agent disable/restore and cancellation on both replicas. |
| 23 | T13b passed, 28 checks; concurrency, tampering, restore and independent-session behavior. |
| 24 | T13 ERROR; operator acted after timeout. Original daily ledger spent 1,800, never reset. |
| 25–27 | T17 failures retained: patch failure, Job recreation race, then overly narrow generation receipt expectations. |
| 28 | T17 PASS, all 18 checks; actual outage, fail-closed traffic and restored two replicas/original Flux annotation. |
| 29 | T23 FAIL at healthy-control evidence, before faults. Session completed three boundaries and cleaned up; backend handshake fanout broke the harness's one-to-one assumption. |
| 30 | T13 ERROR at gateway replacement. Python client corrupted the single JSON log line into dict text; no gateway deletion occurred. First retry ledger is also preserved, not reset. |
| 31 | T27 ERROR. Capture never started within 240 seconds; both sessions cleaned up. Missing capture caused an additional evaluator AttributeError. TLS probe produced an unclassified response; see below. |

Runs 10–12 and findings 14–17 are already recorded. Historical model flakes
remain historical. The verified Keycloak scope-role mapping script is committed
at `infrastructure/scripts/ops/grant-map-role-client-scope.sh`.

Raw reports are `/tmp/phase-b-t26/runN.log`, with combined logs alongside.
Run28 receipts are `/tmp/phase-b-next/run28-{operator,control,components,launch}.json`.
Run29 and run31 supporting files are `/tmp/phase-b-next/run29/` and `run31/`.
Run30 has `run30-operator.json`, `run30-launch.json`, and
`run30-log-deserialization.json`. Do not commit secrets or packet data.

## Immediate Keycloak state: approved but only partially applied

Kubani PR362 merged the reviewed actor-specific helper. Read-only planning for
both actors passed. The subsequent authorized apply created the shared scope,
then failed strict verification with:

`ValueError: existing fixture configuration differs: protocolMappers`

Read-only verification after the interruption confirmed:

- Exactly one `delegation:client` scope exists.
- It is **not attached** to `agent-cli`.
- Neither `conformance-alice-actor` / `conformance-alice-delegate` nor the
  lifecycle equivalents exist.
- No mint/delegated session has been attempted after this apply.

Next: compare safe mapper configuration against the pinned Keycloak response;
fix server-normalization handling only if semantically exact. Do not weaken
comparison to accept broader scopes. Re-run the reviewed idempotent helper and
verify the final objects, then mint consented tokens directly to SOPS files.
Use `SOPS_AGE_KEY_FILE=/home/al/git/kubani/age.key`. Never display plaintext tokens.
Plans are `/tmp/phase-b-next/delegation-{conformance,lifecycle}-plan.json`.
The `*-applied.json` files are empty from failed commands, not success receipts.

The apply commands are `conformance-delegation.py --apply-scope --apply-permission`
and then `--actor agent-tenant-test-conformance-lifecycle --apply-permission`.
Authorization persists; no repeat permission question is needed for that exact scope.

## Prepared fixes and unfinished branches

| Work | Location / status |
| --- | --- |
| Runs28–30 docs | [kubani PR363](https://github.com/X-McKay/kubani/pull/363), head `9ae7ea8e`, `/tmp/phase-b-runs28-29/kubani`. Reviewed; open. Includes lossless gzip for large report, unchanged size/security hooks. Run31 still needs durable recording. |
| T13 raw log fix | [kubani PR361](https://github.com/X-McKay/kubani/pull/361), merged. `_preload_content=False`, bounded raw read, strict UTF-8 and close/release. Actual Kubernetes34.1 HTTP regression reproduced red/green; 16 tests and independent review passed. Keep all active-UID/freshness checks. |
| Scoped delegation helper | [kubani PR362](https://github.com/X-McKay/kubani/pull/362), merged. Fourteen tests / 19 subtests and independent review passed; live normalization issue above remains. |
| Attestor/guard | [zetra PR62](https://github.com/X-McKay/zetra/pull/62), `ba5e56e`, open. UID/RV JSON Patch prevents replacement-Pod attestation; trusted ordering receipts. Root independently passed 54 tests and Ruff; CI passed. Build and coordinate guard/admission/attestor pins together after merge. |
| T23 fanout | [zetra PR63](https://github.com/X-McKay/zetra/pull/63), `2858766`, `/tmp/phase-b-t23-fanout/zetra`, open. Capture emits only fixed bounded `rpc_method` enum; exact stateless handshake sequence and one real tools/call required. Root passed 57 focused tests; author full runner 755 tests and capture tests/race/vet. Requires new MCP capture and runner images together; model capture need not change. |
| T29 fixture | [zetra-agents PR27](https://github.com/X-McKay/zetra-agents/pull/27), open; no release/tag yet. Performance runtime remains incomplete. |
| Versioning initial plan | [kubani PR359](https://github.com/X-McKay/kubani/pull/359), open. Must supersede same-queue initial promotion with the tested distinct-queue migration design below. |

### T2 work in progress

Read `/tmp/phase-b-t2a/HANDOFF.md`, `PLAN.md`, and `EVIDENCE-INTERFACE.md`.
Checkout `/tmp/phase-b-t2a/zetra`, branch `feat/startup-order-conformance`, HEAD
`ba5e56e`, has six untracked files: `conformance_startup_{control,worker,sources}.py`
and matching tests. Control/worker last passed 33 tests. Sources/parser tests are
unfinished and currently fail collection due to an imported missing test helper.
No complete evaluator, runtime, host collector, CLI or manifests exist yet.

Use real UID-bound kubelet/CRI/Pod/guard/attestor evidence, not polling timestamps.
Actual journal/Events sample: `/tmp/phase-b-next/t2a-start-log-preflight.json`.
Kubelet journal is readable without sudo; CRI inspection needs the deferred host
terminal. crictl renders timestamps as RFC3339Nano despite CRI int64 nanoseconds.
Annotation acknowledgement may arrive after agent start; prove causality through
actual annotation observation and guard completion, not an invented ACK ordering.

### T27 work in progress

Run31's evaluator calls `.get` on explicit `capture_complete=None`; add a failing
regression and report missing evidence as failed checks instead of AttributeError.
The plaintext classifier treats any nonempty unknown response as `unexpected_http`.
A credential-free host diagnostic returned the exact seven-byte TLS fatal-alert
frame `15030300020232`, not HTTP. This supports investigating strict TLS-alert
recognition; it does not retrospectively prove what the Pod received. Verify the
primary protocol/pinned implementation and publish a fresh signed fixture.

Artifacts: `/tmp/phase-b-next/run31-plaintext-host-diagnostic.json` and run31 report.
Clean old source checkouts: `/tmp/phase-b-t27/{zetra,zetra-agents}`; branch from
current main for fixes. No fixes have been made yet. The old
`/tmp/phase-b-next/run31/host-capture.sh` now exits with an expiration message.
The local coordinator also needs `isinstance(row, dict)` before parsing JSON log
values; its post-report AttributeError was separate from the harness's error.

For a future attempt, write a terminal-ready marker after successful `sudo -v`,
and wait for it **before** launching the harness. Keep the exact 240-second gate
and bounded capture; no deadline widening or fabricated receipts. User deferred
this work. No raw pcap exists from run31.

### Worker Versioning

Read `/tmp/phase-b-worker-versioning/HANDOFF.md` and the evidence files it names.
`zetra` checkout there is on `feat/guarded-worker-versioning` at `ce7c06b`, with
untracked `worker_versioning.py` and `test_worker_versioning.py`; 14 focused tests
passed. Kubani `feat/inactive-worker-versions` there is clean. No live promotion,
Schedule mutation or deployment has happened.

A real isolated Temporal1.29.1 experiment proved that a new versioned queue can
coexist with the legacy unversioned queue/history without redirecting it. This
approach was approved for implementation. Preserve legacy workers/history; add
explicit governed queues, distinct non-overlapping labels/selectors, exact role
NetworkPolicies/discovery, and CAS-update only future cleanup Schedule actions.
Do not claim universal versioning while legacy callers remain. Initial same-queue
promotion remains blocked without real submission closure; empty visibility or
an operator assertion is insufficient. Respect conflict tokens, pollers, replay,
DRAINED status and seven-day query/retention needs.

Two owned local Docker containers remain idle for integration testing:
`worker-versioning-local-db` and `worker-versioning-local-server`, on an internal
network. Exact IDs are in `/tmp/phase-b-worker-versioning/local-service.json`.
Do not print private environment files or perform broad Docker prune.

### Budget retry2 and performance

Read `/tmp/phase-b-t13-retry2/broker-handoff.md` before continuing;
source/allowlist work is committed locally but not released/deployed. All three
checkouts under that directory use branch `feat/budget-day-retry2`: agents
`c9fc02e3`, platform `49486a20`, Kubani WIP `926bc245`. Independent retry2 review
has **not** completed. Fresh-cache agents checks passed; platform full runner
739 tests and final focused 58 tests passed, with Go tests/vet; Kubani four wiring
and nine signer tests passed. Assets/new pins remain missing. Keep only explicit
`conformance-budget-day-retry2` identity entries. The operator's fixed `AGENTS`
set must include it with tests. No ledger reset or reinterpretation of runs24/30.
Serially publish the signed fixture; stage and separately approve exact assets.
Bundle compatible APS/backend/runner pins and allowlists; never activate new
allowlist settings against old binaries that reject them.

T29 foundation is locally committed at `b847c85b` (56 focused tests passed);
its exact checkout is listed in the broker handoff. Runtime/CLI/evaluator/staging
remain incomplete. Fixture PR27 head is `0517eaea`, with no release yet.

T29 uses bounded fresh-Pod trials, paired cold/warm-token measurements, real
snapshots and UID-bound recovery. Literal 64 MiB workspace may exceed the 64 MiB
archive cap; record that limitation, do not raise the cap just to pass. Keep
physical-memory versus allocatable/request denominators distinct; stop owned
loads before 75% physical working set, reserve admission headroom at 70%, and
abort on stale metrics/pressure. No Docker builds during performance windows.

A local validation test accidentally overwrote uv-hardlinked SDK `step.py` at
locked SDK revision `158a170`. Shared inode 64261582 has links only in local
`.venv`/uv caches, not source files. Receipt:
`/tmp/phase-b-t13-retry2/shared-sdk-inode-receipt.json`.
Do not trust/reuse these affected environments. Use a fresh isolated
`UV_CACHE_DIR` and `UV_LINK_MODE=copy`, and atomic replacement for destructive
installed-file tests. No agent image was built from that host cache; Docker builds
install from pinned Git and exclude host venvs. Reverify installed image modules.

## Suggested resumption order

1. Read this handoff and sibling checkpoint files; inventory branches/PRs and
   confirm the cluster remains quiet. Preserve untracked work.
2. Use narrow Sol sub-agents for independent Keycloak, T23/retry2, and T2/T29/
   versioning preparation. Root owns all live changes and serial releases.
3. Finish approved Keycloak configuration normalization, verify exact grants,
   and proceed through T10a before dependent delegated tests.
4. Review/merge prepared fixes, build from merged main and verify images; deploy
   coordinated pins between exclusive batches. Finish T13 and T23; then T24.
5. Resolve T21 with the user. Complete full T12/T14/T10/T16/T18 evidence.
6. Resume T2/T27 host work only when the user is ready; finish T28/T29 and Worker
   Versioning. Record failed attempts unchanged, then final integrated signoff.

All harness Jobs are applied manually, not reconciled by Flux. Use fresh run and
session IDs, preserve exact reports, confirm normal cleanup after every attempt,
and never overlap mutation tests with releases/deployments or another batch.
