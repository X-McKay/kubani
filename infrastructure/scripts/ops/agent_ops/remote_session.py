"""Bounded session operations executed inside the tenant's Session Runner pod.

agent-ops ships this file and then one JSON request on the standard input of
`kubectl exec`; the command line is the same for every call, so nothing a
request carries is visible in a process listing. It uses the runner's own
Temporal connection (mTLS, namespace and payload codec come from the pod
environment) and reads only the content-addressed snapshot named by a completed
result.

A request may carry a person's consented token for deposit. The token goes to
the Agent Policy Service and nowhere else, and the grant handle the service
returns stays in this process: it is placed in the workflow input and never
printed. A grant deposited earlier for the session is found by session id with
the runner's own projected token. Nothing here prints credential material,
state files, tokens or handles: the report action returns `workspace/report.md`
and member names, and an error is one of the fixed messages in ERRORS.

Keep this file free of imports outside the standard library, temporalio and the
installed `runner` package; it is not imported by Kubani itself.
"""

import asyncio
import dataclasses
import hashlib
import io
import json
import os
import re
import ssl
import sys
import tarfile
import urllib.error
import urllib.request
import uuid
from datetime import timedelta

from temporalio.common import WorkflowIDReusePolicy
from temporalio.service import RPCError, RPCStatusCode

from runner.types import SessionInput
from runner.worker import connect
from runner.workflow import EXECUTION_TIMEOUT, SessionWorkflow

RPC = timedelta(seconds=5)
CLEAN = {"stop": "OK", "delete": "DELETED", "grant": "OK"}
NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?")
RELEASE = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,61}[a-z0-9])?")
SNAPSHOT_LIMIT = 64 * 1024 * 1024
REPORT_LIMIT = 16000
MEMBER_LIMIT = 256
APS_TIMEOUT = 5
APS_LIMIT = 1 << 20
# What SessionInput accepts as a grant handle; also what may be placed in a URL path.
HANDLE = re.compile(r"[A-Za-z0-9_-]{1,128}")
# A bearer value: no whitespace or control characters can reach the Authorization header.
BEARER = re.compile(r"[A-Za-z0-9._~+/=-]{1,16384}")
DEPOSIT_REFUSED = {
    "subject_not_user": "deposit refused: the token belongs to an agent, not a person",
    "scope": "deposit refused: the token lacks this agent's delegation scope",
    "may_act": "deposit refused: the token names no agent allowed to act for the person",
}
ERRORS = {
    *DEPOSIT_REFUSED.values(),
    "deposit refused: the policy service did not accept the token",
    "deposit refused: the policy service rejected the request",
    "deposit refused: this session already has a grant",
    "grant deposit failed",
    "policy service unreachable",
    "policy service session listing failed",
    "the session's grant names another tenant or agent",
    "invalid request",
    "session must be a canonical UUIDv4",
    "invalid run identity",
    "session identity already exists",
    "accepted start run identity missing",
    "exact session identity or queue differs",
    "run is not completed",
    "completion and cleanup are not confirmed",
    "invalid snapshot key",
    "snapshot bounds/hash mismatch",
    "snapshot member bound",
    "invalid report member",
    "report missing",
    "unknown action",
}


def fail(message):
    raise ValueError(message)


def canonical_uuid4(value, message):
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        fail(message)
    if str(parsed) != value or parsed.version != 4:
        fail(message)
    return value


def read_report(key):
    if not isinstance(key, str) or not re.fullmatch("[a-f0-9]{64}", key):
        fail("invalid snapshot key")
    path = os.path.join(os.environ.get("ARTIFACT_DIR", "/var/lib/agent-artifacts"), key[:2], key)
    with open(path, "rb") as source:
        raw = source.read(SNAPSHOT_LIMIT + 1)
    if len(raw) > SNAPSHOT_LIMIT or hashlib.sha256(raw).hexdigest() != key:
        fail("snapshot bounds/hash mismatch")
    report = None
    names = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for index, member in enumerate(archive):
            if index >= MEMBER_LIMIT:
                fail("snapshot member bound")
            if member.name.startswith("workspace/"):
                names.append(member.name)
            if member.name != "workspace/report.md":
                continue
            if report is not None or not member.isfile() or member.size > REPORT_LIMIT:
                fail("invalid report member")
            content = archive.extractfile(member).read(REPORT_LIMIT + 1)
            if len(content) != member.size:
                fail("invalid report member")
            try:
                report = content.decode("utf-8")
            except UnicodeDecodeError:
                fail("invalid report member")
    if report is None:
        fail("report missing")
    return report, sorted(names)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def aps(method, path, *, bearer=None, body=None):
    """One bounded call to the Agent Policy Service: (status, JSON object). The runner's projected token unless a bearer is given."""
    base = os.environ.get("APS_URL", "http://agent-policy-service.agent-platform.svc.cluster.local:9002").rstrip("/")
    try:
        if bearer is None:
            # Read on every call: the kubelet rotates the projected token.
            with open(os.environ.get("APS_TOKEN_PATH", "/var/run/secrets/agent-policy-service/token"), encoding="utf-8") as source:
                bearer = source.read().strip()
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(base + path, data=data, method=method)
        request.add_header("Authorization", "Bearer " + bearer)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        # No proxy from the environment and no redirect: the bearer goes to the configured service only.
        handlers = [urllib.request.ProxyHandler({}), NoRedirect()]
        if os.environ.get("APS_CA_FILE"):
            handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=os.environ["APS_CA_FILE"])))
        try:
            with urllib.request.build_opener(*handlers).open(request, timeout=APS_TIMEOUT) as response:
                status, raw = response.status, response.read(APS_LIMIT)
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read(APS_LIMIT)
            exc.close()
    except Exception:  # noqa: BLE001 - never the exception text: it can describe the request, which carries a token
        fail("policy service unreachable")
    try:
        doc = json.loads(raw) if raw.strip() else {}
    except ValueError:
        doc = {}
    return status, doc if isinstance(doc, dict) else {}


