"""Submit, follow and report one ordinary session through the tenant's Session Runner.

An agent whose release requires delegation needs a person's consent before it starts. `submit` obtains
it in one of two ways and `consent` is the other half of the second:

- started from a terminal, `submit` signs the person in itself and hands the token to the runner pod,
  which deposits it and starts the session in the same remote call;
- otherwise `submit` waits, and the person runs `consent` in their own terminal. `consent` deposits the
  token through the same pod and leaves a record beside the waiting run; `submit` then asks the pod to
  start the session with the grant the policy service holds for that session id.

The person's token travels from the sign-in to the standard input of `kubectl exec` and nowhere else.
The grant handle never leaves the pod: no path here reads, prints or stores one, except a handle the
submitter passes in with `--grant-handle`.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
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
# Exit code: the release requires a person's consent, none arrived in time, nothing was deposited or submitted.
NO_CONSENT = 3
CONSENT_POLL = 0.5
CONSENT_RECORD = "consent.json"
# Held by a `run` for as long as it waits for consent; the kernel releases it if the process dies.
WAITING_LOCK = "waiting.lock"
# Held by `consent` from its last look at the run until its record is written, and by `run` when it gives up.
DEPOSIT_LOCK = "deposit.lock"
SHOWN_TASK_CHARS = 2000


class RunError(Exception):
    pass


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


def _not_submitted(out: Path, session: str, code: int, reason: str, **extra) -> tuple[int, dict]:
    envelope = {"status": "NOT_SUBMITTED", "reason": reason, "sessionId": session, "dir": str(out), **extra}
    if not (out / "status.json").exists():
        _private(out / "status.json", json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return code, envelope


def _signed_in_here(p: dict, session: str, *, timeout: float, browser: bool, sign_in, say, now) -> tuple[dict, dict] | None:
    """Sign the person at this terminal in and return (what to deposit, what the receipt records), or None when they did not answer."""
    intro = f"{p['agent']} (tenant {p['tenant']}, release {p['release']}) will act as you for session {session}: open this URL, sign in if asked and answer the consent screen."
    signed = (sign_in or delegation.sign_in)(p["tenant"], p["agent"], intro=intro, prompt=delegation.PROMPT_REUSE, timeout=timeout, browser=browser, say=say)
    if signed is None:
        return None
    report = delegation.assess(signed["claims"], p["tenant"], p["agent"], now=now())
    if not report["wouldBeAcceptedForDeposit"]:
        raise RunError("the token Keycloak issued would not be accepted for deposit, so nothing was deposited or submitted: " + "; ".join(report["missing"]))
    terms = delegation.deposit_terms(signed, now=now())
    if not terms["refreshTokenIssued"]:
        say(f"Keycloak issued no refresh token: {p['agent']} can act for you only until the access token expires at {terms['expiresAt']}.")
    deposit = {"access_token": signed["tokens"]["access"], "refresh_token": terms["refresh"], "expires_at": terms["expiresAt"]}
    return deposit, {"mode": "inline", "subject": report["subject"], "subjectSource": "verified access token", "refreshTokenIssued": terms["refreshTokenIssued"], "grantExpiresAt": terms["expiresAt"]}


def _consent_record(out: Path, session: str) -> dict:
    try:
        record = json.loads((out / CONSENT_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = None
    if not isinstance(record, dict) or record.get("sessionId") != session:
        raise RunError(f"{out / CONSENT_RECORD} is not a consent record for this session")
    return record


def _awaited(p: dict, session: str, out: Path, *, timeout: float, say, sleep, clock) -> tuple[dict | None, tuple[int, dict] | None]:
    """Wait for `consent` to leave its record beside this run: (what the receipt records, None), or (None, the exit) when nobody consented in time."""
    command = f"just agent consent {p['agent']} --session {session}"
    if out.parent != runs_base() / p["agent"]:
        command += f" --run-dir {out}"
    with _locked(out / WAITING_LOCK):
        say(f"{p['agent']} acts on behalf of a person and this run cannot sign anyone in (not started from a terminal, or --await-consent). Within {timeout:.0f} seconds that person runs, in a terminal on this machine: {command}")
        deadline = clock() + timeout
        while not (out / CONSENT_RECORD).exists():
            remaining = deadline - clock()
            if remaining <= 0:
                # A `consent` that is depositing holds this lock until its record is written, so what is seen under it is final.
                with _locked(out / DEPOSIT_LOCK):
                    if (out / CONSENT_RECORD).exists():
                        break
                    # Written under the lock: it is what tells a `consent` that arrives now that this run is over.
                    return None, _not_submitted(out, session, NO_CONSENT, "no consent arrived in time; nothing was deposited or submitted", timeoutSeconds=timeout)
            sleep(min(CONSENT_POLL, remaining))
    record = _consent_record(out, session)
    # The policy service's grant record names no person, so the subject is what the consent command wrote, not something this run verified.
    return {"mode": "awaited", "subject": record.get("subject"), "subjectSource": "consent command record", "refreshTokenIssued": record.get("refreshTokenIssued"), "grantExpiresAt": record.get("grantExpiresAt")}, None


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
    await_consent: bool = False,
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
        inline = not await_consent and (is_tty or delegation.interactive)()
        if inline:
            delegation.require_pyjwt()  # before a run directory exists and before anyone is asked to sign in
    elif await_consent:
        raise RunError(f"--await-consent applies only when the release requires delegation and no --grant-handle is given; {agent} would not ask for consent")
    say = say or _stderr
    session = str(uuid.uuid4())
    out = out or default_out(agent, session)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    runner = Runner(kube, p["tenant"], out)  # the pod is located before anyone is asked to consent
    public = {"action": "submit", "tenant": p["tenant"], "agent": agent, "release": p["release"], "session_id": session, "task": task, "max_boundaries": max_boundaries}
    _private(out / "request.json", json.dumps(public, indent=2, sort_keys=True) + "\n")
    request = dict(public, grant_handle=grant_handle)
    consent = None
    if p["consent"] and inline:
        signed = _signed_in_here(p, session, timeout=consent_timeout, browser=browser, sign_in=sign_in, say=say, now=now)
        if signed is None:
            return _not_submitted(out, session, NO_CONSENT, "the sign-in was not completed in time; nothing was deposited or submitted", timeoutSeconds=consent_timeout)
        # Deposit and start travel in one remote call, so no host-side step separates the grant from its session.
        request["deposit"], consent = signed
    elif p["consent"]:
        consent, gave_up = _awaited(p, session, out, timeout=consent_timeout, say=say, sleep=sleep, clock=clock)
        if gave_up is not None:
            return gave_up
        request["deposited_grant"] = True
    try:
        accepted = runner.remote(request)
    finally:
        request.pop("deposit", None)
    if accepted.get("granted") is False:
        # The consent command recorded a deposit, yet the policy service holds no grant for this session: it expired, or the
        # cleanup reconciler passed between the deposit and this call and closed a session that had no workflow yet.
        return _not_submitted(out, session, 1, "consent was recorded but the policy service no longer holds a grant for this session; run again and consent again", consent=consent)
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
    return follow(receipt, runner, wait_timeout=wait_timeout, poll_interval=poll_interval, cancel_on_timeout=cancel_on_timeout, sleep=sleep, clock=clock)


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
    for candidate in candidates:
        try:
            request = json.loads((candidate / "request.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(request, dict) and (request.get("session_id"), request.get("agent"), request.get("tenant")) == (session, agent, tenant):
            return candidate, request
    raise delegation.ConsentError(f"no run of {agent} on this machine is waiting for consent to session {session}; consent is given where `just agent run` is waiting (add --run-dir DIR when the run was started with --out)")


def _still_waiting(out: Path) -> None:
    """Refuse unless the run in this directory is alive and still waiting for consent."""
    if (out / CONSENT_RECORD).exists():
        raise delegation.ConsentError("consent was already given for this session; nothing was deposited")
    if (out / "receipt.json").exists() or (out / "status.json").exists():
        raise delegation.ConsentError("this run is no longer waiting for consent; nothing was deposited")
    try:
        fd = os.open(out / WAITING_LOCK, os.O_RDWR)
    except OSError:
        raise delegation.ConsentError("this run is not waiting for consent; nothing was deposited") from None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return  # held by the waiting run
        raise delegation.ConsentError("the run that asked for this consent has ended; nothing was deposited")
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
        raise delegation.ConsentError("consent is given by a person at their own terminal: stdin, stdout and stderr must all be a TTY")
    if not 0 < timeout <= delegation.MAX_TIMEOUT:
        raise delegation.ConsentError(f"--timeout must be above 0 and at most {delegation.MAX_TIMEOUT:.0f} seconds")
    out, request = _waiting_run(tenant, agent, session, run_dir)
    _still_waiting(out)
    delegation.require_pyjwt()
    runner = Runner(kube or live.Kube(), tenant, out, stderr_prefix="consent-exec")  # the pod is located before the person is asked
    say = say or _stderr
    shown = json.dumps(request.get("task"), sort_keys=True)
    if len(shown) > SHOWN_TASK_CHARS:
        shown = shown[:SHOWN_TASK_CHARS] + f"... ({len(shown)} characters; the whole task is in {out / 'request.json'})"
    say(f"Task: {shown}")
    intro = f"{agent} (tenant {tenant}, release {request.get('release')}) will act as you for session {session}, on the task above: open this URL, sign in if asked and answer the consent screen."
    signed = (sign_in or delegation.sign_in)(tenant, agent, intro=intro, prompt=delegation.PROMPT_REUSE, timeout=timeout, browser=browser, say=say)
    base = {"agent": agent, "tenant": tenant, "sessionId": session, "runDir": str(out)}
    if signed is None:
        return 124, dict(base, deposited=False, timedOut=True, timeoutSeconds=timeout)
    report = delegation.assess(signed["claims"], tenant, agent, now=now())
    if not report["wouldBeAcceptedForDeposit"]:
        return 1, dict(base, deposited=False, subject=report["subject"], preferredUsername=report.get("preferredUsername"), missing=report["missing"])
    terms = delegation.deposit_terms(signed, now=now())
    record = {"schemaVersion": 1, "sessionId": session, "agent": agent, "tenant": tenant, "subject": report["subject"], "refreshTokenIssued": terms["refreshTokenIssued"], "grantExpiresAt": terms["expiresAt"]}
    with _locked(out / DEPOSIT_LOCK):
        _still_waiting(out)  # again, now that no `run` can give up and no second `consent` can deposit until the record exists
        staged = out / (CONSENT_RECORD + ".tmp")
        staged.unlink(missing_ok=True)  # left by a consent command that died; cleared before the deposit, so the record can be written after it
        deposit = {"access_token": signed["tokens"]["access"], "refresh_token": terms["refresh"], "expires_at": terms["expiresAt"]}
        try:
            answer = runner.remote({"action": "deposit", "tenant": tenant, "agent": agent, "session_id": session, "deposit": deposit})
        finally:
            deposit.clear()
        if answer.get("deposited") is not True:
            raise RunError("remote deposit did not confirm the deposit; whether it took effect is not known")
        record["depositedAt"] = _utc(now())
        # Renamed into place: the waiting run acts on this file the moment it exists, so it must never be seen half written.
        _private(staged, json.dumps(record, indent=2, sort_keys=True) + "\n")
        os.rename(staged, out / CONSENT_RECORD)
    result = dict(base, deposited=True, subject=report["subject"], preferredUsername=report.get("preferredUsername"), refreshTokenIssued=terms["refreshTokenIssued"], grantExpiresAt=terms["expiresAt"])
    if not terms["refreshTokenIssued"]:
        result["note"] = "Keycloak issued no refresh token: the agent can act for you only until the access token expires, at grantExpiresAt"
    return 0, result
