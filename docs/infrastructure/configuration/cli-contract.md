# Operator command-line outcome contract

`just agent` (`infrastructure/scripts/ops/agent-ops.py`), `just agent-preflight`
(`agent-preflight.py`) and `just mcp` (`mcp-registry.py`) share one outcome
contract. A caller, human or automated, learns whether a command worked and what
kind of failure it was from one document, without parsing prose. The set of
codes is defined once, in `infrastructure/scripts/ops/outcome.py`; the tools
import it and nothing else defines a code.

## The document

Every command prints exactly one JSON document on stdout, on success and on
failure. Lines on stderr (`refused: ...`, `error: ...`, usage, the sign-in
prompts) are for the person at the terminal and are unchanged.

- Every document has a top-level boolean `ok`.
- A failure document also has `error`:
  `{"code": ..., "message": ..., "retryable": true|false}`. `retryable` is the
  code's class, never chosen per call.
- A `check-failed` error also has `proofs`, the list of every check that ran with
  its result.

The contract is additive. Every key a document held before is still there with
the same value and casing (`status`, `reason`, `stage`, `error_type`, `note`, the
receipt fields), indentation is unchanged (`just agent` prints indented JSON,
the other two print one line), and every exit code is unchanged. Where a
document already had an `ok` (the `check-sync` result and the preflight receipt)
it keeps its meaning and the value is the same. A caller branches on `ok`, then
on `error.code` or `error.retryable`.

Two things are not one JSON object, and stay as they were:

- `just agent ls` without `--json` prints a table and `just agent state`
  without `--json` prints text. Both are chosen by leaving the flag off; their
  failures are still a document on stdout.
- `--help` prints argparse's help and exits 0.

`just agent ls --json` used to print a bare JSON array on success, which could
not carry `ok`. It now prints one object: `ok` and the rows under `agents`, each
row unchanged. A consumer that read the array reads `.agents` instead.

One key changed type. In `just mcp`, an offline-stage refusal (`add`, `render`,
`check`) used to carry `error` as a string holding the exception's message. The
contract needs `error` to be the object, so the string is now
`error.message`; nothing else in that document moved.

## Codes

The set is closed. `outcome.error(code, message, proofs=...)` refuses a code
outside the set, a `retryable` flag that disagrees with the code's class, an
empty message, `proofs` on any code but `check-failed`, and a `check-failed`
without `proofs`.

| code | retryable | meaning |
| --- | --- | --- |
| `invalid-arguments` | no | the command line is malformed |
| `validation-failed` | no | an input file, task or definition breaks a rule; the message names what |
| `not-found` | no | the named agent, release, receipt, run or backend does not exist |
| `refused` | no | a gate or policy refused the request |
| `conflict` | no | existing state prevents the request |
| `check-failed` | no | a check ran and did not hold; `error.proofs` lists every check that ran |
| `failed` | no | the work ran and ended unsuccessfully (a session that did not complete, a cancel the runner did not accept) |
| `not-confirmed` | no | the work was started, or may have been, and its result is not confirmed; do not repeat the command, follow up with the receipt |
| `no-consent` | yes | nobody consented in time |
| `timeout` | yes | the wait ended before the work did, and repeating the command is safe (`wait`, a cancel call that did not answer) |
| `interrupted` | yes | interrupted before the command finished |
| `unavailable` | yes | the cluster, a tool the command shells out to, or a remote service could not be reached |
| `internal` | no | an unexpected error in the tool itself |

Where one code stands for several causes, and the cause was not at hand:

- `unavailable` covers `kubectl` failing for any reason (the wrapper reports
  the cause in the message, not in a type), `gh` exiting non-zero, and any
  exception in the `just mcp` credential stages that is an I/O, runtime or
  network error, and a Keycloak answer of 5xx (or 408 or 429, which ask for the
  request to be sent again). A Keycloak answer of any other 4xx (a 403, a 409)
  there is `refused`: the status code is kept on the exception and shown in the
  message as a number, while the response body and the exception text stay
  withheld.
