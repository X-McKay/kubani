# Agent operations: `just agent`

One command family for the day-to-day lifecycle of an applied agent. It wraps
what the November 2026 releases did by hand: copying the Agent from the source
repository, staging a published release, approving it after the controller has
verified it, and submitting an ordinary session. Every subcommand prints one
JSON document and exits non-zero on refusal, so an operator or an automated
session can act on it without parsing prose.

```sh
just agent state                                # Flux, platform pods, agents, releases, sandboxes, open PRs
just agent ls                                   # agents, readiness, the release `run` would use
just agent run db-admin --task "Assess PostgreSQL health."
just agent status --receipt ~/.local/state/kubani/agent-runs/db-admin/<run>/receipt.json
just agent sync db-admin --source ../zetra-agents
just agent check-sync --source ../zetra-agents  # offline without --source; part of validate-local
just agent stage db-admin db-admin/v0.1.2 --source ../zetra-agents
just agent approve db-admin-2026-11-10-0123abcd --ticket https://github.com/X-McKay/kubani/pull/NNN
```

The implementation is `infrastructure/scripts/ops/agent-ops.py` with the
`agent_ops` package beside it; `just test-agent-ops` runs its offline tests.
Reads use `KUBECONFIG=/home/al/.kube/config`. Nothing here applies objects,
reads Secrets, prints tokens or bypasses a release gate.

## What each command establishes

| Command | Reads | Writes | Proves | Does not prove |
| --- | --- | --- | --- | --- |
| `state` | Flux Kustomizations, platform pods, Agents, AgentReleases, tenant pods, open PRs via `gh` | nothing | the platform's current shape in one read, the thing a session handoff used to narrate | anything about history or paused work |
| `ls` | committed agent directories, live Agents and AgentReleases | nothing | which release is approved, Ready, signature-verified and drift-free right now | that a session will succeed |
| `run` | the same, plus the tenant's Ready Session Runner pod | a private run directory; one Temporal workflow via the runner | exact-run identity, confirmed completion and cleanup, the verified report | task correctness, qualification |
| `sync` | `agents/<agent>/deploy/agent.yaml` at the source checkout's clean HEAD | the committed `agent.yaml` with a provenance header | the committed Agent is byte-for-byte the source file at a named commit | that the commit is on the source's main branch |
| `check-sync` | every committed Agent, optionally the source checkout | nothing | header sha256 matches the body; with `--source`, the body matches the recorded commit and reports `stale` when HEAD differs | remote freshness |
| `stage` | the GitHub release assets, the committed Agent, the tenant signer pin | `agentrelease-<version>.yaml` plus its kustomization entry | checksums, image/predicate/bundle agreement, Agent equality, signer pin acceptance; with `--source`, manifest and lock hashes at `buildRevision` | signature or attestations (the controller verifies those after apply) |
| `approve` | the committed unapproved file and the live object | only the `approval` block | live spec equals the committed file; signature Verified by this agent's release workflow inside the tenant pin; all five attestations; NoDrift; digest equals `policySha256`; Ready is false solely for `NotApproved` | functional behavior, qualification |

## Running a session

`run` resolves the tenant from the committed directory, the release from the
live objects (exactly one approved, Ready, signature-verified, drift-free
release unless `--release` names one) and the identity mode from the release
status. Agents with `identity.mode: agent` take no grant handle; on-behalf-of
agents refuse to start without `--grant-handle` from a consented delegation.
`--task TEXT` sends `{"request": TEXT}`; `--task-json` and `--task-file` send
a document as given. Tasks are limited to 16 KiB.

The submission runs inside the tenant's single Ready legacy-pool Session Runner
pod: `agent_ops/remote_session.py` is streamed over `kubectl exec` and uses the
runner's own Temporal connection, namespace and payload codec from the pod
environment. Each remote call is bounded (40 s inside, 60 s outside) and
returns one JSON line; the host polls `status` every ten seconds until the
workflow closes or `--wait-timeout` (900 s) passes. A timeout never cancels
unless `--cancel-on-timeout` is given; the receipt still names the exact run.

Success means Temporal `COMPLETED`, result outcome `COMPLETED`, query state
`CLEANED` and cleanup exactly `{stop: OK, delete: DELETED, grant: OK}`. Only
then is the content-addressed snapshot read (at most 64 MiB, hash verified,
uncompressed tar, at most 256 members) and `workspace/report.md` (at most 16,000
bytes, strict UTF-8) copied out. Exit codes: 0 confirmed success with report,
1 failure or unconfirmed cleanup, 2 refused input, 124 local timeout.

Each run gets a new private directory, by default
`~/.local/state/kubani/agent-runs/<agent>/<UTC time>-<session prefix>/`:

| File | Content |
| --- | --- |
| `request.json` | tenant, agent, release, session id, task and bound (never the grant handle) |
| `receipt.json` | namespace, workflow id, run id, task queue, runner pod uid, remote script sha256 |
| `status.json` | the final envelope: status, query, result, cleanup confirmation |
| `report.md` | the agent's report, present only after confirmed success |
| `exec-NN.stderr` | bounded stderr of a remote call, when any |

`status`, `wait` and `cancel` take `--receipt` and operate on that exact run
only; they never submit. The runner pod's uid, container id, image id and
restart count are re-read after every call and `runnerIdentityChanged` is
reported if any differs.

