"""Opt-in Kubani POC qualification. Faults touch only its dedicated worker/sessions."""

import argparse
import asyncio
import base64
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import grpc
from openshell import SandboxClient, TlsConfig
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode
from temporalio.worker import Replayer
from zetra._runtime.temporal import SessionWorkflow
from zetra.manifest import load_release, source_digest
from zetra.session import SessionHandle, load_execution

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "zetra-poc"
QUEUE = "zetra-kubernetes-poc-v1"


async def kube(*args, data=None):
    process = await asyncio.create_subprocess_exec(
        "kubectl",
        "--context",
        "default",
        *args,
        stdin=asyncio.subprocess.PIPE if data else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, error = await process.communicate(data.encode() if data else None)
    if process.returncode:
        raise RuntimeError(error.decode()[:1000])
    return out.decode()


async def worker_pods():
    raw = await kube("-n", NAMESPACE, "get", "pods", "-l", "app=investigator-worker", "-o", "json")
    return json.loads(raw)["items"]


async def scale(count):
    await kube("-n", NAMESPACE, "scale", "deployment/investigator-worker", f"--replicas={count}")
    if not count:
        async with asyncio.timeout(90):
            while await worker_pods():
                await asyncio.sleep(0.2)


async def wait_worker(client):
    from temporalio.api.taskqueue.v1 import TaskQueue
    from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest

    async with asyncio.timeout(120):
        while True:
            pods = [p for p in await worker_pods() if not p["metadata"].get("deletionTimestamp")]
            response = await client.workflow_service.describe_task_queue(
                DescribeTaskQueueRequest(
                    namespace=NAMESPACE,
                    task_queue=TaskQueue(name=QUEUE),
                    task_queue_type=1,
                )
            )
            for pod in pods:
                if any(pod["metadata"]["name"] in p.identity for p in response.pollers):
                    return pod["metadata"]["name"]
            await asyncio.sleep(0.3)


async def decoded_history(client, handle):
    history = await handle.fetch_history()
    scheduled, completed, effects, receipts, timings = {}, [], [], [], []
    started = {}
    for event in history.events:
        when = event.event_time.ToDatetime().timestamp()
        if event.HasField("activity_task_scheduled_event_attributes"):
            a = event.activity_task_scheduled_event_attributes
            command = (await client.data_converter.decode(a.input.payloads, [dict]))[0]
            scheduled[event.event_id] = {
                "name": a.activity_type.name,
                "command": command,
                "at": when,
            }
            if a.activity_type.name.startswith("execute_"):
                operation = command["operation"]
                assert a.retry_policy.maximum_attempts == 1, "effect retries enabled"
                effects.append(
                    {
                        **{k: operation[k] for k in ("index", "kind", "executor", "operation_id")},
                        "scheduled_event_id": event.event_id,
                    }
                )
        elif event.HasField("activity_task_started_event_attributes"):
            a = event.activity_task_started_event_attributes
            started[a.scheduled_event_id] = when
        elif event.HasField("activity_task_completed_event_attributes"):
            a = event.activity_task_completed_event_attributes
            row = scheduled[a.scheduled_event_id]
            value = (await client.data_converter.decode(a.result.payloads, [dict]))[0]
            completed.append({"name": row["name"], "value": value})
            if row["name"].startswith("execute_"):
                receipts.append(value)
            timings.append(
                {
                    "name": row["name"],
                    "queue_seconds": started[a.scheduled_event_id] - row["at"],
                    "seconds": when - started[a.scheduled_event_id],
                }
            )
    assert len({e["operation_id"] for e in effects}) == len(effects), "effect scheduled twice"
    return history, completed, effects, receipts, timings


def creation_bindings(completed):
    """Return created generations from either history format, excluding readiness echoes."""
    generations = {}
    for row in completed:
        if row["name"] not in ("provision_session", "rebind_session", "create_session"):
            continue
        binding = row["value"]
        generation = binding["generation"]
        assert generation >= 1, "invalid creation generation"
        if generation in generations:
            assert generations[generation] == binding, "creation generation changed binding"
        else:
            generations[generation] = binding
    assert generations, "no completed creation; native absence cannot be confirmed"
    assert list(generations) == list(range(1, len(generations) + 1)), "missing creation generation"
    bindings = list(generations.values())
    assert len({b["sandbox_id"] for b in bindings}) == len(bindings), (
        "sandbox reused across generations"
    )
    return bindings


async def confirm_absence(gateway, completed):
    """Require actual native and Kubernetes absence checks for every created generation."""
    bindings = creation_bindings(completed)
    for binding in bindings:
        try:
            gateway.get(binding["name"], workspace="default")
        except grpc.RpcError as error:
            assert error.code() == grpc.StatusCode.NOT_FOUND
        else:
            raise AssertionError("Native sandbox still exists after DELETED")
        resources = (
            ("sandbox", "default--" + binding["name"]),
            ("pod", "default--" + binding["name"]),
            ("pod", "os-supervisor-" + binding["sandbox_id"]),
            ("pvc", "workspace-default--" + binding["name"]),
        )
        for kind, name in resources:
            found = await kube(
                "-n",
                "zetra-poc-sandboxes",
                "get",
                kind,
                name,
                "--ignore-not-found",
                "-o",
                "name",
            )
            assert not found.strip(), "Native session resource remains: " + name


def check_cancellation(history, status):
    assert status == "CANCELED", "native Workflow did not cancel"
    cancel = next(
        (
            e.event_id
            for e in history.events
            if e.HasField("workflow_execution_cancel_requested_event_attributes")
        ),
        None,
    )
    assert cancel is not None, "no native cancellation request"
    assert all(
        e.activity_task_scheduled_event_attributes.activity_type.name == "close_session"
        for e in history.events
        if e.event_id > cancel and e.HasField("activity_task_scheduled_event_attributes")
    ), "business work continued after cancellation"


async def wait_inflight(handle, minimum):
    async with asyncio.timeout(120):
        while True:
            progress = await handle.query("progress")
            pending = progress.get("pending") or {}
            if (
                pending.get("kind") == "model"
                and (progress.get("position") or {}).get("cursor", 0) >= minimum
            ):
                return pending["operation_id"]
            if (await handle.describe()).close_time:
                raise AssertionError("fault boundary was missed; session already closed")
            await asyncio.sleep(0.1)


EXPORT = """import base64,json,pathlib,sys
p=pathlib.Path('/artifacts/results')/sys.argv[1]
if not (p/'result.json').is_file():raise SystemExit(4)
r=json.loads((p/'result.json').read_text())
summary={k:r.get(k) for k in ('status','cleanup','effect_status')}
summary['cursor']=(r.get('position') or {}).get('cursor')
summary['pending_operation']=(r.get('pending') or {}).get('operation_id')
summary['final_text']=(r.get('result') or {}).get('final_text')
files={str(f.relative_to(p/'workspace')):base64.b64encode(f.read_bytes()).decode() for f in (p/'workspace').rglob('*') if f.is_file()}
print(json.dumps({'result':summary,'files':files,'handle':json.loads((p/'handle.json').read_text())}))
"""


async def export(session):
    async with asyncio.timeout(150):
        while True:
            try:
                return json.loads(
                    await kube(
                        "-n",
                        NAMESPACE,
                        "exec",
                        "deployment/investigator-worker",
                        "--",
                        "/app/.venv/bin/python",
                        "-c",
                        EXPORT,
                        session,
                    )
                )
            except RuntimeError:
                await asyncio.sleep(0.5)


def check_report(files):
    report = files["report.md"].decode()
    narrative = report.split("\n\n## Evidence\n", 1)[0]
    assert len(narrative.split()) <= 150
    assert "investigator-demo-config" in narrative and "CreateContainerConfigError" in narrative
    links = re.findall(r"\]\((evidence/[^)]+)\)", report)
    assert links and all(link in files for link in links), "invalid report citation"
    tools = set()
    for name in links:
        content = files[name]
        assert name.endswith(hashlib.sha256(content).hexdigest() + ".json")
        evidence = json.loads(content)
        assert evidence["namespace"] == "zetra-poc-fixtures"
        tools.add(evidence["tool"])
    assert {"pods_list_in_namespace", "pods_get", "events_list"} <= tools
    return report


async def main(args):
    if not re.fullmatch(r"investigate-[a-z0-9-]{1,40}", args.session):
        raise ValueError("Use a short investigate- session ID")
    release = load_release(args.release)
    assert release.source_sha256 == source_digest(ROOT), "release does not match this source"
    deployment = json.loads(
        await kube("-n", NAMESPACE, "get", "deployment", "investigator-worker", "-o", "json")
    )
    assert deployment["spec"]["template"]["spec"]["containers"][0]["image"] == release.image
    client = await Client.connect(args.temporal_address, namespace=NAMESPACE)
    await wait_worker(client)
    try:
        await client.get_workflow_handle(args.session).describe()
    except RPCError as error:
        if error.status != RPCStatusCode.NOT_FOUND:
            raise
    else:
        raise ValueError(
            "Qualification requires a fresh session; existing results cannot be reused"
        )
    if args.scenario != "normal":
        async for execution in client.list_workflows(query="ExecutionStatus = 'Running'"):
            raise ValueError("Fault qualification requires an otherwise idle POC namespace")
    rendered = await asyncio.create_subprocess_exec(
        sys.executable,
        str(ROOT / "deploy/render-worker.py"),
        str(args.release),
        "--session",
        args.session,
        stdout=asyncio.subprocess.PIPE,
    )
    raw, _ = await rendered.communicate()
    assert rendered.returncode == 0
    job = next(item for item in json.loads(raw)["items"] if item["kind"] == "Job")
    begin = time.monotonic()
    await kube("apply", "-f", "-", data=json.dumps(job))
    handle = client.get_workflow_handle(args.session)
    async with asyncio.timeout(120):
        while True:
            try:
                description = await handle.describe()
                break
            except RPCError as error:
                if error.status != RPCStatusCode.NOT_FOUND:
                    raise
                await asyncio.sleep(0.3)
    handle = client.get_workflow_handle(args.session, run_id=description.run_id)
    accepted = await load_execution(
        client,
        SessionHandle(
            namespace=NAMESPACE,
            workflow_id=args.session,
            run_id=description.run_id,
            runtime_id="kubani-kubernetes-poc-v1",
        ),
    )
    assert (
        accepted["release_id"] == release.identity and accepted["release"] == release.model_dump()
    ), "accepted Workflow release differs from qualified image"
    directory = args.output / args.session
    directory.mkdir(parents=True, exist_ok=True)
    record = {
        "session": args.session,
        "run_id": description.run_id,
        "scenario": args.scenario,
        "release": release.identity,
        "image": release.image,
        "qualification": "FAILED",
    }
    gateway = SandboxClient(
        args.openshell_address,
        tls=TlsConfig(
            ca_path=args.tls_dir / "ca.crt",
            cert_path=args.tls_dir / "tls.crt",
            key_path=args.tls_dir / "tls.key",
        ),
    )
    parked = False
    before_receipts = []
    try:
        if args.scenario != "normal":
            record["injected_operation"] = await wait_inflight(handle, 6)
            if args.scenario in ("worker", "sandbox"):
                old = await wait_worker(client)
                parked = True
                await scale(0)
                assert not (await handle.describe()).close_time, (
                    "injection missed; session completed during graceful drain"
                )
                history, completed, _, before_receipts, _ = await decoded_history(client, handle)
                assert before_receipts, "no accepted checkpoint"
                record["parked_after"] = completed[-1]["name"]
                record["accepted_before_restart"] = len(before_receipts)
                if args.scenario == "sandbox":
                    assert completed[-1]["name"].startswith("execute_"), "missed safe boundary"
                    binding = creation_bindings(completed)[0]
                    ref = gateway.get(binding["name"], workspace="default")
                    assert ref.id == binding["sandbox_id"]
                    gateway.stop(ref.name, workspace="default")
                    gateway.delete(ref.name, workspace="default", allow_missing=True)
                    gateway.wait_deleted(ref.name, workspace="default", expected_sandbox_id=ref.id)
                    record["removed_sandbox_id"] = ref.id
                await scale(1)
                parked = False
                new = await wait_worker(client)
                assert old != new
                record["worker_replaced"] = True
            elif args.scenario == "cancel":
                await handle.cancel()
        async with asyncio.timeout(300):
            while not (await handle.describe()).close_time:
                await asyncio.sleep(0.5)
            terminal = await handle.describe()
            if terminal.status.name == "COMPLETED":
                native = await handle.result(follow_runs=False)
                record.update({k: native.get(k) for k in ("status", "cleanup")})
                record["cursor"] = (native.get("position") or {}).get("cursor")
                record["pending_operation"] = (native.get("pending") or {}).get("operation_id")
            (directory / "history.json").write_text((await handle.fetch_history()).to_json())
            if record.get("status") == "SUCCEEDED":
                async with asyncio.timeout(30):
                    while True:
                        status = json.loads(
                            await kube(
                                "-n", NAMESPACE, "get", "job", job["metadata"]["name"], "-o", "json"
                            )
                        )["status"]
                        assert not status.get("failed"), "submission Job failed"
                        if status.get("succeeded"):
                            break
                        await asyncio.sleep(0.2)
            exported = await export(args.session)
        assert (
            exported["handle"]["run_id"] == description.run_id
            and exported["handle"]["workflow_id"] == args.session
        ), "export receipt does not match accepted execution"
        record.update(exported["result"])
        assert record["cleanup"] == "DELETED", record
        history, completed, effects, receipts, timings = await decoded_history(client, handle)
        (directory / "history.json").write_text(history.to_json())
        record["accepted_release_and_export_handle_verified"] = True
        record["successful_client_export"] = args.scenario in ("normal", "worker", "sandbox")
        assert receipts[: len(before_receipts)] == before_receipts, "accepted prefix changed"
        if args.scenario in ("normal", "worker", "sandbox"):
            assert record["status"] == "SUCCEEDED", record
            files = {name: base64.b64decode(value) for name, value in exported["files"].items()}
            record["report"] = check_report(files)
            record["files"] = sorted(files)
            for name, content in files.items():
                target = directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            if args.scenario == "sandbox":
                bindings = creation_bindings(completed)[1:]
                assert bindings and all(
                    b["sandbox_id"] != record["removed_sandbox_id"] for b in bindings
                )
                record["replacement_sandbox_ids"] = [b["sandbox_id"] for b in bindings]
        elif args.scenario == "cancel":
            check_cancellation(history, (await handle.describe()).status.name)
            assert record["status"] == "CANCELED"
        await confirm_absence(gateway, completed)
        record["native_and_kubernetes_absence_confirmed"] = True
        await Replayer(workflows=[SessionWorkflow]).replay_workflow(history)
        history_json = history.to_json()
        assert not re.search(
            r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]+", history_json
        )
        assert "client_secret" not in history_json and "openshell:resolve:env:" not in history_json
        (directory / "history.json").write_text(history_json)
        record["history_replay"] = "PASSED"
        record["single_attempt_effects"] = True
        record["effects"] = effects
        record["activities"] = timings
        record["client_wall_seconds"] = time.monotonic() - begin
        record["workflow_seconds"] = (
            (await handle.describe()).close_time - description.start_time
        ).total_seconds()
        record["qualification"] = "PASSED"
    finally:
        try:
            if parked:
                await scale(1)
        finally:
            try:
                gateway.close()
            finally:
                (directory / "summary.json").write_text(json.dumps(record, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: record[k]
                for k in (
                    "session",
                    "scenario",
                    "status",
                    "cleanup",
                    "qualification",
                    "workflow_seconds",
                )
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument(
        "--scenario",
        choices=("normal", "worker", "sandbox", "cancel"),
        default="normal",
    )
    parser.add_argument("--release", type=Path, default=ROOT / ".tools/release.json")
    parser.add_argument("--temporal-address", required=True)
    parser.add_argument("--openshell-address", required=True)
    parser.add_argument("--tls-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / ".tools/qualification")
    asyncio.run(main(parser.parse_args()))