- `not-confirmed` is the ending of a `just agent run` from the moment its
  submission is attempted, unless the session is confirmed started and closed or
  confirmed not started: repeating `run` mints a new session id and submits
  again, so no such ending is safe to repeat. It covers a submit call that timed
  out or returned something that cannot be read or placed, an interrupt while
  the submit call was in flight or while following the run, any error raised while
  following (including one that escapes as `REFUSED` or `ERROR`), and `run`'s
  own wait passing `--wait-timeout` (exit 124). The exit code is the one the
  ending always had. The document carries `sessionId` and `dir`, and once the
  receipt exists `receiptPath` and `next`, the exact command to run instead:
  `just agent status --receipt <path>` (or `wait`, to keep following). A submit
  call the runner refuses before it asks for anything to be started (`deposit
  refused: ...`, `session identity already exists`, `invalid request`, a session
  id that is not a UUID) is `refused`, not `not-confirmed`: nothing was started
  and there is nothing to follow up. A
  `consent --session` whose deposit may have taken effect (the call did not
  answer, answered unreadably, did not confirm, or was interrupted; `deposited`
  is `null`) is `not-confirmed` too: a second deposit for the same session is
  refused by the policy service (`this session already has a grant`) while no
  consent record is written, so the run that waits would still give up. A
  `consent --session` whose deposit was confirmed but whose record for the waiting
  run could not be written (an `OSError`, exit 1, or Ctrl-C, exit 130) is
  `not-confirmed` as well, with `deposited: true` and `recordWritten: false`: the
  policy service holds the grant, so repeating the command is refused too. `wait
  --receipt` passing its own deadline stays `timeout`, and so does a `cancel`
  whose call did not answer: repeating either is safe.
- `failed` is the code for a sign-in step that did not succeed (an `error=`
  callback, a `state` mismatch, a failed signature check) and for a remote call
  the runner answered with an error.
- `just agent status` reads a session, and reading it is the success. A session
  that has not ended prints `ok: true` with its `status` (for example `RUNNING`)
  and exits 0; there is no `error`. A session that ended without confirmed
  success or cleanup is `failed` with exit 1. `wait`, whose own deadline can
  pass first, is `timeout` (exit 124); `run` whose own wait passes first is
  `not-confirmed` (exit 124), because the session is running and repeating `run`
  would start another.
- A preflight receipt whose only blocking checks are `unavailable` is
  `unavailable` (its `checks` array is the detail); one whose only blocking
  check is the source checkout having no environment (`.venv`) is `not-found`,
  because repeating the command cannot succeed until the environment exists (the
  check keeps its `unavailable` state in `checks`); any other failed receipt is
  `check-failed`.
- `just mcp status` is `unavailable` when every layer that is not current could
  not be read, else `check-failed` with the layers as proofs.

## Exit codes

Unchanged by the contract; `ok` is true exactly when the exit code is 0.

| Exit | `just agent` | `just agent-preflight` | `just mcp` |
| --- | --- | --- | --- |
| 0 | the command succeeded | every required check passed or was not applicable | the command succeeded |
| 1 | a check failed (`check-sync`, `consent --check`, a token that would not be accepted for deposit); a session that closed without confirmed success or cleanup (also from `status`, which exits 0 for a session still running); a cancel the runner did not accept; an `OSError` or `ValueError` (`ERROR`); an unforeseen exception | a required check failed, was unavailable or was not checked; an unforeseen exception | every refusal (`status: refused`), `stale`, `invalid-registration`, a provisioning `conflict`, an incomplete `status` |
| 2 | a refusal by a gate or by the layout, live or sync code (`REFUSED`); a submit or deposit call that failed or was refused; a sign-in that failed; malformed arguments | malformed arguments | malformed arguments |
| 3 | `run`: nobody consented in time | | |
| 124 | the wait for a session passed `--wait-timeout`; `consent`: the sign-in was not completed in `--timeout` | | |
| 130 | interrupted (Ctrl-C) | an interrupt propagates | an interrupt propagates |

