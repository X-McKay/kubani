# Agent operations: `just agent`

One command family for the day-to-day lifecycle of an applied agent. It wraps
what the November 2026 releases did by hand: copying the Agent from the source
repository, staging a published release, approving it after the controller has
verified it, and submitting an ordinary session. Every subcommand prints one
JSON document and exits non-zero on refusal, so an operator or an automated
session can act on it without parsing prose. Every document carries `ok`, and a
failure carries `error.code` from a closed set; see the
[CLI outcome contract](cli-contract.md).

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
live objects (the approved, Ready, signature-verified, drift-free release; when
several qualify, the one with the latest `spec.approval.approvedAt`, unless
`--release` pins one) and the identity mode from the release status. If the
approval times of the qualifying releases are missing or equal, they cannot be
ordered and `run` refuses and lists their names; pass `--release`. The `run`
output and `receipt.json` record the release used as `release` and how it was
chosen as `releaseChoice` (`default` or `explicit`; receipts written before
this key existed lack it and still load). The command is the same for every agent; what it needs depends on the
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
three; `run` takes the most recently approved of them unless `--release` names
another. A release that requires delegation
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
bytes, strict UTF-8) copied out.

Once its arguments have parsed, `run` prints exactly one JSON document on
stdout however it ends, and each ending has one exit code. A `REFUSED` or
`ERROR` ending also prints one line on stderr (`refused: ...` or
`error: ...`), as the other subcommands do.

| Ending | Exit | `status` in the document | Files the ending leaves |
| --- | --- | --- | --- |
| the workflow closed with confirmed success and cleanup, and the report was copied out | 0 | the workflow's status | `request.json`, `receipt.json`, `status.json`, `report.md` |
| `--no-wait`, the workflow was started | 0 | `SUBMITTED` | `request.json`, `receipt.json` |
| the workflow closed without confirmed success or without confirmed cleanup | 1 | the workflow's status | `request.json`, `receipt.json`, `status.json` |
| `--wait-timeout` passed | 124 | the workflow's status, with `timedOut: true` | `request.json`, `receipt.json`, `status.json` |
| Ctrl-C while following the workflow; the workflow is not cancelled | 130 | `INTERRUPTED` | `request.json`, `receipt.json` |
| refused before a run directory exists: the input, the release, the identity row, no Ready runner pod, PyJWT missing for a sign-in | 2 | `REFUSED` | none |
| an error that is not a refusal, such as a task file that cannot be read or is not JSON | 1 | `ERROR` | none |
| an error the code does not foresee (any other Python exception) | 1 | `ERROR`, the reason naming only the exception's type and the file and line that raised it; with `sessionId` and `dir` once the run directory exists | whatever was written by then, which can include the `receipt.json` of a started workflow; no `status.json` |
| the submit call failed, was refused by the remote script or did not answer in 60 seconds | 2 | `SUBMIT_UNCONFIRMED` | `request.json`, `status.json` |
| Ctrl-C while the submit call was in flight | 130 | `SUBMIT_UNCONFIRMED` | `request.json`, `status.json` |
| nobody consented within `--consent-timeout`, or the sign-in at this terminal was not completed in time | 3 | `NOT_SUBMITTED` | `request.json`, `status.json` |
| the token Keycloak issued at this terminal would not be accepted for deposit | 1 | `NOT_SUBMITTED`, with `missing` | `request.json`, `status.json` |
| `consent.json` is not a record for this session, or does not carry the digest of what this run holds | 1 | `NOT_SUBMITTED` | `request.json`, `status.json` (beside the `consent.json` that was found) |
| consent was recorded and the APS holds no grant for the session | 1 | `NOT_SUBMITTED` | `request.json`, `status.json` (beside `consent.json`) |
| the sign-in at this terminal was refused or failed (an `error=` callback, a `state` mismatch, a failed signature or issuer check, a listener failure) | 2 | `NOT_SUBMITTED` | `request.json`, `status.json` |
| Ctrl-C during the sign-in or while waiting for consent | 130 | `NOT_SUBMITTED` | `request.json`, `status.json` |

