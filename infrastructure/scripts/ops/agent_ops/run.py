"""Submit, follow and report one ordinary session through the tenant's Session Runner.

An agent whose release requires delegation needs a person's consent before it starts. `submit` obtains
it in one of two ways and `consent` is the other half of the second:

- started from a terminal, `submit` signs the person in itself and hands the token to the runner pod,
  which deposits it and starts the session in the same remote call;
- otherwise `submit` waits, and the person runs `consent` in their own terminal. `consent` deposits the
  token through the same pod and leaves a record beside the waiting run; `submit` then asks the pod to
  start the session with the grant the policy service holds for that session id.

Either way the person is shown the tenant, agent, release, session and task before the sign-in URL. On
the second path `consent` writes a digest of what it showed into its record, and `submit` starts nothing
unless that digest is the one of what it is about to submit.

The person's token travels from the sign-in to the standard input of `kubectl exec` and nowhere else.
The grant handle never leaves the pod: no path here reads, prints or stores one, except a handle the
submitter passes in with `--grant-handle`.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import fnmatch
import hashlib
import hmac
import json
import os
import shlex
import stat
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import delegation, layout, live

REMOTE = Path(__file__).with_name("remote_session.py")
PYTHON = "/app/.venv/bin/python"
# Reads the script, of the length given, from stdin and runs it; the script reads its request from what follows.
# Every call has this same command line, so nothing a request carries appears in a process listing or an exec URL.
BOOTSTRAP = "import sys; exec(compile(sys.stdin.buffer.read(int(sys.argv[1])), 'remote_session.py', 'exec'), {'__name__': '__main__'})"
TERMINAL = {"COMPLETED", "FAILED", "CANCELED", "TERMINATED", "TIMED_OUT", "CONTINUED_AS_NEW"}
EXEC_TIMEOUT = 60
MAX_TASK_BYTES = 16 * 1024
# Exit code: the release requires a person's consent and none arrived in time; this run sent no token and started no workflow.
NO_CONSENT = 3
# Exit code: the person interrupted the run or the consent command (Ctrl-C).
INTERRUPTED = 130
CONSENT_POLL = 0.5
CONSENT_RECORD = "consent.json"
# Held by a `run` for as long as it waits for consent; the kernel releases it if the process dies.
WAITING_LOCK = "waiting.lock"
# Held by `consent` from its last look at the run until its record is written, and by `run` when it gives up.
DEPOSIT_LOCK = "deposit.lock"
# Appended to by `consent` just before it sends a token to the pod, and removed once the outcome is recorded or known to be
# a refusal. Left behind, it says a deposit was attempted and this machine does not know how it ended.
DEPOSIT_ATTEMPT = "deposit.attempted"
MAX_REQUEST_BYTES = 256 * 1024
# The runner's cleanup reconciler closes a session that holds a grant and has no workflow; it runs every five minutes
# (RECONCILE_EVERY in zetra platform/runner/runner/worker.py, read at 18aee61, not observed).
GRANT_MAY_BE_HELD = "a grant may be held for this session until the cleanup reconciler's next pass (every five minutes)"
# Answers of the pod's deposit that mean this call left no grant: the policy service refused the token, or the request never reached it.
NO_GRANT_ANSWERS = ("deposit refused:", "invalid request", "session identity already exists", "session must be a canonical UUIDv4")


class RunError(Exception):
    pass


class _Ended(Exception):
    """A run that ends before it asks for a workflow: the exit code, the reason and what else its envelope carries."""

    def __init__(self, code: int, reason: str, **extra):
        super().__init__(reason)
        self.code, self.reason, self.extra = code, reason, extra


def runs_base() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "kubani/agent-runs"


def default_out(agent: str, session: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return runs_base() / agent / f"{stamp}-{session[:8]}"


def _private(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(text)


def _utc(seconds: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


@contextlib.contextmanager
def _locked(path: Path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _stderr(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def shown_digest(tenant: str, agent: str, release, session: str, task) -> str:
    """sha256 over one canonical encoding of what a person is shown before they consent to a session."""
    shown = {"tenant": tenant, "agent": agent, "release": release, "sessionId": session, "task": task}
    return hashlib.sha256(json.dumps(shown, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _plain(value) -> str:
    """A value read from a file or a token, as it may be put on a terminal: printable characters only, and bounded."""
    return "".join(ch if ch.isprintable() else "?" for ch in str(value))[:256]


def _show(say, tenant: str, agent: str, release, session: str, task) -> str:
    """Tell the person which task they are about to consent to; returns the line that introduces the sign-in URL."""
    # The whole task and never a part of it: the digest covers all of it, so all of it has to be put in front of the person.
    # JSON with ASCII escapes leaves no control character and no direction override for a terminal to act on.
    say("Task: " + json.dumps(task, sort_keys=True, ensure_ascii=True))
    return f"{_plain(agent)} (tenant {_plain(tenant)}, release {_plain(release)}) will act as you for session {_plain(session)}, on the task above: open this URL, sign in if asked and answer the consent screen."


def _say_who(say, report: dict) -> None:
    """Name the account that signed in, so a sign-in as someone else is seen before anything runs. Never a token."""
    name = str(report.get("preferredUsername") or report["subject"])
    say("Signed in as " + _plain(name) + ".")


class Runner:
    def __init__(self, kube: live.Kube, tenant: str, out: Path, stderr_prefix: str = "exec"):
        self.kube = kube
        self.tenant = tenant
        self.out = out
        self.stderr_prefix = stderr_prefix
        self.pod = live.runner_pod(kube, tenant)
        self.code = REMOTE.read_bytes()
        self.calls = 0
        self.identity_changed = False

    def remote(self, request: dict) -> dict:
        self.calls += 1
        argv = [PYTHON, "-c", BOOTSTRAP, str(len(self.code))]
        stdin = self.code + json.dumps(request, sort_keys=True).encode("utf-8")
        try:
            proc = self.kube.exec(self.pod["name"], live.PLATFORM_NAMESPACE, "runner", argv, stdin, EXEC_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise RunError(f"remote {request['action']} did not answer within {EXEC_TIMEOUT} seconds; whether it took effect is not known") from None
        stderr = proc.stderr.decode("utf-8", "replace")[-4000:]
        if stderr:
            _private(self.out / f"{self.stderr_prefix}-{self.calls:02d}.stderr", stderr)
        try:
            payload = json.loads(proc.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RunError(f"remote {request['action']} returned no JSON (exit {proc.returncode})") from exc
        self._recheck()
        if proc.returncode != 0 or "error" in payload:
            raise RunError(f"remote {request['action']} failed: {payload.get('error', 'unknown')}")
        return payload

    def _recheck(self) -> None:
        try:
            now = live.runner_pod(self.kube, self.tenant)
        except live.LiveError:
            self.identity_changed = True
            return
        if any(now[k] != self.pod[k] for k in ("uid", "containerID", "imageID", "restartCount")):
            self.identity_changed = True


def plan(root: Path, kube: live.Kube, agent: str, *, release: str | None, grant_handle: str | None, task) -> dict:
    d = layout.find_agent(root, agent)
    views = live.releases(kube, d.tenant)
    view = live.resolve_release(views, agent, release)
    mode = view.identity_mode or live.agents(kube, d.tenant).get(agent, {}).get("identity")
    if mode not in ("agent", "on-behalf-of"):
        raise RunError(f"{agent}: identity mode is not reported by the release or Agent")
    if grant_handle is not None and not grant_handle.strip():
        raise RunError("--grant-handle was given an empty value")
    if mode == "agent" and grant_handle is not None:
        raise RunError(f"{agent} runs with its own identity and takes no grant handle")
    consent = False
    if mode == "on-behalf-of" and grant_handle is None:
        # Only a release that reports delegation as not required runs without a grant; the APS
        # then applies the Agent's fallback per backend. Unreported is not "not required".
        if view.delegation_required is True:
            consent = True
        elif view.delegation_required is not False:
            raise RunError(f"{agent}: release {view.name} does not report whether delegation is required")
    encoded = json.dumps(task, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_TASK_BYTES:
        raise RunError("task exceeds 16 KiB")
    # `consent`: the release requires a person's delegation and no handle was given, so the run has to obtain consent.
    return {"tenant": d.tenant, "agent": agent, "release": view.name, "identity": mode, "delegated": grant_handle is not None or consent, "consent": consent, "task": task}


def _not_submitted(out: Path, session: str, code: int, reason: str, *, status: str = "NOT_SUBMITTED", **extra) -> tuple[int, dict]:
    """End a run that has a directory and no receipt: the envelope goes to `status.json` and to the caller."""
    envelope = {"status": status, "reason": reason, "sessionId": session, "dir": str(out), **extra}
    if not (out / "status.json").exists():
        _private(out / "status.json", json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return code, envelope


def _signed_in_here(p: dict, session: str, out: Path, *, timeout: float, browser: bool, sign_in, say, now) -> tuple[dict, dict]:
    """Show the person at this terminal the task, sign them in and return (what to deposit, what the receipt records)."""
    intro = _show(say, p["tenant"], p["agent"], p["release"], session, p["task"])
    signed = (sign_in or delegation.sign_in)(p["tenant"], p["agent"], intro=intro, prompt=delegation.PROMPT_REUSE, timeout=timeout, browser=browser, say=say)
    if signed is None:
        raise _Ended(NO_CONSENT, "the sign-in was not completed in time; no token was sent to the cluster and no workflow was started", timeoutSeconds=timeout)
    report = delegation.assess(signed["claims"], p["tenant"], p["agent"], now=now())
    _say_who(say, report)
    if not report["wouldBeAcceptedForDeposit"]:
        raise _Ended(
            1,
            "the token Keycloak issued would not be accepted for deposit; no token was sent to the cluster and no workflow was started",
            subject=report["subject"],
            preferredUsername=report.get("preferredUsername"),
            missing=report["missing"],
        )
    terms = delegation.deposit_terms(signed, now=now())
    if not terms["refreshTokenIssued"]:
        say(f"Keycloak issued no refresh token: {p['agent']} can act for you only until the access token expires at {terms['expiresAt']}.")
    deposit = {"access_token": signed["tokens"]["access"], "refresh_token": terms["refresh"], "expires_at": terms["expiresAt"]}
    return deposit, {"mode": "inline", "subject": report["subject"], "subjectSource": "verified access token", "refreshTokenIssued": terms["refreshTokenIssued"], "grantRequestedUntil": terms["expiresAt"]}


def _consent_record(out: Path, session: str) -> dict | None:
    try:
        record = json.loads((out / CONSENT_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) and record.get("sessionId") == session else None


def _no_workflow(out: Path, what: str) -> str:
    """Why a run that waited for consent ended, with what this machine knows about a deposit."""
    if (out / CONSENT_RECORD).exists():
        return f"{what} after a consent command deposited a token for this session; no workflow was started, and {GRANT_MAY_BE_HELD}"
    if (out / DEPOSIT_ATTEMPT).exists():
        return f"{what}; a consent command sent a token and recorded no deposit, so {GRANT_MAY_BE_HELD}; no workflow was started"
    return f"{what}; no consent command reached the deposit step and no workflow was started"


def _awaited(p: dict, session: str, out: Path, *, timeout: float, say, sleep, clock) -> tuple[dict | None, tuple[int, dict] | None]:
    """Wait for `consent` to leave its record beside this run: (what the receipt records, None), or (None, the exit) when the run ends here."""
    command = f"just agent consent {p['agent']} --session {session}"
    where = Path(os.path.abspath(out))
    # The consent command looks a run up under the default directory by the session prefix; any other directory has to be named.
    if where.parent != runs_base() / p["agent"] or not fnmatch.fnmatchcase(where.name, f"*-{session[:8]}"):
        command += f" --run-dir {shlex.quote(str(where))}"
    try:
        with _locked(out / WAITING_LOCK):
            say(f"{p['agent']} acts on behalf of a person and this run cannot sign anyone in (stdin and stderr are not both a terminal). Within {timeout:.0f} seconds that person runs, in a terminal on this machine: {command}")
            deadline = clock() + timeout
            while not (out / CONSENT_RECORD).exists():
                remaining = deadline - clock()
                if remaining <= 0:
                    # A `consent` that is depositing holds this lock until its record is written, so what is seen under it is final.
                    with _locked(out / DEPOSIT_LOCK):
                        if (out / CONSENT_RECORD).exists():
                            break
                        # Written under the lock: it is what tells a `consent` that arrives now that this run is over.
                        return None, _not_submitted(out, session, NO_CONSENT, _no_workflow(out, "no consent was recorded in time"), timeoutSeconds=timeout)
                sleep(min(CONSENT_POLL, remaining))
    except KeyboardInterrupt:
        # Under the same lock as giving up, for the same reason. A second interrupt while a deposit holds it ends in `submit`.
        with _locked(out / DEPOSIT_LOCK):
            return None, _not_submitted(out, session, INTERRUPTED, _no_workflow(out, "interrupted while waiting for consent"))
    record = _consent_record(out, session)
    if record is None:
        return None, _not_submitted(out, session, 1, f"{out / CONSENT_RECORD} is not a consent record for this session; no workflow was started. If a consent command deposited a token, {GRANT_MAY_BE_HELD}")
    # The policy service's grant record names no person, so the subject is what the consent command wrote, not something this run verified.
    consent = {"mode": "awaited", "subject": record.get("subject"), "subjectSource": "consent command record", "refreshTokenIssued": record.get("refreshTokenIssued"), "grantRequestedUntil": record.get("grantRequestedUntil")}
    # The person consented to what the consent command showed them. Nothing is started unless that is what this run holds.
    if not hmac.compare_digest(str(record.get("shownSha256")), shown_digest(p["tenant"], p["agent"], p["release"], session, p["task"])):
        reason = "the consent record does not carry the digest of this run's tenant, agent, release, session and task, so the person was not shown what this run would submit"
        return None, _not_submitted(out, session, 1, f"{reason}; no workflow was started, and {GRANT_MAY_BE_HELD}", consent=consent)
    return consent, None


def submit(
    root: Path,
    agent: str,
    task,
    *,
    release: str | None = None,
    grant_handle: str | None = None,
    max_boundaries: int = 64,
    wait: bool = True,
    wait_timeout: float = 900,
    poll_interval: float = 10,
    cancel_on_timeout: bool = False,
    out: Path | None = None,
    kube: live.Kube | None = None,
    sleep=time.sleep,
    clock=time.monotonic,
    consent_timeout: float = delegation.DEFAULT_TIMEOUT,
    browser: bool = False,
    is_tty=None,
    sign_in=None,
    say=None,
    now=time.time,
) -> tuple[int, dict]:
    kube = kube or live.Kube()
    p = plan(root, kube, agent, release=release, grant_handle=grant_handle, task=task)
    inline = False
    if p["consent"]:
        if not 0 < consent_timeout <= delegation.MAX_TIMEOUT:
            raise RunError(f"--consent-timeout must be above 0 and at most {delegation.MAX_TIMEOUT:.0f} seconds")
        inline = (is_tty or delegation.interactive)()
        if inline:
            delegation.require_pyjwt()  # before a run directory exists and before anyone is asked to sign in
    say = say or _stderr
    session = str(uuid.uuid4())
    out = out or default_out(agent, session)
    runner = Runner(kube, p["tenant"], out)  # the pod is located before a run directory exists and before anyone is asked to consent
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chmod(out, 0o700)  # whatever the umask: `consent` trusts a run directory only at exactly this mode
    public = {"action": "submit", "tenant": p["tenant"], "agent": agent, "release": p["release"], "session_id": session, "task": task, "max_boundaries": max_boundaries}
    _private(out / "request.json", json.dumps(public, indent=2, sort_keys=True) + "\n")
    request = dict(public, grant_handle=grant_handle)
    consent = None
    # From here to the receipt, every ending writes `status.json` and returns its envelope.
    try:
        if p["consent"] and inline:
            # Deposit and start travel in one remote call, so no host-side step separates the grant from its session.
            request["deposit"], consent = _signed_in_here(p, session, out, timeout=consent_timeout, browser=browser, sign_in=sign_in, say=say, now=now)
        elif p["consent"]:
            consent, ended = _awaited(p, session, out, timeout=consent_timeout, say=say, sleep=sleep, clock=clock)
            if ended is not None:
                return ended
            request["deposited_grant"] = True
    except _Ended as end:
        return _not_submitted(out, session, end.code, end.reason, **end.extra)
    except KeyboardInterrupt:
        if inline:
            return _not_submitted(out, session, INTERRUPTED, "interrupted during the sign-in; no token was sent to the cluster and no workflow was started")
        return _not_submitted(out, session, INTERRUPTED, _no_workflow(out, "interrupted while waiting for consent"))
    except (delegation.ConsentError, RunError) as exc:
        # Only the sign-in at this terminal raises here, and it failed before any token left this process.
        return _not_submitted(out, session, 2, f"{exc}; no token was sent to the cluster and no workflow was started")
    # What is true of the grant when the submit call does not return a started workflow.
    held = f"; {GRANT_MAY_BE_HELD}" if p["consent"] else ""
    try:
        accepted = runner.remote(request)
    except KeyboardInterrupt:
        return _not_submitted(out, session, INTERRUPTED, f"interrupted while the submit call was in flight; whether a workflow was started is not known{held}", status="SUBMIT_UNCONFIRMED", consent=consent)
    except RunError as exc:
        if "deposit" in request and any(answer in str(exc) for answer in NO_GRANT_ANSWERS):
            held = "; the policy service holds no grant from this run"
        return _not_submitted(out, session, 2, f"{exc}{held}", status="SUBMIT_UNCONFIRMED", consent=consent)
    finally:
        request.pop("deposit", None)
    if accepted.get("granted") is False:
        # The consent command recorded a deposit, yet the policy service holds no grant for this session: it expired, or the
        # cleanup reconciler passed between the deposit and this call and closed a session that had no workflow yet.
        return _not_submitted(out, session, 1, "consent was recorded but the policy service no longer holds a grant for this session; no workflow was started; run again and consent again", consent=consent)
    receipt = {
        "schemaVersion": 1,
        "tenant": p["tenant"],
        "agent": agent,
        "release": p["release"],
        "sessionId": session,
        "identity": p["identity"],
        "delegated": p["delegated"],
        "consent": consent,
        "workflowId": accepted["workflow_id"],
        "runId": accepted["run_id"],
        "namespace": accepted["namespace"],
        "taskQueue": accepted["task_queue"],
        "runnerPodUid": runner.pod["uid"],
        "remoteSha256": hashlib.sha256(runner.code).hexdigest(),
        "submittedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dir": str(out),
    }
    _private(out / "receipt.json", json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if not wait:
        return 0, {"receipt": receipt, "status": "SUBMITTED", "cleanup": "NOT_CONFIRMED"}
    try:
        return follow(receipt, runner, wait_timeout=wait_timeout, poll_interval=poll_interval, cancel_on_timeout=cancel_on_timeout, sleep=sleep, clock=clock)
    except KeyboardInterrupt:
        reason = f"interrupted while following the run; the workflow was not cancelled, and `just agent status --receipt {out / 'receipt.json'}` reads it"
        return INTERRUPTED, {"receipt": receipt, "status": "INTERRUPTED", "reason": reason, "cleanup": "NOT_CONFIRMED"}


def _identity(receipt: dict, action: str) -> dict:
    return {
        "action": action,
        "tenant": receipt["tenant"],
        "agent": receipt["agent"],
        "session_id": receipt["sessionId"],
        "run_id": receipt["runId"],
    }


def follow(receipt: dict, runner: Runner, *, wait_timeout: float, poll_interval: float, cancel_on_timeout: bool, sleep=time.sleep, clock=time.monotonic) -> tuple[int, dict]:
    deadline = clock() + wait_timeout
    status = None
    while True:
        status = runner.remote(_identity(receipt, "status"))
        if status["status"] in TERMINAL:
            break
        remaining = deadline - clock()
        if remaining <= 0:
            envelope = {"receipt": receipt, "status": status["status"], "query": status.get("query"), "cleanup": "NOT_CONFIRMED", "timedOut": True}
            if cancel_on_timeout:
                envelope["cancel"] = runner.remote(_identity(receipt, "cancel"))
            _private(runner.out / "status.json", json.dumps(envelope, indent=2, sort_keys=True) + "\n")
            return 124, envelope
        sleep(min(poll_interval, remaining))
    return finish(receipt, runner, status)


def finish(receipt: dict, runner: Runner, status: dict) -> tuple[int, dict]:
    envelope = {
        "receipt": receipt,
        "status": status["status"],
        "query": status.get("query"),
        "result": status.get("result"),
        "confirmed": status.get("confirmed", False),
        "cleanup": "CONFIRMED" if status.get("confirmed") else "NOT_CONFIRMED",
        "runnerIdentityChanged": runner.identity_changed,
    }
    code = 1
    if status["status"] == "COMPLETED" and status.get("confirmed"):
        report = runner.remote(_identity(receipt, "report"))
        _private(runner.out / "report.md", report["report"])
        envelope["report"] = str(runner.out / "report.md")
        envelope["workspace"] = report.get("workspace", [])
        code = 0
    _private(runner.out / "status.json", json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return code, envelope


def resume(receipt_path: Path, action: str, *, kube: live.Kube | None = None, wait_timeout: float = 900, poll_interval: float = 10, sleep=time.sleep, clock=time.monotonic) -> tuple[int, dict]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schemaVersion") != 1:
        raise RunError("unsupported receipt")
    kube = kube or live.Kube()
    out = receipt_path.parent
    runner = Runner(kube, receipt["tenant"], out)
    for name in ("status.json", "report.md"):
        if (out / name).exists():
            (out / name).rename(out / f"{name}.{int(time.time())}")
    if action == "status":
        status = runner.remote(_identity(receipt, "status"))
        if status["status"] in TERMINAL:
            return finish(receipt, runner, status)
        return 1, {"receipt": receipt, "status": status["status"], "query": status.get("query"), "cleanup": "NOT_CONFIRMED"}
    if action == "wait":
        return follow(receipt, runner, wait_timeout=wait_timeout, poll_interval=poll_interval, cancel_on_timeout=False, sleep=sleep, clock=clock)
    if action == "cancel":
        return 1, {"receipt": receipt, "cancel": runner.remote(_identity(receipt, "cancel")), "cleanup": "NOT_CONFIRMED"}
    raise RunError("unknown action")


def _stat_directory(path: Path) -> os.stat_result:
    return os.stat(path)


def _stat_open_file(fd: int) -> os.stat_result:
    return os.fstat(fd)


def _own_request(candidate: Path) -> dict:
    """The request of a run directory that only the caller can have written.

    The directory decides what the person is shown and what `consent` records as shown, so one another account
    owns or can write to is refused. ConsentError names what is wrong; OSError or ValueError means there is no
    request to read.
    """
    me = os.geteuid()
    held = _stat_directory(candidate)
    if not stat.S_ISDIR(held.st_mode):
        raise NotADirectoryError(str(candidate))
    if held.st_uid != me:
        raise delegation.ConsentError(f"{candidate} is not owned by you; consent is given only to a run you started")
    if stat.S_IMODE(held.st_mode) != 0o700:
        raise delegation.ConsentError(f"{candidate} has mode {stat.S_IMODE(held.st_mode):04o}, not 0700 as `just agent run` creates it; another account could have changed what it says the run will do")
    try:
        # Non-blocking, so a named pipe put in the file's place is refused below and not waited on.
        fd = os.open(candidate / "request.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise delegation.ConsentError(f"{candidate / 'request.json'} is a symbolic link, not the file `just agent run` wrote") from None
        raise
    try:
        # Asked of the open descriptor before anything is read from it: a directory or a pipe cannot be read as the request.
        entry = _stat_open_file(fd)
        if not stat.S_ISREG(entry.st_mode) or entry.st_uid != me:
            raise delegation.ConsentError(f"{candidate / 'request.json'} is not a regular file owned by you; consent is given only to a run you started")
        with os.fdopen(os.dup(fd), "rb") as source:
            return json.loads(source.read(MAX_REQUEST_BYTES).decode("utf-8"))
    finally:
        os.close(fd)


def _waiting_run(tenant: str, agent: str, session: str, run_dir: Path | None) -> tuple[Path, dict]:
    """The directory and request of the run on this machine that is waiting for consent to this session."""
    try:
        canonical = str(uuid.UUID(session)) == session
    except ValueError:
        canonical = False
    if not canonical:
        raise delegation.ConsentError("--session takes the session id `just agent run` printed, a lower-case UUID")
    base = runs_base() / agent
    candidates = [run_dir] if run_dir is not None else sorted(base.glob(f"*-{session[:8]}")) if base.is_dir() else []
    distrusted = None
    for candidate in candidates:
        try:
            request = _own_request(candidate)
        except delegation.ConsentError as exc:
            distrusted = distrusted or exc
            continue
        except (OSError, ValueError):
            continue
        if isinstance(request, dict) and (request.get("session_id"), request.get("agent"), request.get("tenant")) == (session, agent, tenant):
            return candidate, request
    if distrusted is not None:
        raise distrusted
    raise delegation.ConsentError(f"no run of {agent} on this machine is waiting for consent to session {session}; consent is given where `just agent run` is waiting (add --run-dir DIR when the run was started with --out)")


def _still_waiting(out: Path) -> None:
    """Refuse unless the run in this directory is alive and still waiting for consent."""
    if (out / CONSENT_RECORD).exists():
        raise delegation.ConsentError("consent was already given for this session; this command deposited nothing")
    if (out / "receipt.json").exists() or (out / "status.json").exists():
        raise delegation.ConsentError("this run is no longer waiting for consent; this command deposited nothing")
    try:
        fd = os.open(out / WAITING_LOCK, os.O_RDWR)
    except OSError:
        raise delegation.ConsentError("this run is not waiting for consent; this command deposited nothing") from None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return  # held by the waiting run
        raise delegation.ConsentError("the run that asked for this consent has ended; this command deposited nothing")
    finally:
        os.close(fd)


def consent(
    root: Path,
    agent: str,
    session: str,
    *,
    run_dir: Path | None = None,
    timeout: float = delegation.DEFAULT_TIMEOUT,
    browser: bool = False,
    kube: live.Kube | None = None,
    is_tty=None,
    sign_in=None,
    say=None,
    now=time.time,
) -> tuple[int, dict]:
    """A person consents, at their own terminal, to the session a `run` on this machine is waiting to start."""
    tenant = delegation.tenant_of(root, agent)
    if not (is_tty or delegation.interactive)():
        raise delegation.ConsentError("consent is given by a person at their own terminal: stdin and stderr must both be a TTY")
    if not 0 < timeout <= delegation.MAX_TIMEOUT:
        raise delegation.ConsentError(f"--timeout must be above 0 and at most {delegation.MAX_TIMEOUT:.0f} seconds")
    out, request = _waiting_run(tenant, agent, session, run_dir)
    _still_waiting(out)
    delegation.require_pyjwt()
    runner = Runner(kube or live.Kube(), tenant, out, stderr_prefix="consent-exec")  # the pod is located before the person is asked
    say = say or _stderr
    release, task = request.get("release"), request.get("task")
    intro = _show(say, tenant, agent, release, session, task)
    # What the lines above were built from, read once: the waiting run starts nothing unless it holds the same.
    shown = shown_digest(tenant, agent, release, session, task)
    base = {"agent": agent, "tenant": tenant, "sessionId": session, "runDir": str(out)}
    try:
        signed = (sign_in or delegation.sign_in)(tenant, agent, intro=intro, prompt=delegation.PROMPT_REUSE, timeout=timeout, browser=browser, say=say)
    except KeyboardInterrupt:
        return INTERRUPTED, dict(base, deposited=False, interrupted=True)
    if signed is None:
        return 124, dict(base, deposited=False, timedOut=True, timeoutSeconds=timeout)
    report = delegation.assess(signed["claims"], tenant, agent, now=now())
    _say_who(say, report)
    who = {"subject": report["subject"], "preferredUsername": report.get("preferredUsername")}
    if not report["wouldBeAcceptedForDeposit"]:
        return 1, dict(base, deposited=False, **who, missing=report["missing"])
    terms = delegation.deposit_terms(signed, now=now())
    record = {"schemaVersion": 1, "sessionId": session, "agent": agent, "tenant": tenant, "shownSha256": shown, "subject": report["subject"], "refreshTokenIssued": terms["refreshTokenIssued"], "grantRequestedUntil": terms["expiresAt"]}
    with _locked(out / DEPOSIT_LOCK):
        _still_waiting(out)  # again, now that no `run` can give up and no second `consent` can deposit until the record exists
        staged = out / (CONSENT_RECORD + ".tmp")
        staged.unlink(missing_ok=True)  # left by a consent command that died; cleared before the deposit, so the record can be written after it
        deposit = {"access_token": signed["tokens"]["access"], "refresh_token": terms["refresh"], "expires_at": terms["expiresAt"]}
        attempt = out / DEPOSIT_ATTEMPT
        first = not attempt.exists()
        with os.fdopen(os.open(attempt, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a", encoding="utf-8") as mark:
            mark.write(_utc(now()) + "\n")
        try:
            answer = runner.remote({"action": "deposit", "tenant": tenant, "agent": agent, "session_id": session, "deposit": deposit})
        except KeyboardInterrupt:
            return INTERRUPTED, dict(base, deposited=None, interrupted=True, **who, reason=f"interrupted while the deposit was in flight; whether it took effect is not known, and {GRANT_MAY_BE_HELD}")
        except RunError as exc:
            if any(refusal in str(exc) for refusal in NO_GRANT_ANSWERS):
                if first:
                    attempt.unlink(missing_ok=True)  # an earlier attempt whose outcome is unknown keeps its mark
                return 2, dict(base, deposited=False, **who, reason=f"{exc}; this command deposited nothing")
            return 2, dict(base, deposited=None, **who, reason=f"{exc}; {GRANT_MAY_BE_HELD}")
        finally:
            deposit.clear()
        if answer.get("deposited") is not True:
            return 2, dict(base, deposited=None, **who, reason=f"remote deposit did not confirm the deposit; whether it took effect is not known, and {GRANT_MAY_BE_HELD}")
        record["depositedAt"] = _utc(now())
        # Renamed into place: the waiting run acts on this file the moment it exists, so it must never be seen half written.
        _private(staged, json.dumps(record, indent=2, sort_keys=True) + "\n")
        os.rename(staged, out / CONSENT_RECORD)
        attempt.unlink(missing_ok=True)
    result = dict(base, deposited=True, **who, refreshTokenIssued=terms["refreshTokenIssued"], grantRequestedUntil=terms["expiresAt"])
    if not terms["refreshTokenIssued"]:
        result["note"] = "Keycloak issued no refresh token: the agent can act for you only until the access token expires, at grantRequestedUntil"
    return 0, result