def deposit_grant(session, tenant, agent, deposit):
    """Deposit a person's consented token for this session. Returns the handle, which the caller keeps inside this process."""
    if not isinstance(deposit, dict) or set(deposit) != {"access_token", "refresh_token", "expires_at"}:
        fail("invalid request")
    access, refresh, expires = deposit["access_token"], deposit["refresh_token"], deposit["expires_at"]
    if not isinstance(access, str) or not BEARER.fullmatch(access) or not isinstance(expires, str):
        fail("invalid request")
    if refresh is not None and (not isinstance(refresh, str) or not 0 < len(refresh) <= 16384):
        fail("invalid request")
    body = {"session_id": session, "tenant": tenant, "agent": agent, "refresh_token": refresh, "expires_at": expires}
    status, doc = aps("POST", "/v1/grants", bearer=access, body=body)
    if status == 201:
        handle = doc.get("grant_handle")
        if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
            fail("grant deposit failed")
        return handle
    if status == 401:
        fail("deposit refused: the policy service did not accept the token")
    if status == 403:
        fail(DEPOSIT_REFUSED.get(doc.get("reason"), "grant deposit failed"))
    if status == 409:
        fail("deposit refused: this session already has a grant")
    if status == 400:
        fail("deposit refused: the policy service rejected the request")
    fail("grant deposit failed")


def deposited_grant(session, tenant, agent):
    """The handle of the grant the policy service holds for this session, or None when it holds none."""
    status, doc = aps("GET", "/v1/sessions")
    rows = doc.get("sessions")
    if status != 200 or not isinstance(rows, list):
        fail("policy service session listing failed")
    rows = [row for row in rows if isinstance(row, dict) and row.get("session_id") == session]
    if not rows or all(row.get("grant_handle") is None for row in rows):
        return None
    handle = rows[0].get("grant_handle")
    if len(rows) != 1 or rows[0].get("tenant") != tenant or rows[0].get("agent") != agent or not isinstance(handle, str) or not HANDLE.fullmatch(handle):
        fail("the session's grant names another tenant or agent")
    # The listing reports a handle while either the record or the token is held; the grant read answers only while both are.
    status, doc = aps("GET", "/v1/grants/" + handle)
    if status == 404:
        return None
    if status != 200:
        fail("policy service session listing failed")
    if doc.get("session_id") != session or doc.get("tenant") != tenant or doc.get("agent") != agent:
        fail("the session's grant names another tenant or agent")
    return handle


async def exists(client, workflow_id):
    try:
        await client.get_workflow_handle(workflow_id).describe(rpc_timeout=RPC)
    except RPCError as exc:
        if exc.status != RPCStatusCode.NOT_FOUND:
            raise
        return False
    return True


async def release_unstarted(client, workflow_id, session, handle):
    """Remove the grant of a session whose workflow does not exist. A workflow that did start removes its own grant at cleanup."""
    try:
        if not await exists(client, workflow_id):
            aps("DELETE", "/v1/grants/" + handle + "?session_id=" + session)
    except Exception:  # noqa: BLE001 - the cleanup reconciler removes the grant of a session that never started
        pass