The last six rows are reached only by a release that requires delegation.
`SUBMIT_UNCONFIRMED` means the submit call returned no started workflow and
no receipt was written, so `status`, `wait` and `cancel` cannot be pointed at
the session. Whether a workflow exists depends on the reason (read from
`remote_session.py`, not observed on the cluster):

- This call started none. The remote script gives these answers before it
  asks Temporal to start anything: `invalid request`, `session must be a
  canonical UUIDv4`, `session identity already exists` (a workflow with that
  identity was already there), every `deposit refused: ...`, `grant deposit
  failed`, `policy service unreachable`, `policy service session listing
  failed` and `the session's grant names another tenant or agent`.
- A workflow was started: `accepted start run identity missing`.
- Not known: `operation failed; ...` (any other failure inside the pod, its
  40-second limit included), a call that did not answer in 60 seconds, a
  `kubectl exec` that failed, and Ctrl-C while the call was in flight.

Every `NOT_SUBMITTED`, `SUBMIT_UNCONFIRMED` and `INTERRUPTED` document
carries a `reason`; for a release that requires delegation the reason says
what is known about a grant (see
[What can go wrong](#what-can-go-wrong)). A remote call that wrote to stderr
also leaves an `exec-NN.stderr` file. Two endings fall outside the table: a
remote `status` call that fails while the workflow is being followed ends as
`REFUSED` with exit 2, and an operating-system error such as a file that
cannot be written ends as `ERROR` with exit 1; both leave what was written by
then and write no `status.json`. Ctrl-C at a moment `run`
does not handle itself (before the run directory exists, for example) ends as
`INTERRUPTED` with exit 130 and a document that holds only `status` and
`reason`. No ending prints a Python traceback; an unforeseen exception's
message is not printed either, because it is not known to be free of what a
remote answer or a token carried.

Each run gets a new private directory, by default
`~/.local/state/kubani/agent-runs/<agent>/<UTC time>-<session prefix>/`:

| File | Content |
| --- | --- |
| `request.json` | tenant, agent, release, session id, task and bound (never the grant handle) |
| `receipt.json` | namespace, workflow id, run id, task queue, runner pod uid, remote script sha256, the release's identity mode, whether a grant handle was submitted or a grant deposited, and how consent was obtained (never a token or a handle) |
| `status.json` | the document `run` printed, for the endings the table above lists it under: status, query, result and cleanup confirmation once a workflow closed or `--wait-timeout` passed; `NOT_SUBMITTED` or `SUBMIT_UNCONFIRMED` with a `reason` otherwise. Not written by `--no-wait`, by Ctrl-C while following, or by a `REFUSED`, `ERROR` or bare `INTERRUPTED` ending |
| `report.md` | the agent's report, present only after confirmed success |
| `exec-NN.stderr` | bounded stderr of a remote call, when any |
| `consent.json` | written by `consent --session` after the APS accepted the deposit: session id, agent, tenant, `shownSha256` (the digest of what the person was shown), the person's subject id, whether a refresh token was issued, `grantRequestedUntil`, when the deposit was made (never a token or a handle) |
| `waiting.lock`, `deposit.lock` | empty lock files of a run that waited for consent |
| `deposit.attempted` | one timestamp per deposit a consent command sent. Removed when the deposit is confirmed, and when the APS refuses it and no earlier attempt is unresolved. While it exists, a run that ends without a workflow says a grant may be held |
| `consent-exec-NN.stderr` | bounded stderr of the consent command's remote call, when any |

`status`, `wait` and `cancel` take `--receipt` and operate on that exact run
only; they never submit. The runner pod's uid, container id, image id and
restart count are re-read after every call and `runnerIdentityChanged` is
reported if any differs. Only `wait` takes `--wait-timeout` and
`--poll-interval`; `status` and `cancel` reject them. `cancel` exits 0 when the
runner accepted the cancellation (`cancel.cancel_requested: true`) and 1
otherwise; `status` exits 0 only for a closed, confirmed run, as `run` does.
`check-sync NAME` refuses a name that is not a committed agent (exit 2) and
lists the valid ones. `--poll-interval`, `--wait-timeout` and
`--max-boundaries` must be above 0.

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

`--consent-timeout` and `--browser` apply only on these two paths. A run that
asks nobody accepts them and ignores them.

**Started from a terminal** (stdin and stderr are both a TTY; stdout may be a
pipe or a file, so `just agent run ... | jq` still signs the person in here).
`run` prints on stderr, before any URL: the whole task as it will be
submitted, as one line of JSON with every non-ASCII and control character
written as an escape, then one line naming the agent, tenant, release and session id, then the authorization
URL. The person who started it opens the URL and answers the consent screen.
The sign-in is the one `consent --check` performs
([steps 1 to 3](#checking-consent-just-agent-consent---check-agent)) with one
difference: the URL carries `prompt=consent` in place of
`prompt=login consent`. That asks Keycloak to reuse an open session and still
show the consent screen (`agent-cli` has `consentRequired`; not observed).
Because a reused session may belong to another account than the person
expects, `run` prints `Signed in as <preferred_username>.` on stderr after
the sign-in (the `sub` when the token has no username). `--browser` also
hands the URL to the default browser. `run` checks the token against the four
conditions `consent --check` reports and, if one fails, ends with exit 1 and
`NOT_SUBMITTED` without sending the token anywhere; the reasons are under
`missing`. Otherwise it makes one remote call, which deposits the token for
the session id and starts the workflow.

**Started without a terminal** (stdin or stderr is not a TTY). `run` signs
nobody in. It prints one line on stderr and waits up to `--consent-timeout`
seconds (300 by default, 900 at most):

```text
investigator acts on behalf of a person and this run cannot sign anyone in (stdin and stderr are not both a terminal). Within 300 seconds that person runs, in a terminal on this machine: just agent consent investigator --session <id>
```

The consent command finds the run under the default run directory by the
session id's first eight characters. When `--out` put the run directory
anywhere that lookup would not find it, including a differently named
directory inside the default location, the printed command also carries
`--run-dir` with the absolute path, quoted for the shell. The person runs the
printed command in their own terminal. `consent --session`:

1. Refuses, before anyone is asked to sign in, unless the committed Agent is
   on-behalf-of, stdin and stderr are both a TTY, the session id is a
   lower-case UUID, and a `run` of that agent and tenant on this machine is
   alive and still waiting for that session. It also refuses a run directory
   that the caller does not own or whose mode is not exactly 0700, and a
   `request.json` that is a symbolic link, is not a regular file or is not
   owned by the caller: that file decides what the person is shown.
2. Prints the whole task from the run's `request.json`, however long, then
   the agent, tenant, release and session id and the authorization URL,
   in the same form as a run started from a terminal, and after the sign-in
   the same `Signed in as` line.
3. If the token meets the four conditions, deposits it through its own remote
   call and writes `consent.json` into the run directory. If it does not, the
   command exits 1, lists the reasons under `missing` and deposits nothing;
   the run keeps waiting.

`consent.json` carries `shownSha256`: a SHA-256 over one canonical JSON
encoding of the tenant, agent, release, session id and whole task document
that step 2 displayed from. `run` computes the same digest from what it holds
in memory, which is what it will submit, and starts nothing unless the two
are equal. A `request.json` changed between `run` writing it and the consent
command reading it therefore ends the run with exit 1 and `NOT_SUBMITTED`,
after the deposit: the grant may be held until the cleanup reconciler's next
pass, and the reason says so. The handle never reaches the host, so the host
cannot release that grant itself. The digest covers the whole task and the
whole task is displayed: up to 16 KiB, which as escaped JSON can be several
times that many characters on the terminal. Nothing is cut, because a part
left unshown would be consented to unseen. The release and the other names on
the following line, and the account name after the sign-in, are printed with
every character outside visible ASCII replaced by `?` (an account name with
other letters shows `?` for them), and a name over 256 characters is cut with
the cut and the full length stated, so a value in `request.json` cannot move
the cursor, erase the task line or hide part of itself. A release changed
that way still fails the digest comparison, after the deposit.

`run` learns that the grant exists from `consent.json` and from nothing else:
it looks for the file twice a second. The file is written only after the APS
accepted the deposit, and it is renamed into place, so it is never seen half
written. `run` then makes one remote call, which finds the grant by session
id and starts the workflow. Two lock files keep the two commands from
crossing: `run` cannot give up while a deposit is in progress, and a second
`consent` for the same session is refused.

If nobody consents in time, `run` exits 3 with status `NOT_SUBMITTED`. No
workflow was started, and a `consent` that arrives afterwards is refused
before the sign-in. The reason says what this machine knows about a deposit:
that no consent command reached the deposit step, or that one sent a token
and recorded no deposit, in which case a grant may be held until the cleanup
reconciler's next pass. A run started from a terminal exits 3 in the same way
when the sign-in is not completed in time; no token left the machine.

Ctrl-C ends either path with exit 130, `NOT_SUBMITTED` in `status.json` and
on stdout, and no traceback. A consent command that arrives afterwards is
refused.

The awaited path asks more of the person than a sign-in. The run directory is
private to the operating-system user who started `run`, and the deposit is
made with `kubectl exec` into the Session Runner pod. So the person has to be
at a terminal on the machine where `run` waits, as that user, with a
kubeconfig that may exec into that pod. Today that is the operator consenting
to a session that an automated session started. There is no path yet for a
person who has no such access.

What the digest does not do: it is checked by `run` on the host. Nothing at
the APS or the Session Runner binds a grant to a task, so a process that can
already exec into the runner pod could start that session id with another
task once a grant exists.

#### Where the token and the handle go

The person's token goes from their browser to the command's loopback
listener, stays in the command's memory, and is written to the standard input
of `kubectl exec`. The remote script sends it to the APS as the bearer token
of `POST /v1/grants` on port 9002, with the refresh token (or null) and the
expiry in the body. The token is never placed on a command line, in a file,
in the command's output, in the receipt or in an error message. The remote
script reaches the APS without a proxy and without following a redirect, and
reports a failure as one of a fixed list of messages. That request is plain
HTTP inside the cluster network
(`http://agent-policy-service.agent-platform.svc.cluster.local:9002`), as
every Session Runner call to the APS already was before this path existed;
whether traffic between nodes is encrypted was not checked.

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
ask for `offline_access`; `agent-cli` is refused it with HTTP 400
`not_allowed`, which
`infrastructure/gitops/apps/agent-platform/conformance/human/DELEGATION.md`
records as observed, although the realm file lists it as an optional scope of
the client). Both answers are
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

Either way the receipt records `refreshTokenIssued` and
`grantRequestedUntil`. That time is the upper bound the deposit asked for,
not how long delegation will work. The APS refreshes the access token only
during an exchange, and only when less than 120 seconds of it remain; it does
nothing between exchanges. With the realm's client session idle time of 600
seconds, a session that makes no delegated call for about ten minutes is
expected to find the refresh token dead and delegation over, well before
`grantRequestedUntil` (read from the realm file and zetra `18aee61`, not
observed).
Nothing is revoked at Keycloak, for the reason given under
[`consent --check`](#checking-consent-just-agent-consent---check-agent).

#### What the receipt records about consent

`consent` in the receipt is null when the run asked nobody, so receipts of
own-identity agents, of optional delegation and of `--grant-handle` runs gain
a `consent: null` field they did not have before. Otherwise it
holds `mode` (`inline` for a run that signed the person in itself, `awaited`
for one that waited for the consent command), `subject`, `subjectSource`,
`refreshTokenIssued` and `grantRequestedUntil`.

`subject` is the `sub` claim of the person's token, Keycloak's opaque id for
the user. It is recorded because it says who consented, the APS already logs
it at deposit, and `consent --check` already prints it. The username is
printed on stderr after the sign-in and is not recorded in the receipt. For
an inline run the subject comes from the token `run` verified.
For an awaited run `run` never sees the token and copies the subject from
`consent.json`, a file any process of the same operating-system user could
have written; `subjectSource` says which of the two it was. The receipt holds
no token and no handle.

#### What can go wrong

Every result below is one JSON document on stdout with the exit code given.
"A grant may be held" is the reason's own wording: `a grant may be held for
this session until the cleanup reconciler's next pass (every five minutes)`.
The interval is read from zetra `18aee61`; no removal has been observed.

| Case | Result |
| --- | --- |
| nobody runs the consent command within `--consent-timeout` | `run` exits 3, `NOT_SUBMITTED`: `no consent was recorded in time; no consent command reached the deposit step and no workflow was started` |
| a consent command sent a token and its deposit was never confirmed, and the run then gives up or is interrupted | `run` exits 3 (130 when interrupted), `NOT_SUBMITTED`; the reason says a consent command sent a token and recorded no deposit, so a grant may be held |
| the sign-in of a run started from a terminal is not completed in time | `run` exits 3, `NOT_SUBMITTED`; no token was sent to the cluster and no workflow was started |
| Keycloak issues a token that fails one of the four conditions, run started from a terminal | `run` exits 1, `NOT_SUBMITTED`, with `subject`, `preferredUsername` and the reasons under `missing`; no token was sent to the cluster |
| the same, in `consent --session` | exit 1 with `deposited: false` and the reasons under `missing`; the run keeps waiting until its timeout |
| Keycloak refuses the authorization request, or the sign-in fails a check, run started from a terminal | `run` exits 2, `NOT_SUBMITTED`, the reason naming the refusal; no token was sent to the cluster |
| the same, in `consent --session` or `consent --check` | exit 2, `REFUSED`; the run keeps waiting until its timeout |
| the sign-in of `consent --session` is not completed in time | exit 124 with `deposited: false` and `timedOut: true`; the run keeps waiting until its timeout |
| the APS refuses the deposit, run started from a terminal | `run` exits 2, `SUBMIT_UNCONFIRMED`: `remote submit failed: deposit refused: <reason>; the policy service holds no grant from this run`; no receipt |
| the APS refuses the deposit, `consent --session` | exit 2 with `deposited: false` and `remote deposit failed: deposit refused: <reason>; this command deposited nothing`; no `consent.json`; the run keeps waiting |
| the consent command's deposit fails another way, is not confirmed, or does not answer within 60 seconds | exit 2 with `deposited: null` and a reason that says a grant may be held; no `consent.json`; `deposit.attempted` stays; the run keeps waiting |
| `consent.json` is for another session or cannot be read | `run` exits 1, `NOT_SUBMITTED`; no workflow was started; if a consent command deposited a token, a grant may be held |
| `consent.json` does not carry the digest of this run's tenant, agent, release, session and task | `run` exits 1, `NOT_SUBMITTED`; no workflow was started and a grant may be held |
| `consent.json` exists but the APS holds no grant for the session when `run` looks | `run` exits 1, `NOT_SUBMITTED`, `consent was recorded but the policy service no longer holds a grant for this session; no workflow was started; run again and consent again`; no receipt |
| the workflow cannot be started after the grant was deposited or found | the remote script tries once to remove the grant, naming this session, if no workflow exists for it, and does not report whether that worked; `run` exits 2, `SUBMIT_UNCONFIRMED`, and the reason says a grant may be held; the next run needs a new consent |
| a remote call does not answer within 60 seconds | from `run`'s submit call: exit 2, `SUBMIT_UNCONFIRMED`, `remote submit did not answer within 60 seconds; whether it took effect is not known`, and for a release that requires delegation that a grant may be held |
| Ctrl-C during the sign-in or the wait | `run` exits 130, `NOT_SUBMITTED`; `consent --session` exits 130 with `deposited: false` and `interrupted: true`, or `deposited: null` with a reason when the deposit was in flight |
| `consent --session` without a terminal, for an own-identity agent, for a session no live run of that agent and tenant on this machine waits for, for a run directory or `request.json` another account owns or could have changed, or after consent was already given | exit 2, `REFUSED`, before the sign-in; `this command deposited nothing` where a run directory was found |

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
  consent, required with `--grant-handle`), the refusals, timeouts and
  interrupts above, the digest and ownership checks, the terminal test on
  stand-in streams, and that no token, token segment, authorization code or PKCE verifier is in
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

Limits that apply to every agent, not only to one that requires delegation:

- Every remote call, including `status`, `wait` and `cancel` for an
  own-identity agent, now sends the script and the request on the standard
  input of `kubectl exec` (the bootstrap described under "Running a
  session"). On 2026-11-11 (UTC) one db-admin session was run on it from
  this change at `19ec7ca7`, before merge: submit and the status polling
  completed with confirmed cleanup, and `status --receipt` on the finished
  run answered. `wait`, `cancel`, and a submit that carries a deposit or
  looks up a deposited grant have run only against stand-ins.
- A refusal or error before submit now also prints a `REFUSED` or `ERROR`
  document on stdout, where stdout used to stay empty; the stderr line and
  the exit code are as before. A caller that reads stdout only after exit 0
  sees no difference.
- The Session Runner pod is located before the run directory is created, so
  a run refused for want of a Ready runner pod leaves no directory, where it
  used to leave one holding `request.json`.
- Receipts gain `consent: null` for the identity rows that ask nobody.
- A failed or unanswered submit call now ends with a `SUBMIT_UNCONFIRMED`
  document and `status.json` for every agent, where it used to print only a
  `refused:` line and write no `status.json`. The exit code is 2 as before.
- The remote script's output is confined to a fixed list of messages, and
  the tests read it for tokens and handles. The pod's stderr is different: up
  to 4,000 characters of it are copied into `exec-NN.stderr` (or
  `consent-exec-NN.stderr`) as they came. The script names stderr nowhere,
  but what the Python interpreter or the runner's libraries write there on a
  crash or a warning was not established by reading them. It is the one path out of the
  pod that is not closed by reading the code.

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
| delegation required, no `--grant-handle` | nobody: `run` asks the person for consent | see [What can go wrong](#what-can-go-wrong); when nobody consents in time, exit 3 with no workflow started and a reason that says what is known about a deposit |
| on-behalf-of release that reports neither true nor false for `delegationRequired`, no `--grant-handle` | `run`, before a run directory exists or anything is submitted | `refused: <agent>: release <name> does not report whether delegation is required`, exit 2 |
| `identity.mode: agent`, `--grant-handle` given | `run`, at the same point | `refused: <agent> runs with its own identity and takes no grant handle`, exit 2 |
| delegation required, handle the APS does not hold (unknown, expired or already deleted) | Session Runner preflight | the preflight activity fails as `Forbidden` (`APS GET refused with 404`); the result outcome is `FAILED` and `run` exits 1 without a report |
| delegation required, handle deposited in another tenant | Session Runner preflight | the same, with `APS GET refused with 403` |
| delegation required, handle deposited for another session id | Session Runner preflight | `Forbidden` (`delegated session without a grant`); the same outcome and exit code |

The release is resolved before the handle is looked at; while investigator has
two Ready releases, `run investigator` without `--release` uses the most
recently approved one, and refuses only if their approval times cannot order
them.

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
`identity.mode: on-behalf-of`, and unless stdin and stderr are both a
terminal (stdout may be a pipe or a file; it receives only the JSON
document). The terminal check runs before anything is listened on or fetched.
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
callback and a listener failure), 124 when no callback arrived in time,
130 on Ctrl-C. A refusal prints `refused: <reason>` on stderr and
`{"status": "REFUSED", "reason": ...}` on stdout; Ctrl-C prints
`{"status": "INTERRUPTED", ...}` and no traceback. The same holds for
`consent --session`, whose other documents are listed under
[What can go wrong](#what-can-go-wrong).

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

The token checks use PyJWT, which is one of the project's locked
dependencies (`PyJWT[crypto]==2.13.0` in `pyproject.toml` and `uv.lock`).
`just setup` installs it with everything else, and `just agent` starts every
subcommand from the locked environment with no `--with`, so a machine whose
environment is synced needs no package index to run any agent. `run` imports
PyJWT only when it signs someone in, so a run that asks nobody, or that waits
for the consent command, does not use it. As of 2026-11-10 `consent --check` has run only against the
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
  start made by `run`: the rest of the consent command's own remote call, up
  to half a second until `run` sees `consent.json`, then one `kubectl exec`,
  a connection to Temporal and two reads at the APS. That is expected to take
  seconds; it has not been measured. If
  a pass removes the grant before `run` looks for it, `run` exits 1 with
  `NOT_SUBMITTED` and no workflow starts. If it removes the grant between the
  lookup and the start, the session fails at preflight as above.

In both cases the person consents again on the next run. A grant that was
deposited for a run that then died before starting a workflow is removed the
same way, by the reconciler's next pass. None of this has been observed on
the cluster.

#### Prerequisites for a first run

On the machine and for the command:

- **The browser runs on the same host as the command.** The redirect goes to
  the command's listener on `127.0.0.1` (the realm allows `agent-cli` only
  `http://127.0.0.1/*`). Over SSH the person either forwards the port the
  printed URL names in its `redirect_uri` to the same port on the remote host
  before opening the URL, or runs the command where the browser is. The port
  is chosen per sign-in, so the forward is set up after the URL is printed.
- **PyJWT is in the synced environment** (`just setup`, or `uv sync
  --locked`). A run that would sign someone in refuses before creating a run
  directory when it is missing.
- **investigator has two Ready releases**; `run` takes the most recently
  approved unless `--release` pins the other, and `just agent ls` shows which
  it would use. The release is resolved before anything about
  consent is looked at.
- **Automation gives the run time.** A run that waits for consent lasts up to
  `--consent-timeout` seconds before it submits anything. An automated
  session starts it in the background, or with a tool timeout longer than
  `--consent-timeout`: killing the run ends the wait, and a consent given
  after that is refused.

Two more things remain the operator's to authorise for each person. No
command here does either. Without the first the person is not expected to get
a token `run` will deposit; without the second the session is expected to
start and investigator to be refused what it tries to read. Neither
expectation has been observed:

1. The Keycloak delegate permission for the agent's service account over that
   person. Without it the person is not expected to get a depositable
   token; what Keycloak does instead has not been observed (see the outcomes
   listed above). `consent --check` shows whether the token Keycloak issues
   that person meets the four conditions, which is the visible effect of the
   permission and not the permission itself, and neither `run` nor
   `consent --session` deposits a token that lacks the scope or `may_act`.
   The one tool that grants the permission,
   `infrastructure/scripts/ops/conformance-delegation.py`, refuses any actor
   but the synthetic `conformance-alice`.
2. Kubernetes read access for that person in `zetra-poc-fixtures`, the
   namespace investigator reads. Which name the API server sees for the
   person is unknown: probably the Keycloak `sub` (the `subject` that
   `consent --check`, `consent --session` and the receipt report); not
   confirmed. This repository holds no API-server OIDC username
   configuration, and how the person's identity reaches the API server has
   not been exercised. No RoleBinding is committed for it.

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
  produce, for one session. Nothing is revoked at Keycloak. The only removal
  these commands make is the remote script's: after a failed start it asks
  the APS once to delete the grant it deposited or found for that session.
