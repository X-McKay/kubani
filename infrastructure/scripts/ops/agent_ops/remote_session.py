"""Bounded session operations executed inside the tenant's Session Runner pod.

agent-ops ships this file over `kubectl exec ... python -` with one JSON request
argument. It uses the runner's own Temporal connection (mTLS, namespace and
payload codec come from the pod environment) and reads only the content-addressed
snapshot named by a completed result. It never prints credential material, state
files or tokens: the report action returns `workspace/report.md` and member names.

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
import sys
import tarfile
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
ERRORS = {
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

    if action == "submit":
        release = req.get("release")
        if not isinstance(release, str) or not RELEASE.fullmatch(release) or not release.startswith(agent + "-"):
            fail("invalid request")
        try:
            await client.get_workflow_handle(workflow_id).describe(rpc_timeout=RPC)
        except RPCError as exc:
            if exc.status != RPCStatusCode.NOT_FOUND:
                raise
        else:
            fail("session identity already exists")
        inp = SessionInput(
            tenant=tenant,
            agent=agent,
            release=release,
            session_id=session,
            grant_handle=req.get("grant_handle"),
            task=req.get("task"),
            max_boundaries=int(req.get("max_boundaries", 64)),
            worker_pool="legacy",
        )
        inp.validate()
        if inp.task_queue != queue:
            fail("invalid request")
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
        request = json.loads(sys.argv[1])
        print(json.dumps(asyncio.run(asyncio.wait_for(main(request), 40)), sort_keys=True))
    except Exception as exc:  # noqa: BLE001 - the host side needs one bounded JSON line
        message = str(exc) if str(exc) in ERRORS else "operation failed; retain the receipt and inspect the exact session"
        print(json.dumps({"error": message, "error_type": type(exc).__name__}, sort_keys=True))
        raise SystemExit(2)