async def main(req):
    if not isinstance(req, dict):
        fail("invalid request")
    tenant, agent, action = req.get("tenant"), req.get("agent"), req.get("action")
    if not all(isinstance(x, str) for x in (tenant, agent, action)):
        fail("invalid request")
    if not NAME.fullmatch(tenant) or not NAME.fullmatch(agent):
        fail("invalid request")
    session = canonical_uuid4(req.get("session_id"), "session must be a canonical UUIDv4")
    workflow_id = f"session:{tenant}:{agent}:{session}"
    queue = f"sessions-{tenant}"
    client = await connect(tenant)
    if client.namespace != f"agents-{tenant}":
        fail("invalid request")

    if action == "deposit":
        # The consent command's half of an awaited consent: the grant is left for the waiting `run` to find by session id.
        if set(req) != {"action", "tenant", "agent", "session_id", "deposit"}:
            fail("invalid request")
        if await exists(client, workflow_id):
            fail("session identity already exists")
        deposit_grant(session, tenant, agent, req["deposit"])
        return {"deposited": True, "session_id": session}

    if action == "submit":
        release = req.get("release")
        if not isinstance(release, str) or not RELEASE.fullmatch(release) or not release.startswith(agent + "-"):
            fail("invalid request")
        # At most one source of a grant: a handle given by the submitter, a token to deposit now, or the grant already deposited for this session.
        grant_handle, deposit, deposited = req.get("grant_handle"), req.get("deposit"), req.get("deposited_grant", False)
        if deposited not in (False, True) or sum((grant_handle is not None, deposit is not None, deposited)) > 1:
            fail("invalid request")
        if await exists(client, workflow_id):
            fail("session identity already exists")

        def session_input(handle):
            inp = SessionInput(
                tenant=tenant,
                agent=agent,
                release=release,
                session_id=session,
                grant_handle=handle,
                task=req.get("task"),
                max_boundaries=int(req.get("max_boundaries", 64)),
                worker_pool="legacy",
            )
            inp.validate()
            if inp.task_queue != queue:
                fail("invalid request")
            return inp

        inp = session_input(grant_handle)  # everything but a deposited grant is checked before a token is deposited
        held = None  # a grant deposited for this session that no workflow has taken over yet
        try:
            if deposit is not None:
                held = deposit_grant(session, tenant, agent, deposit)
            elif deposited:
                held = deposited_grant(session, tenant, agent)
                if held is None:
                    return {"granted": False, "session_id": session}
            if held is not None:
                inp = session_input(held)
            handle = await client.start_workflow(
                SessionWorkflow.run,
                inp,
                id=workflow_id,
                task_queue=queue,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                execution_timeout=EXECUTION_TIMEOUT,
                task_timeout=timedelta(seconds=10),
                rpc_timeout=RPC,
            )
        except BaseException:
            if held is not None:
                await release_unstarted(client, workflow_id, session, held)
            raise
        run_id = handle.first_execution_run_id
        if not isinstance(run_id, str) or str(uuid.UUID(run_id)) != run_id:
            fail("accepted start run identity missing")
        return {"workflow_id": workflow_id, "run_id": run_id, "namespace": client.namespace, "task_queue": queue}

    run_id = req.get("run_id")
    if not isinstance(run_id, str):
        fail("invalid run identity")
    try:
        if str(uuid.UUID(run_id)) != run_id:
            fail("invalid run identity")
    except ValueError:
        fail("invalid run identity")
    handle = client.get_workflow_handle_for(SessionWorkflow.run, workflow_id, run_id=run_id)
    desc = await handle.describe(rpc_timeout=RPC)
    if (
        desc.id != workflow_id
        or desc.run_id != run_id
        or desc.workflow_type != "SessionWorkflow"
        or desc.task_queue != queue
    ):
        fail("exact session identity or queue differs")
    if action == "cancel":
        await handle.cancel(rpc_timeout=RPC)
        return {"workflow_id": workflow_id, "run_id": run_id, "cancel_requested": True}
    if action not in ("status", "report"):
        fail("unknown action")
    status = await handle.query(SessionWorkflow.status, rpc_timeout=RPC)
    response = {"workflow_id": workflow_id, "run_id": run_id, "status": desc.status.name, "query": status}
    if desc.status.name != "COMPLETED":
        if action == "report":
            fail("run is not completed")
        return response
    result = await handle.result(follow_runs=False, rpc_timeout=RPC)
    response["result"] = dataclasses.asdict(result)
    confirmed = (
        result.outcome == "COMPLETED"
        and result.cleanup == CLEAN
        and status.get("state") == "CLEANED"
        and status.get("cleanup") == CLEAN
        and bool(result.snapshot)
    )
    response["confirmed"] = confirmed
    if action == "report":
        if not confirmed:
            fail("completion and cleanup are not confirmed")
        response["report"], response["workspace"] = read_report(result.snapshot)
    return response


if __name__ == "__main__":
    try:
        request = json.loads(sys.stdin.buffer.read())
        print(json.dumps(asyncio.run(asyncio.wait_for(main(request), 40)), sort_keys=True))
    except Exception as exc:  # noqa: BLE001 - the host side needs one bounded JSON line
        message = str(exc) if str(exc) in ERRORS else "operation failed; retain the receipt and inspect the exact session"
        print(json.dumps({"error": message, "error_type": type(exc).__name__}, sort_keys=True))
        raise SystemExit(2)
