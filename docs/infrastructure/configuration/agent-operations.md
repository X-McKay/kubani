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
just agent consent investigator --session <id>  # the person's half of a `run` that is waiting for consent
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
| `run` | the same, plus the tenant's Ready Session Runner pod; for a release that requires delegation and a run started from a terminal, one person's sign-in and consent | a private run directory; one Temporal workflow via the runner; for a release that requires delegation, one grant at the APS for that session, made from the person's consent | exact-run identity, confirmed completion and cleanup, the verified report | task correctness, qualification |
| `consent --check` | the committed Agent; one person's sign-in and consent at the `agents` realm's `agent-cli` client; the realm's signing keys | no file, no cluster object and nothing at the APS; at Keycloak, what any sign-in leaves: a session, the tokens issued for it and the consent answer for `agent-cli` | whether Keycloak issued that person, for that agent, an access token that meets the four conditions the APS deposit handler places on a bearer token | that a deposit or a session would succeed; it deposits nothing and never calls the APS |
| `consent --session` | the committed Agent; the run directory of a `run` waiting on this machine; one person's sign-in and consent; the realm's signing keys; the tenant's Ready Session Runner pod | one grant at the APS for the waiting session; `consent.json` in that run directory (no token, no handle); at Keycloak, what any sign-in leaves | that the APS accepted that person's token for that session, tenant and agent | that the session will run, or that the person's own access is enough for the task |
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
| `identityMode: on-behalf-of`, `delegationRequired: false` | runs; the session has no grant, so for each backend the Agent delegates the APS follows the Agent's `onBehalfOf.fallback`: `agent` exchanges with the agent's own identity, `deny` refuses the call | the handle is submitted with the session; preflight does not check it, and cleanup deletes the grant it names only if that grant was deposited for this session id; otherwise the grant step fails as `Forbidden` (see "Grant handles") |
| `identityMode: on-behalf-of`, `delegationRequired: true` | asks the person for consent and runs with the grant deposited from it: inline when started from a terminal, otherwise it waits for `just agent consent` (see "Consent for a release that requires delegation") | the handle is submitted with the session; preflight checks it, and cleanup deletes the grant it names only if that grant was deposited for this session id; otherwise the grant step fails as `Forbidden` (see "Grant handles") |

