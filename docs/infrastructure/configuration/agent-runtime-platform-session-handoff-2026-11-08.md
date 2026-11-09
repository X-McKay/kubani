# Agent Runtime Platform session handoff — 2026-11-08

Written on November 8, America/New_York; final approvals/readiness occurred after
00:00 UTC on November 9. This is the current continuation checkpoint. It
supersedes the November 6 handoff's current-state claims and resumption order,
while preserving that document and all historical failures.

## 2026-11-09 update

Kubani #405 added `just agent` (`state`, `ls`, `run`, `status/wait/cancel`,
`sync`, `check-sync`, `stage`, `approve`); see
[agent operations](agent-operations.md). All 13 Agents now carry a sync header
and are byte-exact copies of zetra-agents `202768da` with no rendered change.
One ordinary db-admin session ran through `just agent run` and completed with
confirmed cleanup. The durable rules below and in the November 6 handoff were
lifted into `.claude/rules/agent-platform.md`, which now governs when a handoff
disagrees. Qualification JSON evidence moved to `evidence/`; links were
updated. Everything else in this document is unchanged and remains the
checkpoint for paused work.

## Start here

1. Read `.claude/rules/agent-platform.md`, then this file,
   [onboarding preflight](agent-onboarding-preflight.md),
   [MCP registry](mcp-backend-registry.md), and
   [db-admin deployment notes](db-admin-deployment-notes.md).
2. Inspect repository branches, dirty/untracked files and remote heads before
   changing anything. Use an isolated checkout; preserve older work.
3. Recheck cluster state with `just agent state` and `just agent ls`.
   This handoff records observations, not a permanent readiness guarantee.
4. Continue the user's current design/deployment priority. **Broad functional
   qualification is paused.** Do not resume fault campaigns, host capture,
   versioning promotion or benchmarks merely because an older plan says “next.”

The latest requested implementation is complete: all 13 source agents pass the
actual offline generic preflight; three corrected fixture releases are separately
approved and Ready. There is no pending build, tag, merge or approval for that
request. Do not repeat the release sequence.

## Persistent decisions and authorizations

- Prefer narrow gpt-6.1-sol sub-agents in isolated checkouts for independent work.
  Avoid duplicate full-suite runs. One primary owner handles live operations,
  merges and serial release publication.
- Work through gh. Necessary PR merges, releases and separate AgentRelease
  approvals are authorized after signature, all five attestations and NoDrift
  verification. Publish agent release tags one at a time, from merged source.
- Keep secrets SOPS-encrypted. Never print tokens, read secrets from Pods, or
  commit private reports/credentials. Operator age key, when legitimately
  required: /home/al/git/kubani/age.key.
- Never rollout restart Flux-managed workloads. Use exact Pod deletion only
  when appropriate. No new vLLM engine or broker downtime without asking.
  Brokers remain retained.
- Host T2a/T27 capture is deferred until the user coordinates terminal commands.
  Do not bypass the environment's sudo restriction through privileged containers.
- Preserve failed reports, spent budget ledgers, strict test requirements,
  unfinished branches and untracked files. Never weaken checks to obtain passes.
- **T21 decision is settled:** preserve confirmed deletion before replacement;
  test stale-token fencing separately from blocked deletion. Kubani PR #371
  records this. Do not ask the contract question again.
- The originally described Alice/conformance/lifecycle delegation fixtures were
  explicitly approved. Do not re-ask for those exact operations. The later
  consolidation proposal is a distinct change; see the paused-work section.

## Repository baseline and workspace preservation

These were the merged heads before this documentation-only update:

| Repository | Main revision |
| --- | --- |
| kubani | cce23c704cf2bf00dec7d80672859580b2020680 — PR #403 |
| zetra-agents | 202768dac41b0a9c64eed4b27f938530e57ffda5 — PR #35 |
| zetra | 87a4ee956d19ce7ab98ee1a909df9e35797972ab — PR #71 |

The original /home/al/git/kubani checkout was intentionally left clean on main
at bbe52316. **Its local main is older than GitHub main.** Do not assume a file
missing there is missing remotely. Fetch/read origin/main or create an isolated
checkout; do not reset the original checkout or discard other work.

Recent isolated checkouts remain available:

| Path | Preserved work |
| --- | --- |
| /tmp/all-agent-pass-kubani | approval branch at 072bf80a; implementation branch 95ca8254 retained |
| /tmp/all-agent-pass-source | clean detached merged source 202768d; source-fix branch fc0400b retained |
| /tmp/all-agent-pass-runner | reviewed MTU branch at 0a6c5e9f |
| /tmp/kubernetes-mcp-registry | prior Kubernetes registration implementation |
| /tmp/platform-handoff-20261108 | this documentation change |

Do not clean older /tmp workspaces. Some contain the only copies of unfinished
qualification code. Use fresh UV_CACHE_DIR and UV_LINK_MODE=copy for SDK tests;
the November 6 checkpoint records an older uv hardlink/cache contamination.

## Completed shared deployment work

