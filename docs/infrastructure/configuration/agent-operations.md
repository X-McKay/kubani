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
just agent consent --check investigator         # would Keycloak issue this person a depositable token; deposits nothing
just agent sync db-admin --source ../zetra-agents
just agent check-sync --source ../zetra-agents  # offline without --source; part of validate-local
just agent stage db-admin db-admin/v0.1.2 --source ../zetra-agents
just agent approve db-admin-2026-11-10-0123abcd --ticket https://github.com/X-McKay/kubani/pull/NNN
```

The implementation is `infrastructure/scripts/ops/agent-ops.py` with the
`agent_ops` package beside it; `just test-agent-ops` runs its offline tests
(`tests/test_agent_ops*.py`).
Reads use `KUBECONFIG=/home/al/.kube/config`. Nothing here applies objects,
reads Secrets, prints tokens or bypasses a release gate.

## What each command establishes

| Command | Reads | Writes | Proves | Does not prove |
| --- | --- | --- | --- | --- |
| `state` | Flux Kustomizations, platform pods, Agents, AgentReleases, tenant pods, open PRs via `gh` | nothing | the platform's current shape in one read, the thing a session handoff used to narrate | anything about history or paused work |
| `ls` | committed agent directories, live Agents and AgentReleases | nothing | which release is approved, Ready, signature-verified and drift-free right now | that a session will succeed |
| `run` | the same, plus the tenant's Ready Session Runner pod | a private run directory; one Temporal workflow via the runner | exact-run identity, confirmed completion and cleanup, the verified report | task correctness, qualification |
| `consent --check` | the committed Agent; one person's sign-in and consent at the `agents` realm's `agent-cli` client; the realm's signing keys | no file, no cluster object and nothing at the APS; at Keycloak, what any sign-in leaves: a session, the tokens issued for it and the consent answer for `agent-cli` | whether Keycloak issued that person, for that agent, an access token that meets the four conditions the APS deposit handler places on a bearer token | that a deposit or a session would succeed; it deposits nothing and never calls the APS |
| `sync` | `agents/<agent>/deploy/agent.yaml` at the source checkout's clean HEAD | the committed `agent.yaml` with a provenance header | the committed Agent is byte-for-byte the source file at a named commit | that the commit is on the source's main branch |
| `check-sync` | every committed Agent, optionally the source checkout | nothing | header sha256 matches the body; with `--source`, the body matches the recorded commit and reports `stale` when HEAD differs | remote freshness |
| `stage` | the GitHub release assets, the committed Agent, the tenant signer pin | `agentrelease-<version>.yaml` plus its kustomization entry | checksums, image/predicate/bundle agreement, Agent equality, signer pin acceptance; with `--source`, manifest and lock hashes at `buildRevision` | signature or attestations (the controller verifies those after apply) |
| `approve` | the committed unapproved file and the live object | only the `approval` block | live spec equals the committed file; signature Verified by this agent's release workflow inside the tenant pin; all five attestations; NoDrift; digest equals `policySha256`; Ready is false solely for `NotApproved` | functional behavior, qualification |

## Running a session

`run` resolves the tenant from the committed directory, the release from the
live objects (exactly one approved, Ready, signature-verified, drift-free
release unless `--release` names one) and the identity mode from the release
status. The command is the same for every agent; what it needs depends on the
identity the release reports:

| Release reports | Without `--grant-handle` | With `--grant-handle` |
| --- | --- | --- |
| `identityMode: agent` | runs with the agent's own identity | refused |
| `identityMode: on-behalf-of`, `delegationRequired: false` | runs; the session has no grant, so for each backend the Agent delegates the APS follows the Agent's `onBehalfOf.fallback`: `agent` exchanges with the agent's own identity, `deny` refuses the call | the handle is submitted with the session; preflight does not check it, and cleanup deletes the grant it names |
| `identityMode: on-behalf-of`, `delegationRequired: true` | refused | the handle is submitted with the session; preflight checks it, and cleanup deletes the grant it names |

An on-behalf-of release that does not report `delegationRequired` as true or
false is refused without a handle. An empty `--grant-handle` is refused for
every agent. The receipt records `identity` and `delegated`; `delegated: true`
means a handle was submitted, not that any call was made on a person's behalf.
On 2026-11-10 `conformance` has two runnable releases and `conformance-b`
three, so `run` needs `--release` for them. No supported path produces a
handle today; see [Grant handles](#grant-handles) before trying to run an agent
whose release requires delegation.
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
| `receipt.json` | namespace, workflow id, run id, task queue, runner pod uid, remote script sha256, the release's identity mode and whether a grant handle was submitted |
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
when the release reports `status.delegationRequired: true`. The Session Runner
checks the grant of an on-behalf-of release unless the release reports
`status.delegationRequired: false`. The Registry Controller reports true for an
Agent that declares `identity.mode: on-behalf-of` unless its
`onBehalfOf.required` is false. On 2026-11-10 the two investigator releases are
the only ones in `tenant-test` that report true. The `conformance` and
`conformance-b` fixtures are on-behalf-of with `required: false` and
`fallback: agent`; `run` submits them without a handle, and the APS then
exchanges with the agent's own identity for each delegated backend (read from
zetra `677a2de`; no such session has been run through `run`). The agent
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
| Sign in and consent to the delegation | the human whose access the agent will use | Authorization code with PKCE at the `agents` realm's public `agent-cli` client, consenting to the scope `delegation:client:agent-<tenant>-<agent>`. The same helper's `--mint` does this for Alice. `just agent consent --check <agent>` takes a real person through it, reports what Keycloak issued and discards the tokens; see [below](#checking-consent-just-agent-consent---check-agent). |
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
| delegation required, no `--grant-handle` | `run`, before a run directory exists or anything is submitted | `refused: <agent> runs on behalf of a human; pass --grant-handle from a consented delegation`, exit 2 |
| on-behalf-of release that reports neither true nor false for `delegationRequired`, no `--grant-handle` | `run`, at the same point | `refused: <agent>: release <name> does not report whether delegation is required`, exit 2 |
| `identity.mode: agent`, `--grant-handle` given | `run`, at the same point | `refused: <agent> runs with its own identity and takes no grant handle`, exit 2 |
| delegation required, handle the APS does not hold (unknown, expired or already deleted) | Session Runner preflight | the preflight activity fails as `Forbidden` (`APS GET refused with 404`); the result outcome is `FAILED` and `run` exits 1 without a report |
| delegation required, handle deposited in another tenant | Session Runner preflight | the same, with `APS GET refused with 403` |
| delegation required, handle deposited for another session id | Session Runner preflight | `Forbidden` (`delegated session without a grant`); the same outcome and exit code |

The release is resolved before the handle is looked at, so while investigator
has two Ready releases, `run investigator` without `--release` is refused for
that first. Cleanup deletes the handle a session was given whether or not
preflight accepted it, and the APS then deletes the grant that handle names.
A session submitted with a handle deposited for another session of the same
tenant therefore removes that other session's grant at cleanup: after being
refused at preflight when the release requires delegation, and after running
otherwise, because preflight never reads the handle then. zetra PR #80 changes
this; it takes effect when APS and Session Runner images built from it are
rolled.

#### Checking consent: `just agent consent --check <agent>`

`consent --check` answers one question for one person and one agent: does
Keycloak issue that person an access token that the APS deposit handler would
accept for this agent? `--check` is the only mode. Without it the command
refuses with exit 2, because depositing is not implemented.

The command refuses unless the committed Agent declares
`identity.mode: on-behalf-of`, and unless stdin, stdout and stderr are all a
terminal. The terminal check runs before anything is listened on or fetched.
It stops a run from a pipeline or a plain subprocess; a wrapper that supplies
a pseudo-terminal passes it. What a script cannot supply is the sign-in, which
the person does in their own browser. The command then:

1. Listens on `127.0.0.1` on a port the kernel picks and prints, on stderr,
   which agent is being authorised and an authorization URL for `agent-cli`.
   The URL carries PKCE S256, a random `state` and `nonce`,
   `prompt=login consent`, and the scope
   `openid agent-policy-service delegation:client:agent-<tenant>-<agent>`
   (no `offline_access`). The person opens the URL, signs in and answers the
   consent screen in their own browser. The command takes no username or
   password and fills in no form. `--browser` also hands the URL to the
   default browser; the default is to print it only.
2. Waits up to `--timeout` seconds (300 by default, 900 at most) for one
   request on the listener, then closes it. The first request that arrives is
   the only one read. It must be the callback and it must carry exactly one
   `state` that matches, in a constant-time comparison; that is checked before
   anything else in the request. An `error=` callback is a refusal that names
   the error code.
3. Exchanges the code at the token endpoint as a public client with the PKCE
   verifier. It verifies the access token and the ID token against the realm's
   published keys and issuer, and requires the ID token to carry this
   sign-in's `nonce` and the same subject. Only RS256 signatures are accepted,
   and `iss`, `sub` and `exp` must be present; expiry, not-before and
   issued-at are checked with five seconds of leeway, as the APS does.
4. Prints one JSON document on stdout.

The document holds metadata only: `agent`, `tenant`, `issuer`, `subject`,
`preferredUsername` when the token has one, `audiences`,
`hasPolicyServiceAudience`, `requiredScope`, `hasDelegationScope`,
`otherScopes` (names), `mayActSubPresent` and `mayActSub` (a service account
id), `clientType`, `undecodableClaims` (names), `accessTokenExpiresInSeconds` (null when `exp` is
not a JSON number),
`refreshTokenIssued`, `wouldBeAcceptedForDeposit` and `missing`, a list of
reasons in plain words.
Tokens, the authorization code and the PKCE verifier stay in memory. They are
not written to a file, passed on a command line, or put in the output or in an
error message.

Exit codes: 0 when `wouldBeAcceptedForDeposit` is true, 1 when it is false,
2 on a refusal (including a failed signature or issuer check, a `state`
mismatch, an `error=` callback, a request on the listener that is not the
callback and a listener failure), 124 when no callback arrived in time.

What it proves: for the person who signed in, at that moment, Keycloak issued
a token for which these four conditions hold, or it names the ones that do
not. They are the conditions the APS deposit handler places on the bearer
token: the audience includes `agent-policy-service`; `client_type` is not
`agent`; the scope includes `delegation:client:agent-<tenant>-<agent>`;
`may_act.sub` is not empty. `wouldBeAcceptedForDeposit` is true when those
four hold for a token that passed the checks in step 3 and none of the claims
the APS decodes (`azp`, `scope`, `client_type`, `agent_id`, `tenant`,
`spiffe_id`, `may_act`, `act`, `aud`, `exp`, `iat`, `nbf`) has a JSON type its
decoder rejects. That list was read from the APS verifier and its JOSE library,
not run against them, and claim names are compared exactly here while the APS
decoder matches them without regard to case.

The command's verification is not the APS's. The APS accepts ten signature
algorithms and does not require `sub`; a token it would accept but that is not
signed with RS256, or that lacks `sub`, is refused here with exit 2 and gets no
verdict.

How Keycloak behaves for a person the agent's service account has no delegate
permission over has not been observed on this realm. The conformance notes
(`infrastructure/gitops/apps/agent-platform/conformance/human/T10A.md`) say
only that the missing permission "may deny issuance of `may_act` itself".
Three outcomes are possible:

- Keycloak issues a token without the delegation scope. The command exits 1
  and the reason names the missing permission as a likely cause and the
  operator's step to grant it (the first row of the table above). It is a
  likely cause, not the only one: the scope may also be absent, or the request
  refused, when the agent has no Keycloak client or the delegation scope is
  not set up for it.
- Keycloak issues a token with the scope and without `may_act`. The command
  exits 1 with the same likely cause.
- Keycloak refuses the authorization request. The command exits 2 with
  `Keycloak returned the error <code> instead of an authorization code` and
  gives no further explanation.

What it does not prove:

- That a deposit would succeed. The command never calls the APS. The APS
  verifies the token itself and also checks the session id, tenant, agent and
  expiry in the request and that the session has no grant yet. None of that is
  exercised.
- That a session would run. Session Runner preflight, the MCP backends and
  what the person may read in Kubernetes are not touched.
- Anything about another person, another agent, or a later time. The
  permission behind the scope can change after the check.

What it leaves behind: no file, no grant and no handle. At Keycloak it leaves
what the sign-in created: the person's browser session, now with an
`agent-cli` client session, and whatever Keycloak stores for the consent
answer. The tokens are dropped from memory and nothing is revoked. The access
token expires on its own (`accessTokenExpiresInSeconds`); a refresh token, if
one was issued (`refreshTokenIssued`), stays valid at Keycloak until that
session ends, and no copy of it exists after the command exits.

The command does not revoke the refresh token because of what revocation does
in Keycloak 26.8.1, read from its source
(`DefaultRefreshTokenProvider.revokeToken`), not run: it detaches the
`agent-cli` client session inside the token's browser session and removes the
browser session when no other client session is left. A grant deposited from
the same browser session shares that client session, so revoking here would
invalidate the refresh token the APS holds for it.

The token checks use PyJWT. The `agent` recipe adds it with `uv run --with`
only when the first argument is `consent`, so the other subcommands start from
the locked environment alone, and no other subcommand imports it. As of
2026-11-10 the command has run only against the in-process fake identity
provider in `tests/test_agent_ops_consent.py`. It has not been run against the
live realm.

#### Consent has to be given at run time

Verified in zetra `677a2de`: a grant deposited before its session's workflow
exists does not last. The deposit registers the session with the APS. The
tenant's cleanup reconciler, when it is running, makes a pass every five
minutes, lists every APS session without an age filter, and treats a session
whose workflow does not exist as closed. Its next pass therefore removes the
grant. A person cannot consent in advance and hand over a handle for later;
consent and deposit have to happen as part of starting the run. Even then the
deposit comes before the workflow exists, so a reconciler pass in between
would remove the grant; whatever makes the deposit has to account for that.
No command does that yet, and how the deposit will be made is not decided.

#### Per-person prerequisites

Two things are the operator's to authorise for each person, before that
person's consent can lead to a working investigator session:

1. The Keycloak delegate permission for the agent's service account over that
   person. Without it the person is not expected to get a depositable
   token; what Keycloak does instead has not been observed (see the outcomes
   listed above).
2. Kubernetes RBAC for that person in the namespace the investigator reads.
   This is expected, not yet verified.

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