An on-behalf-of release that does not report `delegationRequired` as true or
false is refused without a handle. An empty `--grant-handle` is refused for
every agent. The receipt records `identity`, `delegated` and `consent`;
`delegated: true` means a handle was submitted or a grant was deposited for
the session, not that any call was made on a person's behalf.
On 2026-11-10 `conformance` has two runnable releases and `conformance-b`
three, so `run` needs `--release` for them. A release that requires delegation
is run by asking the person for consent at run time; see
[below](#consent-for-a-release-that-requires-delegation). As of 2026-11-10 that
path has run only against test stand-ins.
`--task TEXT` sends `{"request": TEXT}`; `--task-json` and `--task-file` send
a document as given. Tasks are limited to 16 KiB.

The submission runs inside the tenant's single Ready legacy-pool Session Runner
pod: `agent_ops/remote_session.py` is streamed over `kubectl exec` and uses the
runner's own Temporal connection, namespace and payload codec from the pod
environment. The script and its request both travel on the standard input of
`kubectl exec`; the command line is the same for every call, so nothing a
request carries appears in a process listing. Each remote call is bounded (40 s inside, 60 s outside) and
returns one JSON line; the host polls `status` every ten seconds until the
workflow closes or `--wait-timeout` (900 s) passes. A timeout never cancels
unless `--cancel-on-timeout` is given; the receipt still names the exact run.

Success means Temporal `COMPLETED`, result outcome `COMPLETED`, query state
`CLEANED` and cleanup exactly `{stop: OK, delete: DELETED, grant: OK}`. Only
then is the content-addressed snapshot read (at most 64 MiB, hash verified,
uncompressed tar, at most 256 members) and `workspace/report.md` (at most 16,000
bytes, strict UTF-8) copied out. Exit codes: 0 confirmed success with report,
1 failure or unconfirmed cleanup, 2 refused input, 3 nobody consented in time
(nothing was deposited or submitted), 124 local timeout.

Each run gets a new private directory, by default
`~/.local/state/kubani/agent-runs/<agent>/<UTC time>-<session prefix>/`:

| File | Content |
| --- | --- |
| `request.json` | tenant, agent, release, session id, task and bound (never the grant handle) |
| `receipt.json` | namespace, workflow id, run id, task queue, runner pod uid, remote script sha256, the release's identity mode, whether a grant handle was submitted or a grant deposited, and how consent was obtained (never a token or a handle) |
| `status.json` | the final envelope: status, query, result, cleanup confirmation; `NOT_SUBMITTED` with a reason when the run ended before a workflow started |
| `report.md` | the agent's report, present only after confirmed success |
| `exec-NN.stderr` | bounded stderr of a remote call, when any |
| `consent.json` | written by `consent --session` after the APS accepted the deposit: session id, agent, tenant, the person's subject id, whether a refresh token was issued, the grant's expiry, when the deposit was made (never a token or a handle) |
| `waiting.lock`, `deposit.lock` | empty lock files of a run that waited for consent |
| `consent-exec-NN.stderr` | bounded stderr of the consent command's remote call, when any |

`status`, `wait` and `cancel` take `--receipt` and operate on that exact run
only; they never submit. The runner pod's uid, container id, image id and
restart count are re-read after every call and `runnerIdentityChanged` is
reported if any differs.

The wait is the host's polling loop and the report reader is in the remote
script. The deployed session-runner image (built from zetra `18aee61`, kubani
#419) includes zetra's `agent-session-submit --wait --report` (zetra PR #71),
as every image since `541e2ef` (kubani #415) has; `run` does not use that CLI,
and the two success contracts have not been compared line by line.

### Consent for a release that requires delegation

When the release reports `delegationRequired: true` and no `--grant-handle`
is given, `run` needs one person's consent before it submits. It chooses the
session id, writes `request.json`, and then takes one of two paths. A run of
an own-identity agent, of an agent whose delegation is optional, or with
`--grant-handle` reaches neither and behaves as it did before.

**Started from a terminal** (stdin, stdout and stderr are all a TTY, and
`--await-consent` is not given). `run` prints, on stderr, the agent, tenant,
release and session id and an authorization URL. The person who started it
opens the URL and answers the consent screen. The sign-in is the one
`consent --check` performs ([steps 1 to 3](#checking-consent-just-agent-consent---check-agent))
with one difference: the URL carries `prompt=consent`, so an open Keycloak
session is reused and the consent screen is still shown every time.
`--browser` also hands the URL to the default browser. `run` checks the token
against the four conditions `consent --check` reports and, if one fails,
refuses with exit 2 without sending the token anywhere. Otherwise it makes
one remote call, which deposits the token for the session id and starts the
workflow.

**Started without a terminal, or with `--await-consent`.** `run` signs nobody
in. It prints one line on stderr and waits up to `--consent-timeout` seconds
(300 by default, 900 at most):

```text
investigator acts on behalf of a person and this run cannot sign anyone in (not started from a terminal, or --await-consent). Within 300 seconds that person runs, in a terminal on this machine: just agent consent investigator --session <id>
```

`--run-dir DIR` is added to the printed command when `--out` put the run
directory outside the default location. The person runs the printed command
in their own terminal. `consent --session`:

1. Refuses, before anyone is asked to sign in, unless the committed Agent is
   on-behalf-of, stdin, stdout and stderr are all a TTY, the session id is a
   lower-case UUID, and a `run` of that agent on this machine is alive and
   still waiting for that session.
2. Prints the task from the run's `request.json` (cut at 2,000 characters),
   then the agent, tenant, release and session id and the authorization URL.
   The sign-in is the same as for a run started from a terminal.
3. If the token meets the four conditions, deposits it through its own remote
   call and writes `consent.json` into the run directory. If it does not, the
   command exits 1, lists the reasons under `missing` and deposits nothing;
   the run keeps waiting.

`run` learns that the grant exists from `consent.json` and from nothing else:
it looks for the file twice a second. The file is written only after the APS
accepted the deposit, and it is renamed into place, so it is never seen half
written. `run` then makes one remote call, which finds the grant by session
id and starts the workflow. Two lock files keep the two commands from
crossing: `run` cannot give up while a deposit is in progress, and a second
`consent` for the same session is refused.

If nobody consents in time, `run` exits 3 with status `NOT_SUBMITTED`. No
workflow was started and no grant was deposited, and a `consent` that arrives
afterwards is refused before the sign-in. A run started from a terminal
exits 3 in the same way when the sign-in is not completed in time.

The awaited path asks more of the person than a sign-in. The run directory is
private to the operating-system user who started `run`, and the deposit is
made with `kubectl exec` into the Session Runner pod. So the person has to be
at a terminal on the machine where `run` waits, as that user, with a
kubeconfig that may exec into that pod. Today that is the operator consenting
to a session that an automated session started. There is no path yet for a
person who has no such access.

#### Where the token and the handle go

The person's token goes from their browser to the command's loopback
listener, stays in the command's memory, and is written to the standard input
of `kubectl exec`. The remote script sends it to the APS as the bearer token
of `POST /v1/grants` on port 9002, with the refresh token (or null) and the
expiry in the body. The token is never placed on a command line, in a file,
in the command's output, in the receipt or in an error message. The remote
script reaches the APS without a proxy and without following a redirect, and
reports a failure as one of a fixed list of messages.

The grant handle never reaches the host. The APS returns it to the remote
script inside the pod:

- For a run started from a terminal, the same remote call places it in the
  workflow input.
- For an awaited consent, the consent command's remote call discards it. The
  remote call `run` makes afterwards lists the APS's sessions with the Session
  Runner's own projected ServiceAccount token (`GET /v1/sessions`), takes the
  handle listed beside the session id, reads that grant and requires it to
  name the same session, tenant and agent, and then places the handle in the
  workflow input.

No zetra change was needed for this: the listing already reports the handle
to the runner. The handle remains in the Temporal workflow input, as it does
with `--grant-handle`.

#### Refresh tokens and how long the grant lasts

The access token lives 300 seconds. Whether Keycloak issues `agent-cli` a
refresh token for this sign-in has not been observed (the request does not
ask for `offline_access`, which the client is refused). Both answers are
handled, and the command says which one it got:

- **A refresh token was issued.** It is deposited with the access token, and
  the deposit asks for the longest expiry the APS allows, eight hours. The APS
  refreshes the access token when less than 120 seconds of it remain (read
  from zetra `18aee61`, not observed). Refreshing works only while the
  person's Keycloak session lasts; the realm sets the client session's idle
  time to 600 seconds and its maximum to eight hours (read from the realm
  configuration, not observed).
- **No refresh token was issued.** The deposit carries null, and its expiry
  is the access token's own. The agent can act for the person for about five
  minutes after the sign-in; a call after that is refused at the APS. `run`
  prints a line saying so on stderr, and `consent --session` puts it in the
  `note` field of its output.

Either way the receipt records `refreshTokenIssued` and `grantExpiresAt`.
Nothing is revoked at Keycloak, for the reason given under
[`consent --check`](#checking-consent-just-agent-consent---check-agent).

#### What the receipt records about consent

`consent` in the receipt is null when the run asked nobody. Otherwise it
holds `mode` (`inline` for a run that signed the person in itself, `awaited`
for one that waited for the consent command), `subject`, `subjectSource`,
`refreshTokenIssued` and `grantExpiresAt`.

`subject` is the `sub` claim of the person's token, Keycloak's opaque id for
the user. It is recorded because it says who consented, the APS already logs
it at deposit, and `consent --check` already prints it. The username is not
recorded. For an inline run the subject comes from the token `run` verified.
For an awaited run `run` never sees the token and copies the subject from
`consent.json`, a file any process of the same operating-system user could
have written; `subjectSource` says which of the two it was. The receipt holds
no token and no handle.

#### What can go wrong

| Case | Result |
| --- | --- |
| nobody runs the consent command within `--consent-timeout` | `run` exits 3, `NOT_SUBMITTED`; nothing was deposited or submitted |
| the sign-in of a run started from a terminal is not completed in time | the same |
| Keycloak issues a token that fails one of the four conditions, run started from a terminal | `refused: the token Keycloak issued would not be accepted for deposit, so nothing was deposited or submitted: <reasons>`, exit 2; the run directory holds only `request.json` |
| the same, in `consent --session` | exit 1 with `deposited: false` and the reasons under `missing`; the run keeps waiting until its timeout |
| the sign-in of `consent --session` is not completed in time | exit 124 with `deposited: false`; the run keeps waiting until its timeout |
| the APS refuses the deposit | `refused: remote submit failed: deposit refused: <reason>` (`remote deposit failed` from the consent command), exit 2; no workflow, no receipt, no `consent.json` |
| `consent.json` exists but the APS holds no grant for the session when `run` looks | `run` exits 1, `NOT_SUBMITTED`, `consent was recorded but the policy service no longer holds a grant for this session; run again and consent again`; no receipt |
| the workflow cannot be started after the grant was deposited or found | the remote script removes the grant, naming this session, if no workflow exists for it; `run` exits 2; the next run needs a new consent |
| a remote call does not answer within 60 seconds | `refused: remote <action> did not answer within 60 seconds; whether it took effect is not known`, exit 2; a grant left without a workflow is removed by the cleanup reconciler |
| `--await-consent` on a run that would ask nobody | refused, exit 2, before a run directory exists |
| `consent --session` without a terminal, for an own-identity agent, for a session no live run on this machine waits for, or after consent was already given | refused, exit 2, before the sign-in |

The APS's refusals of a deposit are reported as: the token belongs to an
agent, not a person; the token lacks this agent's delegation scope; the token
names no agent allowed to act for the person; the policy service did not
accept the token; the policy service rejected the request; this session
already has a grant.

#### What is and is not verified (2026-11-10)

Tested offline by `just test-agent-ops`:

- The host side, against the in-process fake identity provider and fake
  cluster in the test files: one test for each identity row (own identity,
  optional delegation, required with inline consent, required with awaited
  consent, required with `--grant-handle`), the refusals and timeouts above,
  and that no token, token segment, authorization code or PKCE verifier is in
  any file, command line, printed line or output, while the access token is
  in the standard input of exactly one remote call.
- The remote script, started as a subprocess the way `run` starts it, against
  a stand-in for the APS: the deposit request, the lookup by session id, each
  refusal, the removal after a failed start, and that neither its output nor
  its stderr holds a token or a handle. `temporalio` and the `runner` package
  are small stand-ins in that test.

Read from zetra `18aee61`, not run: the APS routes, bodies and status codes
the remote script relies on; that the APS accepts the Session Runner's
ServiceAccount for the session listing and the grant read; the refresh
behaviour; the reconciler's passes.

Not verified, and not verifiable without a person's own sign-in: anything
against the live realm, APS or cluster. That covers whether Keycloak shows
the consent screen on a reused session, whether it issues a refresh token,
whether a real person's token carries the scope and `may_act`, whether the
APS accepts the deposit, whether the session passes preflight, and whether
investigator can then read what the person may read. No session whose release
requires delegation has been run through `run`.

### Grant handles

A grant handle is the Agent Policy Service's (APS) reference to one human's
consented token, deposited for one session. When the release reports
`status.delegationRequired: true`, `run` needs a grant for the session: it
makes one from the person's consent (above) or takes a handle with
`--grant-handle`. The Session Runner
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

`run` makes the deposit itself, from the person's consent at run time, so no
handle has to exist beforehand. As of 2026-11-10 that path has run only
against test stand-ins: no deposit has been made at the live APS, and
investigator, whose need for delegation
[the platform handoff](agent-runtime-platform-handoff.md) files under Phase C,
has not run a session. The steps of the design
([spec](agent-runtime-platform-spec.md) section 4.3) and what exists for each:

| Step | Who performs it | State on 2026-11-10 |
| --- | --- | --- |
| Permit one user to delegate to one agent's Keycloak client | the operator, and only after Al has approved that user and that actor | `infrastructure/scripts/ops/conformance-delegation.py` does this only for the synthetic `conformance-alice` user and the clients `agent-tenant-test-conformance` and `agent-tenant-test-conformance-lifecycle`; it refuses any other actor. Merging the helper was not authority to add one (`.claude/rules/agent-platform.md`). |
| Sign in and consent to the delegation | the human whose access the agent will use | Authorization code with PKCE at the `agents` realm's public `agent-cli` client, consenting to the scope `delegation:client:agent-<tenant>-<agent>`. The same helper's `--mint` does this for Alice. `just agent run` and `just agent consent --session` take a real person through it and deposit the result. `just agent consent --check <agent>` takes a real person through it, reports what Keycloak issued and discards the tokens; see [below](#checking-consent-just-agent-consent---check-agent). |
| Deposit the token for one session id with `POST /v1/grants` on the APS and receive the handle | the submitting client | `just agent run` (started from a terminal) and `just agent consent --session` make this call from inside the tenant's Session Runner pod, and the handle stays in that pod; see [above](#where-the-token-and-the-handle-go). Not yet made against the live APS. The call cannot be made from outside the cluster: the `agents` Gateway routes only `POST /v1/token` to the APS, and the APS NetworkPolicies admit port 9002 only from the gateway, the Session Runners and cleanup reconcilers (legacy and governed) and the conformance harness. |
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
beforehand cannot match the session `run` submits. That is why the consent
path is part of `run`: the deposit is made for exactly the session id `run`
chose.

What a missing or wrong handle produces:

| Case | Refused by | Result |
| --- | --- | --- |
| delegation required, no `--grant-handle` | nobody: `run` asks the person for consent | see [What can go wrong](#what-can-go-wrong); when nobody consents in time, exit 3 with nothing deposited or submitted |
| on-behalf-of release that reports neither true nor false for `delegationRequired`, no `--grant-handle` | `run`, before a run directory exists or anything is submitted | `refused: <agent>: release <name> does not report whether delegation is required`, exit 2 |
| `identity.mode: agent`, `--grant-handle` given | `run`, at the same point | `refused: <agent> runs with its own identity and takes no grant handle`, exit 2 |
| delegation required, handle the APS does not hold (unknown, expired or already deleted) | Session Runner preflight | the preflight activity fails as `Forbidden` (`APS GET refused with 404`); the result outcome is `FAILED` and `run` exits 1 without a report |
| delegation required, handle deposited in another tenant | Session Runner preflight | the same, with `APS GET refused with 403` |
| delegation required, handle deposited for another session id | Session Runner preflight | `Forbidden` (`delegated session without a grant`); the same outcome and exit code |

The release is resolved before the handle is looked at, so while investigator
has two Ready releases, `run investigator` without `--release` is refused for
that first.

Cleanup runs for the handle a session was given whether or not preflight
accepted it, and preflight reads the handle only for an on-behalf-of release
that does not report `delegationRequired: false`. Before 2026-11-10 that let a
session submitted with a handle deposited for another session of the same
tenant remove that other session's grant; on the governed worker pools it
still does (see below). The APS and Session Runner images built from zetra PR
#80 (`18aee61`, rolled by kubani #419 on 2026-11-10) bind cleanup to the
session id:

- The runner reads the grant first. If the APS shows it bound to another
  session id, the runner sends no delete and the grant step fails as
  `Forbidden`.
- Otherwise the runner's delete names its own session id, and the APS answers
  403 with reason `session`, removing nothing, when that is not the session
  the grant was deposited for. The cleanup reconciler names the session the
  APS listed beside the handle.
- Such a session ends with cleanup `grant: FAILED:Forbidden` and state
  `NOT_CONFIRMED`, which `run` reports as unconfirmed cleanup with exit 1.
- The `session_started` record in the runner's log no longer carries the
  handle. Logs written before the roll still hold handle and session id pairs.

The binding is to the session id alone: neither layer compares the agent, and
only the APS compares the tenant. The governed worker pools still run older
runner images, which send the delete without naming a session; the APS checks
those by tenant alone, as before, and those images still log the handle. `run`
does not submit to those pools. The refusal is covered by zetra's tests and
has not been exercised on the cluster: the one session run after the roll was
db-admin, which has no grant.

#### Checking consent: `just agent consent --check <agent>`

`consent --check` answers one question for one person and one agent: does
Keycloak issue that person an access token that the APS deposit handler would
accept for this agent? `consent` takes exactly one of two modes: `--check`,
described here, and `--session`, the person's half of a waiting `run`
([above](#consent-for-a-release-that-requires-delegation)). With neither or
with both it refuses with exit 2.

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
only when the first argument is `run` or `consent`, so the other subcommands
start from the locked environment alone. `run` imports it only when it signs
someone in, so a run that asks nobody, or that waits for the consent command,
does not need it. As of 2026-11-10 `consent --check` has run only against the
in-process fake identity provider in `tests/test_agent_ops_consent.py`. It
has not been run against the live realm.

#### Consent has to be given at run time

Verified in zetra `677a2de`: a grant deposited before its session's workflow
exists does not last. The deposit registers the session with the APS. The
tenant's cleanup reconciler, when it is running, makes a pass every five
minutes, lists every APS session without an age filter, and treats a session
whose workflow does not exist as closed. Its next pass therefore removes the
grant. A person cannot consent in advance and hand over a handle for later;
consent and deposit have to happen as part of starting the run, which is what
`run` now does. Even then the deposit comes before the workflow exists, so a
reconciler pass in between removes the grant. `run` keeps that gap short and
fails closed when a pass lands in it:

- **Run started from a terminal.** The deposit and the workflow start are
  consecutive steps of one remote call, one request to the APS and one to
  Temporal apart. If a pass removes the grant in between, the workflow
  starts with a handle the APS no longer holds, preflight refuses it as
  `Forbidden`, the outcome is `FAILED` and `run` exits 1. Nothing acted for
  the person.
- **Awaited consent.** The gap runs from the consent command's deposit to the
  start made by `run`: up to half a second until `run` sees `consent.json`,
  then one `kubectl exec` and two reads at the APS, a few seconds in all. If
  a pass removes the grant before `run` looks for it, `run` exits 1 with
  `NOT_SUBMITTED` and no workflow starts. If it removes the grant between the
  lookup and the start, the session fails at preflight as above.

In both cases the person consents again on the next run. A grant that was
deposited for a run that then died before starting a workflow is removed the
same way, by the reconciler's next pass. None of this has been observed on
the cluster.

#### Per-person prerequisites

Two things remain the operator's to authorise for each person. No command
here does either, and without them that person's consent does not lead to a
working investigator session:

1. The Keycloak delegate permission for the agent's service account over that
   person. Without it the person is not expected to get a depositable
   token; what Keycloak does instead has not been observed (see the outcomes
   listed above). `consent --check` shows whether it is in place, and neither
   `run` nor `consent --session` deposits a token that lacks the scope or
   `may_act`.
2. Kubernetes read access for that person in `zetra-poc-fixtures`, the
   namespace investigator reads, granted to the person's Keycloak `sub` (the
   `subject` that `consent --check`, `consent --session` and the receipt
   report). This is expected, not yet verified: how the person's identity
   reaches the API server has not been exercised. No RoleBinding is committed
   for it, because the `sub` is not known until the person has signed in
   once.

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
- Nothing here changes identities, budgets or network policy. The only grant
  these commands create is the one a person's own sign-in and consent
  produce, for one session; no command mints one or revokes anything.