| Work | Durable record |
| --- | --- |
| Scoped PostgreSQL monitoring MCP and db-admin | Kubani #388–393; zetra-agents #30–31 |
| Incremental MCP registry integrated with agentgateway, identity and network policy | Kubani #394–395 |
| Source pre-tag compatibility and reliable check failure propagation | zetra-agents #32–34 |
| Bounded session wait/resume/report CLI | zetra #71; Kubani #396 |
| Paired encrypted credential preparation and bootstrap checks | Kubani #397 |
| Generic agent onboarding preflight | Kubani #398–399 |
| Existing Kubernetes MCP registration and public RBAC status | Kubani #400 |
| Explicit model-free fixtures, signed replacements and separate approval | zetra-agents #35; Kubani #402–403 |
| Runner Docker/Kata MTU correction | Kubani #401 |

The registry supports generated container-sse-v1 backends and a bounded
existing-streamable-http-v1 profile for the existing Kubernetes MCP deployment.
Registration does not itself grant agent tools or approve a release. Use the
registry guide for incremental server addition; unsupported profiles fail closed.
Kubernetes registration preserved the rendered runtime resources and human access.
Postgres remains present; db-admin is the scoped monitoring agent, not an
unrestricted database administration principal.

The bounded CLI was verified by exact-run resume/report of an already completed
db-admin run, with zero new submit/cancel operations. It is source/operator tooling;
do not assume an unrelated deployed runtime image contains the new CLI.

The latest fixes deliberately remove inference authority from the deterministic
lifecycle, performance and transport fixtures. Source manifests explicitly use
model: null and Agent capabilities.models: []. Missing model remains an error;
ordinary models must still be granted and satisfy unchanged reservation checks.
There is no fixture-name exemption or larger token budget. Deterministic
implementations must provide their own execution behavior; the ordinary SDK
inference loop has not become a model-free workflow engine.

## Verified releases and current evidence

All four releases below were read again while preparing this handoff and were
approved, Ready, signature verified, had all five attestations and NoDrift.
Exact full immutable image/policy/manifest/lock digests remain in their committed
AgentRelease files under infrastructure/gitops/apps/agents/tenant-test/.

| Agent | Tag | Current AgentRelease |
| --- | --- | --- |
| db-admin | db-admin/v0.1.1 | db-admin-2026-11-07-3e94dc5e |
| conformance-lifecycle | conformance-lifecycle/v0.1.1 | conformance-lifecycle-2026-11-08-2d023e66 |
| conformance-performance | conformance-performance/v0.1.1 | conformance-performance-2026-11-08-32f7a43c |
| conformance-transport | conformance-transport/v0.1.2 | conformance-transport-2026-11-08-6b1f8f93 |

The three fixture tags were published serially from zetra-agents 202768d.
PR #402 staged exact assets unapproved. Controller signature, exact issuer/tag
subject, five attestations, matching policy digest and NoDrift were checked
before approval preparation and again before merging separate PR #403.
After Flux reconciliation all three replacements were Ready.

Historical releases are retained. Their old policies may now drift against the
updated Agent definitions; do not reuse them or relabel their historical evidence.
No qualification session was started by these changes.

Verification performed:

- Final actual offline CLI matrix: **13/13 pass**, all exit zero, valid receipts,
  empty stderr, no crashes. Inputs were clean Kubani 95ca8254 and merged source
  202768d; prospective tags stayed absent and both trees were unchanged.
  Approval subsequently changed only approval metadata and documentation.
- Source just check: 319 tests plus lint/layout checks; all 13 CI image builds.
  Three fixture installed-driver checks passed against the pinned SDK.
- Generic preflight: 24 tests; fixture templates: seven tests; GitOps builds,
  scoped hooks, CI and independent Sol reviews passed.
- All 13 live Agent UIDs and identity identifiers remained unchanged. The only
  Agent specification delta was removal of those three model grants.
- All eight Flux Kustomizations were Ready at completion and again at handoff.
  The final request left tenant-test without sandbox Pods.
- db-admin v0.1.1 previously completed a bounded ordinary session with all four
  diagnostics, evidence-derived report verification and complete cleanup. See
  its deployment notes; this is not database-health certification.

Preflight proves configuration compatibility. Release readiness proves separate
release gates. Neither is whole-platform functional qualification.

## Release-infrastructure finding

Lifecycle publication attempt 1 failed during apt with memory allocation failure;
attempt 2 failed downloading git. Both logs are retained. The Kata guest's eth0
MTU was 1230 while Docker bridge/build interfaces were 1500; runner-level public
downloads were fast while nested apt stalled.

PR #401 makes dind validate and inherit the guest MTU through the exact pinned
image's original entrypoint. It preserves images, Kata isolation, job guard,
network policies, resources and storage limits. Fresh guest, bridge and build
interfaces all reported 1230; lifecycle then published on attempt 3, followed by
successful serial performance and transport releases. **The historical OOM
cause is not established.** Do not “fix” it by raising limits or weakening isolation.

