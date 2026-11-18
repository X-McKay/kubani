"""The delivery path of agents the registry owns: sessions over HTTP, the signed-in release commands and revocation files.

An agent is on this path when the live Agent carries the registry's annotation (`registry_owned`); the decision reads the
object `run` already reads and asks the registry nothing, so an agent on the old path behaves as it always did while the
registry is down. On this path a session is started, read and cancelled through the tenant's session interface at
`<registry URL>/v1/tenants/<tenant>/sessions` with the person's own token (zetra platform/session-api/contract/sessions.md),
and nothing goes through `kubectl exec`. Release changes are one registry route each (zetra platform/registry/contract/
delivery.md sections 6 to 8). A person's token is held in memory only and is never written or printed.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

import outcome

from . import layout, live, registry_client, run

ANNOTATION_PREFIX = "registry.agentplatform.io/"
OWNER_ANNOTATION = ANNOTATION_PREFIX + "deployment"
CURRENT_ANNOTATION = ANNOTATION_PREFIX + "current-release"
PATH_NAME = "session-interface"
RECEIPT_VERSION = 2
MAX_TASK_BYTES = 64 * 1024
DEFAULT_BOUNDARIES = 64
REVOCATIONS = Path("infrastructure/registry/revocations")
NAME_PART = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\Z")
# The session's `outcome` as the receipt's `status` says it, in the words the runner's statuses use.
STATUS = {"completed": "COMPLETED", "failed": "FAILED", "cancelled": "CANCELED", "timed-out": "TIMED_OUT", "not-confirmed": "NOT_CONFIRMED"}


class DeliveryError(outcome.Coded):
    """A delivery command was refused before the registry or the session interface was asked."""

    default_code = "refused"


# ---- which path ----------------------------------------------------------------------------


def registry_owned(agent: dict | None) -> bool:
    """True when the live Agent object carries the registry's deployment annotation: the registry owns the agent."""
    meta = (agent or {}).get("metadata") or {}
    return isinstance((meta.get("annotations") or {}).get(OWNER_ANNOTATION), str)


def live_agent(kube, tenant: str, agent: str) -> dict | None:
    """The live Agent object, or None when it cannot be read: the old path then reports its own read error."""
    try:
        items = kube.get("agents", None, tenant).get("items", [])
    except live.LiveError:
        return None
    return next((i for i in items if (i.get("metadata") or {}).get("name") == agent), None)


def new_path(root: Path, kube, agent: str) -> tuple[layout.AgentDir, dict] | None:
    """(the agent's directory, the live Agent) when the registry owns the agent, else None."""
    try:
        d = layout.find_agent(root, agent)
    except layout.LayoutError:
        return None  # the old path names the missing or doubled directory in its own words
    found = live_agent(kube, d.tenant, agent)
    return (d, found) if registry_owned(found) else None


# ---- sessions ------------------------------------------------------------------------------


def sessions_path(tenant: str, agent: str | None = None, session: str | None = None) -> str:
    path = f"/v1/tenants/{registry_client.segment(tenant)}/sessions"
    return path if agent is None else f"{path}/{registry_client.segment(agent)}/{registry_client.segment(session)}"


class Api:
    """The registry client with the person's token. When the registry no longer accepts the token (they last for minutes)
    the person signs in again once, at the same terminal, and the call is repeated."""

    def __init__(self, cfg: registry_client.Settings, sign_in, *, timeout: float, browser: bool):
        self.cfg, self._sign_in, self._timeout, self._browser = cfg, sign_in, timeout, browser
        self._client = None

    def _fresh(self) -> registry_client.Client:
        self._client = registry_client.Client(self.cfg, self._sign_in(timeout=self._timeout, browser=self._browser))
        return self._client

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        client = self._client or self._fresh()
        try:
            return client._call(method, path, body)
        except registry_client.RegistryError as exc:
            if exc.code != "not-signed-in":
                raise
        return self._fresh()._call(method, path, body)


def _api(sign_in, timeout: float, browser: bool) -> Api:
    return Api(registry_client.settings(), sign_in or registry_client.person_token, timeout=timeout, browser=browser)