Malformed arguments keep argparse's behaviour: usage and the message on stderr,
exit 2. The `invalid-arguments` document is added on stdout by a parser subclass
that every subparser inherits. argparse echoes what was typed in most of its
messages, and `--grant-handle` carries a credential, so the document's message
holds only text the parser defines and ends by saying that usage is on stderr:
the list of missing arguments is kept; `argument NAME: ...` becomes `argument
NAME: the value is invalid or missing`, followed by the list of choices when the
value was an invalid choice; an ambiguous option keeps the candidates and drops
the typed word; unrecognized arguments, and any other message, become a fixed
sentence. stderr itself is unchanged.

## Redaction

`just mcp` stages that can touch a credential (`provision`, `identity`,
`status`, and the authentication step before the last two) never put an
exception's text in the document. `error.message` is one fixed sentence chosen by
the code (a Keycloak HTTP status code, a number, may follow it), and `error_type` still names the exception's type (a Keycloak HTTP error is reported as `RuntimeError`, as before the error got its own subclass). Only the offline
stages (`add`, `render`, `check`) may show a message, and only for `ValueError`
and `OSError`, which read committed files and touch no credential.

`just agent` shows in `error.message` what it already showed in `reason` or on
stderr (the `run` and `consent` documents already carry `reason`). An unforeseen
exception is `internal` and names only its type and the file and line that
raised it, because its message is not known to be free of a token or a remote
answer. `just agent-preflight` does the same for an exception that escapes the
receipt, whose own checks already sanitise what they carry. Any new failure path
keeps this rule: a code and a fixed or already-shown sentence, never new text
from an exception, a response body or the output of a remote process.

## Examples

`just agent check-sync`, success (indented in practice, shortened here):

```json
{"agents": [{"agent": "sample", "detail": "header verified offline; source not compared", "file": "infrastructure/gitops/apps/agents/tenant-test/sample/agent.yaml", "repo": "X-McKay/zetra-agents", "commit": "0123456789012345678901234567890123456789", "state": "ok", "tenant": "tenant-test"}], "ok": true, "pins": [{"detail": "both pin copies equal the pin derived from the sync headers", "state": "ok", "tenant": "tenant-test"}]}
```

`just agent run sample --task go` when nobody consented in time (exit 3):

```json
{
  "dir": "/home/al/.local/state/kubani/agent-runs/sample/20261111T101500-6b1f2f0e",
  "error": {"code": "no-consent", "message": "no consent was recorded in time; no consent command reached the deposit step and no workflow was started", "retryable": true},
  "ok": false,
  "reason": "no consent was recorded in time; no consent command reached the deposit step and no workflow was started",
  "sessionId": "6b1f2f0e-3c1c-4f65-9d0a-5b0e2c7a9d41",
  "status": "NOT_SUBMITTED",
  "timeoutSeconds": 300.0
}
```

`just agent-preflight sample --source ../zetra-agents --tag sample/v0.2.0`,
success (one line, shortened):

```json
{"agent": "sample", "checks": [{"code": "source_compatibility", "state": "pass", "required": true}], "ok": true, "schemaVersion": 1, "scope": "offline-compatibility", "tag": "sample/v0.2.0"}
```

The same command, a required check failed (exit 1):

```json
{"agent": "sample", "checks": [{"code": "source_compatibility", "state": "pass", "required": true}, {"code": "agent_semantics", "state": "fail", "required": true}], "error": {"code": "check-failed", "message": "1 required checks did not hold; see proofs", "proofs": [{"code": "source_compatibility", "state": "pass", "required": true}, {"code": "agent_semantics", "state": "fail", "required": true}], "retryable": false}, "ok": false, "schemaVersion": 1, "scope": "offline-compatibility", "tag": "sample/v0.2.0"}
```

`just mcp check`, success:

```json
{"ok": true, "scope": "offline-registration", "status": "valid"}
```

`just mcp identity plan example-monitor` when Keycloak could not be reached
(exit 1; the exception's text is withheld):

```json
{"error": {"code": "unavailable", "message": "a service or tool this stage depends on could not be reached or did not answer; the exception text is withheld", "retryable": true}, "error_type": "RuntimeError", "note": "No conflicting identity is overwritten. Inspect configuration and any partial operation before retry.", "ok": false, "stage": "identity-authentication", "status": "refused"}
```