An extra whole-repository hook invocation also found baseline vendored YAML
line-length/secret-scanner findings and a Python 3.14/Ansible incompatibility.
Changed-file hooks, normal scoped pre-push checks and CI passed. The broad failure
log is retained; no unrelated baseline exceptions were added.

## Paused qualification and older unfinished work

Read the [November 6 handoff](agent-runtime-platform-session-handoff-2026-11-06.md)
for historical context, then the newer private local checkpoints before touching
qualification work:

- /tmp/runtime-resume-evidence/ROOT-CHECKPOINT.md — append-only; later entries
  supersede earlier “active,” “pending” and “not deployed” statements.
- /tmp/runtime-resume-evidence/current-qualification-checkpoint.md.
- [Public Phase B results](agent-runtime-platform-phase-b-qualification.md).
- docs/plans/2026-11-06-worker-versioning-distinct-queues.md and
  docs/plans/2026-11-06-worker-versioning-live-qualification.md.

Do not carry forward the November 6 “16 remaining” count as current. T13 run32
passed and is recorded in PR #376. The later private checkpoint also records a
T28 run34 pass; its detailed receipts/publication remain separate. The last saved
original-scope count was **14**, not a fresh specification audit in this session:
T21/T23/T29; delegated T10a/T10/T12/T14/T16/T18/T24; host T2/T27;
Worker Versioning; final signoff. Recheck retained evidence before revising the
public qualification matrix. These items are not instructions to resume testing.

Important supersessions and holds:

- Both originally approved Alice actor fixtures were applied after the initial
  mapper/reference fixes. The old “scope only, permissions absent” state is stale.
  Later evaluation found conflicting separate permissions under global UNANIMOUS.
  Open Kubani **#374** proposes an Alice-only consolidation and awaited a separate
  decision. Do not apply that distinct proposal based on the old fixture approval.
  No valid delegated refresh-backed fixture was established in the selected saved
  checkpoints; verify live state read-only before any future action.
- Kubani #380 merged other-tenant helper source, not authorization to create/mint
  an additional actor fixture.
- T23 run33 failed healthy-control transport correlation before fault cases.
  Preserve it. T21 run35 failed before activation due to SDK incompatibility;
  exact temporary resources were later removed. Neither is a pass.
- Worker Versioning progressed beyond local experiments: retained A/B workers,
  promotion/rollback, scheduled cleanup and drain observations exist privately.
  Actual seven-day query/replay retention, fresh canonical history equality and
  universal caller coverage remain open. Do not retire retained workers/history.
  Recheck current routing and Schedule state before any mutation.
- Older checkpoints record automatic approval-review rejections/holds on public
  T23/T29/T21/digest/run34 payloads. This progress handoff does not publish those
  payloads or resolve those holds. Inspect the exact current proposal and recorded
  rejection before any attempted publication; never route around a rejection.
- Open #359 is an older versioning plan, not authority to replace the reviewed
  distinct-queue migration with same-queue promotion.

Selected preserved work was inventoried, not repaired:

| Path | Observed state / purpose |
| --- | --- |
| /tmp/runtime-resume-t29 | head 2a1d55d; modified runtime/CLI/collector/tests and untracked journal implementation/tests |
| /tmp/runtime-resume-t29-activation | head 6becd49c; inactive templates |
| /tmp/runtime-resume-t23-capture | head 67dbe3e; later capture work |
| /tmp/phase-b-t2a/zetra | head ba5e56e; six untracked startup source/test files |
| /tmp/phase-b-worker-versioning/zetra | head ce7c06b; two untracked early versioning files |
| /tmp/runtime-resume-evidence/t29-operator | private unfinished operator/coordinator; read its checkpoint before use |

These are pointers, not a claim that every old branch was inventoried or is ready
to merge. Later checkpoints may supersede an early implementation.

## Evidence locations and sensible continuation

Current completed work:

- /tmp/all-agent-pass-evidence/STATE.md — final COMPLETE entry is authoritative.
- matrix-final/report.json and report.md under that directory.
- releases/*/controller-staged.json, controller-premerge.json and
  controller-ready.json; verified-ready-summary.json; final-preservation-summary.json.
- lifecycle-release-failed.log and lifecycle-release-retry-failed.log, successful
  workflow logs, runner-network-observation.json and runner-mtu-after.txt.
- /tmp/kubernetes-mcp-evidence/STATE.md — prior registry/live registration evidence.
- /tmp/preflight-all-evidence/ — historical initial matrix.
- /tmp/platform-handoff-evidence-20261108/ — fresh handoff read-only snapshots.

Local /tmp evidence is not portable and must not be treated as committed data.
If absent in a new environment, use merged PRs, release assets and committed guides;
do not invent unavailable receipts or call unobserved qualification passed.

The user's priority has been generic deployment improvements that benefit all
agents, while discussing system design before further qualification investment.
The registry, credential preparation, bounded CLI and generic preflight work are
already implemented. There is no selected next implementation item in this
checkpoint. Start by summarizing this state and agreeing the next shared
improvement; do not silently resume the paused qualification backlog.