def _session_url(cfg: registry_client.Settings, tenant: str) -> str:
    return cfg.url + sessions_path(tenant)


def _plan(d: layout.AgentDir, live_object: dict, *, release: str | None, grant_handle: str | None, max_boundaries: int, task) -> None:
    """Every refusal that needs neither the person nor the registry, before anything is created or sent."""
    if grant_handle is not None:
        raise DeliveryError(f"{d.agent} is owned by the registry: its session interface takes no grant handle, so --grant-handle is refused; an agent that acts for a person cannot be started here", "invalid-arguments")
    if max_boundaries != DEFAULT_BOUNDARIES:
        raise DeliveryError("--max-boundaries does not apply to an agent owned by the registry: the session interface does not take it", "invalid-arguments")
    current = ((live_object.get("metadata") or {}).get("annotations") or {}).get(CURRENT_ANNOTATION)
    if release and current and release != current:
        raise DeliveryError(f"{release} is not the current release of {d.agent} ({current}): only the evaluator may start a session of another release", "refused")
    if len(json.dumps(task, separators=(",", ":")).encode("utf-8")) > MAX_TASK_BYTES:
        raise DeliveryError("task exceeds 64 KiB", "validation-failed")


def submit(
    d: layout.AgentDir,
    live_object: dict,
    task,
    *,
    release: str | None = None,
    grant_handle: str | None = None,
    max_boundaries: int = DEFAULT_BOUNDARIES,
    wait: bool = True,
    wait_timeout: float = 900,
    poll_interval: float = 10,
    cancel_on_timeout: bool = False,
    out: Path | None = None,
    consent_timeout: float = 300,
    browser: bool = False,
    sign_in=None,
    sleep=time.sleep,
    clock=time.monotonic,
    started: dict | None = None,
) -> tuple[int, dict]:
    """Start one session through the session interface and, by default, follow it to its report. Same results as `run.submit`."""
    _plan(d, live_object, release=release, grant_handle=grant_handle, max_boundaries=max_boundaries, task=task)
    api = _api(sign_in, consent_timeout, browser)
    session = str(uuid.uuid4())
    out = out or run.default_out(d.agent, session)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chmod(out, 0o700)
    if started is not None:
        started.update(run.follow_up(out, session, receipt=False))
    body = {"agent": d.agent, "task": task, "release": release, "sessionId": session, "purpose": "task"}
    run._private(out / "request.json", json.dumps({"action": "start", "path": PATH_NAME, "tenant": d.tenant, **body}, indent=2, sort_keys=True) + "\n")
    if isinstance(started, run.Started):
        started.attempted = True
    try:
        answer = api.call("POST", sessions_path(d.tenant), body)
    except KeyboardInterrupt:
        return run._not_submitted(out, session, run.INTERRUPTED, "interrupted while the start call was in flight; whether a session was started is not known", status="SUBMIT_UNCONFIRMED", kind="not-confirmed")
    except registry_client.RegistryError as exc:
        if exc.code == "registry-unreachable":
            # No answer of the service's own: a session may have been started. Its id is in the run directory.
            return run._not_submitted(out, session, 2, f"{exc}; whether a session was started is not known", status="SUBMIT_UNCONFIRMED", kind="not-confirmed")
        # The service answered with a refusal of its own: nothing was started. Its message is shown as it was sent.
        return run._not_submitted(out, session, 2, str(exc), kind=exc.code)
    receipt = {
        "schemaVersion": RECEIPT_VERSION,
        "path": PATH_NAME,
        "sessionInterface": _session_url(api.cfg, d.tenant),
        "tenant": d.tenant,
        "agent": d.agent,
        "release": answer.get("release"),
        "releaseChoice": "explicit" if release else "default",
        "sessionId": answer.get("sessionId") or session,
        "workflowId": answer.get("workflowId"),
        "created": answer.get("created"),
        "submittedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dir": str(out),
    }
    run._private(out / "receipt.json", json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    found = run.follow_up(out, session, receipt=True)
    if started is not None:
        started.update(found)
    if not wait:
        return 0, {"receipt": receipt, "status": "SUBMITTED", "cleanup": "NOT_CONFIRMED"}
    try:
        return follow(receipt, api, out, wait_timeout=wait_timeout, poll_interval=poll_interval, cancel_on_timeout=cancel_on_timeout, sleep=sleep, clock=clock, unconfirmed=found)
    except KeyboardInterrupt:
        reason = f"interrupted while following the run; the session was not cancelled, and `{found['next']}` reads it"
        return run.INTERRUPTED, run.tag({"receipt": receipt, "status": "INTERRUPTED", "reason": reason, "cleanup": "NOT_CONFIRMED", **found}, "not-confirmed")


def _read(api: Api, receipt: dict) -> dict:
    return api.call("GET", sessions_path(receipt["tenant"], receipt["agent"], receipt["sessionId"]))


def _cancel(api: Api, receipt: dict, reason: str) -> dict:
    return api.call("POST", sessions_path(receipt["tenant"], receipt["agent"], receipt["sessionId"]) + "/cancel", {"reason": reason})


def follow(receipt: dict, api: Api, out: Path, *, wait_timeout: float, poll_interval: float, cancel_on_timeout: bool, sleep=time.sleep, clock=time.monotonic, unconfirmed: dict | None = None) -> tuple[int, dict]:
    """Read the session until it finishes or `wait_timeout` passes. `unconfirmed` has the meaning it has in `run.follow`."""
    deadline = clock() + wait_timeout
    while True:
        session = _read(api, receipt)
        if session.get("state") == "finished":
            return finish(receipt, session, out)
        remaining = deadline - clock()
        if remaining <= 0:
            envelope = {"receipt": receipt, "status": "RUNNING", "query": session.get("progress"), "cleanup": "NOT_CONFIRMED", "timedOut": True}
            if cancel_on_timeout:
                envelope["cancel"] = _cancel(api, receipt, "the wait of `just agent` ended and --cancel-on-timeout was given")
            kind = "timeout"
            if unconfirmed is not None:
                kind = "not-confirmed"
                asked = "; a cancel was requested" if cancel_on_timeout else "; it was not cancelled"
                envelope.update(unconfirmed, reason=f"the wait ended before the session did (status RUNNING); the session was started and its end is not confirmed{asked}")
            run._private(out / "status.json", json.dumps(envelope, indent=2, sort_keys=True) + "\n")
            return 124, run.tag(envelope, kind)
        sleep(min(poll_interval, remaining))


def finish(receipt: dict, session: dict, out: Path) -> tuple[int, dict]:
    """The document of a finished session, with its report written beside the receipt when the session completed."""
    ended = session.get("outcome")
    envelope = {
        "receipt": receipt,
        "status": STATUS.get(ended, "FAILED"),
        "query": session.get("progress"),
        "result": {"outcome": ended, "startedAt": session.get("startedAt"), "finishedAt": session.get("finishedAt")},
        "confirmed": ended != "not-confirmed",
        "cleanup": "NOT_CONFIRMED" if ended == "not-confirmed" else "CONFIRMED",
    }
    code = 1
    if ended == "completed":
        report = session.get("report")
        if isinstance(report, str):
            run._private(out / "report.md", report)
            envelope["report"] = str(out / "report.md")
            code = 0
        else:
            envelope["reason"] = "the session completed but its report could not be read" + (f": {session['reportProblem']}" if session.get("reportProblem") else "")
    run._private(out / "status.json", json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return code, run.tag(envelope, "failed" if code else None)


def is_session_receipt(path: Path) -> bool:
    """Whether the receipt names the session interface; a receipt that cannot be read is the old path's to report."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(doc, dict) and doc.get("path") == PATH_NAME


def resume(receipt_path: Path, action: str, *, wait_timeout: float = 900, poll_interval: float = 10, sign_in=None, sleep=time.sleep, clock=time.monotonic) -> tuple[int, dict]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schemaVersion") != RECEIPT_VERSION or not all(isinstance(receipt.get(k), str) for k in ("tenant", "agent", "sessionId")):
        raise run.RunError("unsupported receipt", "validation-failed")
    out = receipt_path.parent
    api = _api(sign_in, 300, False)
    for name in ("status.json", "report.md"):
        if (out / name).exists():
            (out / name).rename(out / f"{name}.{int(time.time())}")
    if action == "status":
        session = _read(api, receipt)
        if session.get("state") == "finished":
            return finish(receipt, session, out)
        return 0, {"receipt": receipt, "status": "RUNNING", "query": session.get("progress"), "cleanup": "NOT_CONFIRMED"}
    if action == "wait":
        return follow(receipt, api, out, wait_timeout=wait_timeout, poll_interval=poll_interval, cancel_on_timeout=False, sleep=sleep, clock=clock)
    if action == "cancel":
        answer = _cancel(api, receipt, "cancelled with `just agent cancel`")
        asked = answer.get("cancelRequested") is True
        doc = {"receipt": receipt, "cancel": answer, "cleanup": "NOT_CONFIRMED"}
        if not asked:
            doc["reason"] = "the session had already finished, so there was nothing to cancel"
        return (0 if asked else 1), run.tag(doc, "failed")
    raise run.RunError("unknown action", "internal")


# ---- release changes -----------------------------------------------------------------------


def _signed_in(root: Path, agent: str, sign_in=None) -> tuple[registry_client.Settings, registry_client.Client, layout.AgentDir, str]:
    d = layout.find_agent(root, agent)
    cfg = registry_client.settings()
    client = registry_client.Client(cfg, (sign_in or registry_client.person_token)())
    return cfg, client, d, registry_client.deployment_path(cfg, d.tenant, agent)


def _result(cfg, d: layout.AgentDir, answer: dict, nxt: str, **extra) -> dict:
    return {"agent": d.agent, "deployment": registry_client.deployment_id(cfg, d.tenant, d.agent), "path": "registry", "changed": answer.get("changed") is True, **extra, "next": nxt}


def revision_of(deployment: dict, agent: str, release: str) -> int:
    """The newest revision of the named release, from the registry's deployment document."""
    wanted = f"agent:{agent}:{release}"
    numbers = [r.get("number") for r in deployment.get("revisions") or [] if isinstance(r, dict) and r.get("releaseId") == wanted and isinstance(r.get("number"), int)]
    if not numbers:
        raise DeliveryError(f"the registry holds no revision of {agent} for release {release}", "not-found")
    return max(numbers)


def rollback(root: Path, agent: str, *, to: str | None = None, reason: str | None = None, sign_in=None) -> dict:
    cfg, client, d, path = _signed_in(root, agent, sign_in)
    number = revision_of(client.get(path), agent, to) if to else None
    answer = client.post(path + "/rollback", {"revision": number, "reason": reason or "rolled back with `just agent rollback`"})
    return _result(cfg, d, answer, "`just agent status` shows the release in use and whether the cluster has taken the change", revision=number)


def pin(root: Path, agent: str, *, release: str | None = None, sign_in=None) -> dict:
    cfg, client, d, path = _signed_in(root, agent, sign_in)
    deployment = client.get(path)
    if release:
        number = revision_of(deployment, agent, release)
    else:
        number = (deployment.get("deployment") or {}).get("currentRevision")
        if not isinstance(number, int):
            raise DeliveryError(f"{agent} has no current release to pin; name one with --release", "refused")
    answer = client.post(path + "/pin", {"revision": number})
    return _result(cfg, d, answer, f"newer releases are activated but not used until `just agent unpin {agent}`", revision=number)


def unpin(root: Path, agent: str, *, sign_in=None) -> dict:
    cfg, client, d, path = _signed_in(root, agent, sign_in)
    answer = client.post(path + "/pin", {"revision": None})
    return _result(cfg, d, answer, "`just agent status` shows the release in use")


def set_enabled(root: Path, agent: str, enabled: bool, *, reason: str | None = None, sign_in=None) -> dict:
    cfg, client, d, path = _signed_in(root, agent, sign_in)
    word = "enable" if enabled else "disable"
    answer = client.post(path + "/enabled", {"enabled": enabled, "reason": reason or f"{word}d with `just agent {word}`"})
    return _result(cfg, d, answer, "`just agent status` shows whether the cluster has taken the change", enabled=enabled)


def evaluate(root: Path, agent: str, *, reason: str | None = None, sign_in=None) -> dict:
    """Another evaluation of the newest revision after a refusal (delivery.md D14)."""
    cfg, client, d, path = _signed_in(root, agent, sign_in)
    numbers = [r.get("number") for r in client.get(path).get("revisions") or [] if isinstance(r, dict) and isinstance(r.get("number"), int)]
    if not numbers:
        raise DeliveryError("the registry holds no revision of this agent", "not-found")
    number = max(numbers)
    answer = client.post(f"{path}/revisions/{number}/evaluations", {"reason": reason or "asked for with `just agent evaluate`"})
    evaluation = answer.get("evaluation") if isinstance(answer.get("evaluation"), dict) else {}
    return {
        "agent": d.agent,
        "deployment": registry_client.deployment_id(cfg, d.tenant, d.agent),
        "path": "registry",
        "revision": number,
        "attempt": evaluation.get("attempt"),
        "state": evaluation.get("state"),
        "changed": True,
        "next": "`just agent status` shows the evaluation's verdict",
    }


# ---- revocation ----------------------------------------------------------------------------


def revocation_id(agent: str, release: str) -> str:
    """`<date>-<agent>-<suffix>` for a release named `<agent>-<date>-<suffix>`, which is the form delivery.md 8.1 shows."""
    rest = release[len(agent) + 1 :]
    match = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)\Z", rest)
    return f"{match.group(1)}-{agent}-{match.group(2)}" if match else release


def revoke(root: Path, agent: str, release: str, *, reason: str, summary: str, by: str, sessions: str | None = None, now: datetime | None = None) -> dict:
    """Write the reviewed revocation file and regenerate the committed feed. Commits, pushes and calls nothing."""
    import registry_feed

    if reason not in registry_feed.REVOCATION_REASONS:
        raise DeliveryError("--reason must be security or quality", "invalid-arguments")
    if sessions is not None and sessions not in registry_feed.REVOCATION_SESSIONS:
        raise DeliveryError("--sessions must be cancel or finish", "invalid-arguments")
    if not NAME_PART.match(agent) or not NAME_PART.match(release) or not release.startswith(agent + "-"):
        raise DeliveryError(f"{release!r} is not a release name of {agent!r}: it must start with the agent's name and a dash", "invalid-arguments")
    if not summary.strip() or "\n" in summary.strip() or not by.strip():
        raise DeliveryError("--summary is one sentence and --by names who decided; neither may be empty", "invalid-arguments")
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rid = revocation_id(agent, release)
    target = root / REVOCATIONS / f"{rid}.yaml"
    if target.exists():
        raise DeliveryError(f"{target.relative_to(root)} already exists: a revocation file is never edited after it is written", "conflict")
    effective = sessions or ("cancel" if reason == "security" else "finish")
    doc = {"schemaVersion": 1, "id": rid, "kind": "agent", "item": agent, "release": release, "reason": reason, "sessions": effective, "summary": summary.strip(), "revokedBy": by.strip(), "revokedAt": stamp}
    text = yaml.safe_dump(doc, sort_keys=False, width=1000, allow_unicode=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    feed_path = root / registry_feed.FEED
    before = feed_path.read_bytes() if feed_path.is_file() else None
    target.write_text(text, encoding="utf-8")
    try:
        feed_path.parent.mkdir(parents=True, exist_ok=True)
        feed_path.write_bytes(registry_feed.feed_bytes(registry_feed.render(root)))
    except (ValueError, OSError) as exc:
        target.unlink(missing_ok=True)
        if before is not None:
            feed_path.write_bytes(before)
        raise DeliveryError(f"the revocation file was not accepted by the feed renderer and was removed: {exc}", "validation-failed") from None
    return {
        "agent": agent,
        "release": release,
        "id": rid,
        "reason": reason,
        "sessions": effective,
        "files": [str(target.relative_to(root)), str(registry_feed.FEED)],
        "next": "open a pull request with these two files; the revocation takes effect when it merges and the registry applies the feed",
    }
