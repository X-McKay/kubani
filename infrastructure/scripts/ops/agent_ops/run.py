"""Submit, follow and report one ordinary session through the tenant's Session Runner."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import layout, live

REMOTE = Path(__file__).with_name("remote_session.py")
PYTHON = "/app/.venv/bin/python"
TERMINAL = {"COMPLETED", "FAILED", "CANCELED", "TERMINATED", "TIMED_OUT", "CONTINUED_AS_NEW"}
EXEC_TIMEOUT = 60
MAX_TASK_BYTES = 16 * 1024


class RunError(Exception):
    pass


def default_out(agent: str, session: str) -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "kubani/agent-runs"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return base / agent / f"{stamp}-{session[:8]}"


def _private(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(text)


class Runner:
    def __init__(self, kube: live.Kube, tenant: str, out: Path):
        self.kube = kube
        self.tenant = tenant
        self.out = out
        self.pod = live.runner_pod(kube, tenant)
        self.code = REMOTE.read_bytes()
        self.calls = 0
        self.identity_changed = False

    def remote(self, request: dict) -> dict:
        self.calls += 1
        argv = [PYTHON, "-", json.dumps(request, sort_keys=True)]
        proc = self.kube.exec(self.pod["name"], live.PLATFORM_NAMESPACE, "runner", argv, self.code, EXEC_TIMEOUT)
        stderr = proc.stderr.decode("utf-8", "replace")[-4000:]
        if stderr:
            _private(self.out / f"exec-{self.calls:02d}.stderr", stderr)
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
    if mode == "on-behalf-of" and grant_handle is None:
        # Only a release that reports delegation as not required runs without a grant; the APS
        # then applies the Agent's fallback per backend. Unreported is not "not required".
        if view.delegation_required is True:
            raise RunError(f"{agent} runs on behalf of a human; pass --grant-handle from a consented delegation")
        if view.delegation_required is not False:
            raise RunError(f"{agent}: release {view.name} does not report whether delegation is required")
    encoded = json.dumps(task, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_TASK_BYTES:
        raise RunError("task exceeds 16 KiB")
    return {"tenant": d.tenant, "agent": agent, "release": view.name, "identity": mode, "delegated": grant_handle is not None, "task": task}


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
) -> tuple[int, dict]:
    kube = kube or live.Kube()
    p = plan(root, kube, agent, release=release, grant_handle=grant_handle, task=task)
    session = str(uuid.uuid4())
    out = out or default_out(agent, session)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    runner = Runner(kube, p["tenant"], out)
    request = {
        "action": "submit",
        "tenant": p["tenant"],
        "agent": agent,
        "release": p["release"],
        "session_id": session,
        "grant_handle": grant_handle,
        "task": task,
        "max_boundaries": max_boundaries,
    }
    _private(out / "request.json", json.dumps({k: v for k, v in request.items() if k != "grant_handle"}, indent=2, sort_keys=True) + "\n")
    accepted = runner.remote(request)
    receipt = {
        "schemaVersion": 1,
        "tenant": p["tenant"],
        "agent": agent,
        "release": p["release"],
        "sessionId": session,
        "identity": p["identity"],
        "delegated": p["delegated"],
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
