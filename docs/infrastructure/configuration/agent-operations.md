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
No supported path produces such a handle today; see
[Grant handles](#grant-handles) before trying to run an on-behalf-of agent.
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

The wait is the host's polling loop and the report reader is in the remote
script. The session-runner image deployed since 2026-11-10 (built from zetra
`541e2ef`, kubani #415) includes zetra's `agent-session-submit --wait
--report` (zetra PR #71), which the image before it did not; `run` does not
use that CLI, and the two success contracts have not been compared line by
line.

### Grant handles

A grant handle is the Agent Policy Service's (APS) reference to one human's
consented token, deposited for one session. `run` asks for `--grant-handle`
whenever the identity mode is on-behalf-of. The Session Runner checks the grant
of an on-behalf-of release unless the release reports
`status.delegationRequired: false`. The Registry Controller reports true for an
Agent that declares `identity.mode: on-behalf-of` unless its
`onBehalfOf.required` is false. On 2026-11-10 the two investigator releases are
the only ones in `tenant-test` that report true. The `conformance` and
`conformance-b` fixtures are on-behalf-of with `required: false`; `run` asks
for a handle for them all the same, so it does not run them either. The agent
`zetra-agents init` scaffolds declares `identity.mode: agent` and takes no
handle.

No supported path produces a handle that `just agent run` can use today, so an
agent that requires delegation cannot be run through it. That includes
investigator, whose need for delegation
[the platform handoff](agent-runtime-platform-handoff.md) files under Phase C.
The steps of the design
([spec](agent-runtime-platform-spec.md) section 4.3) and what exists for each:

| Step | Who performs it | State on 2026-11-10 |
| --- | --- | --- |
| Permit one user to delegate to one agent's Keycloak client | the operator, and only after Al has approved that user and that actor | `infrastructure/scripts/ops/conformance-delegation.py` does this only for the synthetic `conformance-alice` user and the clients `agent-tenant-test-conformance` and `agent-tenant-test-conformance-lifecycle`; it refuses any other actor. Merging the helper was not authority to add one (`.claude/rules/agent-platform.md`). |
| Sign in and consent to the delegation | the human whose access the agent will use | Authorization code with PKCE at the `agents` realm's public `agent-cli` client, consenting to the scope `delegation:client:agent-<tenant>-<agent>`. The only tooling is the same helper's `--mint`, for Alice. |
| Deposit the token for one session id with `POST /v1/grants` on the APS and receive the handle | the submitting client | No command in Kubani or zetra makes this call. The `agents` Gateway routes only `POST /v1/token` to the APS, and the APS NetworkPolicies admit port 9002 only from the gateway, the Session Runners and cleanup reconcilers (legacy and governed) and the conformance harness. |
| Check the handle at preflight and delete it at cleanup | the Session Runner | Deployed. |

What the code binds a handle to: the handle is `gh_` followed by 32 random hex
characters, and the APS records the session id, tenant, agent and expiry given
at deposit. The expiry must be in the future and is capped at eight hours. The
APS refuses a deposit made with an agent's own token, and accepts one only when
the bearer token carries the `agent-policy-service` audience, the scope
`delegation:client:agent-<tenant>-<agent>` for the tenant and agent named in
the deposit, and a `may_act` claim. A second deposit for the same session id is
refused with 409. The APS returns a grant only to a Session Runner it accepts
for the grant's tenant, and the runner's preflight then requires the grant's
session id to equal the session's own. `run` generates the session id itself
after its own checks and has no option to set one, so a handle deposited
beforehand cannot match the session `run` submits.

What a missing or wrong handle produces:

| Case | Refused by | Result |
| --- | --- | --- |
| on-behalf-of agent, no `--grant-handle` | `run`, before a run directory exists or anything is submitted | `refused: <agent> runs on behalf of a human; pass --grant-handle from a consented delegation`, exit 2 |
| `identity.mode: agent`, `--grant-handle` given | `run`, at the same point | `refused: <agent> runs with its own identity and takes no grant handle`, exit 2 |
| delegation required, handle the APS does not hold (unknown, expired or already deleted) | Session Runner preflight | the preflight activity fails as `Forbidden` (`APS GET refused with 404`); the result outcome is `FAILED` and `run` exits 1 without a report |
| delegation required, handle deposited in another tenant | Session Runner preflight | the same, with `APS GET refused with 403` |
| delegation required, handle deposited for another session id | Session Runner preflight | `Forbidden` (`delegated session without a grant`); the same outcome and exit code |

The release is resolved before the handle is looked at, so while investigator
has two Ready releases, `run investigator` without `--release` is refused for
that first. Cleanup deletes the handle a session was given whether or not
preflight accepted it, and the APS then deletes the grant that handle names.
A session submitted with a handle deposited for another session of the same
tenant is therefore refused and then removes that other session's grant.

## Registering a repository

Every agent repository, `X-McKay/zetra-agents` or one a person creates with
`zetra-agents init` (zetra `platform/agent-tools`; see zetra `docs/agents.md`),
has the same shape: `agents/<name>/` members of one uv workspace, releases
tagged `<agent>/vX.Y.Z`, signed by that repository's own `release.yml`. The
repository needs the shared `automation` registry credential as the secrets
`REGISTRY_USERNAME` and `REGISTRY_PASSWORD` and the variable `RELEASE_RUNNER`;
handing those over is the operator's human step. Before its first release the
operator registers it with a tenant:

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
`stage` and `approve` steps. The scaffolded agent runs with its own identity,
so its first `just agent run` takes no grant handle. An agent changed to
on-behalf-of with delegation required cannot be run yet; see
[Grant handles](#grant-handles).

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