The deployed session-runner image predates zetra's `agent-session-submit
--wait --report` (zetra PR #71), so the remote script carries its own bounded
wait and report reader with the same success contract. When the runner image
is bumped to include that CLI, the remote script can delegate to it.

## Registering a repository

Every agent repository, `X-McKay/zetra-agents` or one created from the zetra
template, has the same shape: `agents/<name>/` members of one uv workspace,
releases tagged `<agent>/vX.Y.Z`, signed by that repository's own
`release.yml`. Before its first release the operator registers it with a tenant:

```bash
just agent register tenant-test OWNER/REPO my-agent --source ~/git/my-agent
```

This creates `apps/agents/tenant-test/my-agent/` from the checkout (a `sync`
with the repository recorded in the header), lists it in the agents
kustomization, and regenerates the tenant's signer pin in both places it is
declared: the Namespace annotation the Registry Controller reads and the
`kyverno/tenant-signers` ConfigMap Kyverno reads. The pin is derived from the
sync headers of the tenant's committed Agents, one branch per repository bound
to exactly its own agents, so a repository can never sign another repository's
agent. `check-sync` fails when either copy differs from that derivation.
Registering the same agent from a second repository is refused; agent names are
unique across tenants because image paths are `agents/<agent>`. Commit the
result as one PR; after Flux applies the Agent, releases follow the usual
`stage` and `approve` steps. The repository needs the shared `automation`
registry credential as `REGISTRY_USERNAME`/`REGISTRY_PASSWORD` secrets, which
is a separate human step.

## Syncing the Agent

The committed `agent.yaml` is the source file's exact bytes behind three
comment lines:

```yaml
# Synced from X-McKay/zetra-agents agents/db-admin/deploy/agent.yaml at <commit>
# sha256:<digest> of the body below; do not hand-edit.
# Change deploy/agent.yaml in the source repository, then: just agent sync db-admin --source PATH
```

`sync` refuses a source checkout with uncommitted changes under the agent's
directory and reports `specChanged` so a capability change is visible in the
PR. `check-sync` runs in `just validate-local` and CI without a source
checkout, which catches hand edits; run it with `--source` before cutting a
release to catch a copy that lags the source. Kustomize strips comments, so the
header changes nothing the controller sees. All 13 agents were synced on
2026-11-09 with no rendered object change.

## Staging and approving a release

`stage` and `approve` take the source repository from the Agent's sync header;
`--repo` overrides it. With `--source`, `stage` verifies `lockSha256` against
the repository's `uv.lock` at `buildRevision`, falling back to
`agents/<agent>/uv.lock` for releases built before the workspace layout.

`stage` downloads `agent.yaml`, `agentrelease.yaml`, `policy-bundle.json`,
`predicate.json`, `SHA256SUMS` and `image` with `gh release download`, verifies
every listed checksum, and refuses when: the release is not unapproved; the
name, namespace or agent differ; the image is not a digest-pinned
`registry.almckay.io/agents/<agent>` reference equal to the `image` asset; the
predicate or bundle disagree with the release; the published Agent differs from
the committed one (sync first, or the release will never become Ready); or the
expected signer subject `.../release.yml@refs/tags/<tag>` is outside the
tenant's `subjectRegExp` in `tenant-signers.yaml`. It writes
`agentrelease-<version>.yaml` in the form the previous hand-staged files used
(yamllint and secret-scanner pragmas included) and appends it to the agent's
kustomization. Commit and merge that; Flux applies it unapproved.

`approve` is run only after the controller has reconciled the staged object.
It edits nothing unless every gate in the table above holds against the live
object, then rewrites exactly the `approval` block with `approved: true`,
`approvedBy` (the Agent owner unless `--by`), `approvedAt` and an optional
`ticket`. The edited file must parse back to the committed release plus that
block, or the command refuses. Commit and merge in a separate PR; `ls` shows
the release as runnable once Ready.

## Verification (2026-11-09)

- All 13 Agents were synced from zetra-agents `202768da`; `kubectl kustomize`
  of `apps/agents` rendered 48 identical objects before and after, and
  `check-sync --source` passed for every agent.
- `stage db-admin db-admin/v0.1.1 --source` in a disposable copy reproduced the
  committed release exactly (modulo header and pragmas) with manifest and lock
  hashes verified at `buildRevision`; in the real tree it refused the duplicate.
- `approve` against the already-approved live db-admin release refused at the
  live gate; its 19 offline tests cover every other gate.
- `just agent run db-admin --task ...` submitted one ordinary session through
  the tenant runner: `COMPLETED`, 11 boundaries, generation 1, cleanup
  `CLEANED` with stop OK / delete DELETED / grant OK, no sandbox Pod left, and
  the report plus four evidence links were copied out. `status --receipt` on
  the finished run returned the same envelope. This is a bounded deployment
  check of the tooling, not qualification.

## Boundaries

- Release signatures and attestations are verified by the Registry Controller;
  `stage` establishes asset integrity and `approve` reads the controller's
  verdict. Neither replaces the controller.
- `run` is an ordinary session, not qualification. Historical failures and the
  paused qualification matrix are unaffected by its results.
- Governed worker pools are not selectable from `run`; it submits to the legacy
  queue through the tenant's existing runner.
- Nothing here changes identities, grants, budgets or network policy.
