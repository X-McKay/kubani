"""Opt-in live worker-loss test. The completion gate exists only in test children."""

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from datetime import UTC
from pathlib import Path
from unittest.mock import patch

import grpc
from openshell import SandboxClient, TlsConfig
from temporalio import activity
from temporalio.api.enums.v1 import TimeoutType
from temporalio.client import Client
from temporalio.worker import Replayer
from zetra._runtime.activities import Activities
from zetra._runtime.artifacts import FileStore, Tape
from zetra._runtime.temporal import SessionWorkflow
from zetra.client import SessionClient
from zetra.manifest import load_release
from zetra.session import SessionHandle, load_execution
from zetra.worker import OpenShellSession, create_worker

TEMPORAL_ADDRESS = "temporal-frontend.temporal.svc.cluster.local:7233"
MESSAGE = "Investigate investigator-demo-broken in zetra-poc-fixtures. Explain the startup problem using MCP evidence, compare the healthy pod, and write report.md."


async def connect_temporal():
    """Retry only test bootstrap connections, before admitting any work."""
    async with asyncio.timeout(30):
        while True:
            try:
                async with asyncio.timeout(5):
                    return await Client.connect(
                        os.environ.get("TEMPORAL_ADDRESS", TEMPORAL_ADDRESS), namespace="zetra-poc"
                    )
            except (RuntimeError, OSError):
                await asyncio.sleep(0.5)


async def discover_submission(temporal, release, session):
    """Recover an accepted native run without submitting or executing work."""
    async with asyncio.timeout(30):
        description = await temporal.get_workflow_handle(session).describe()
        handle = SessionHandle(
            namespace=temporal.namespace,
            workflow_id=session,
            run_id=description.run_id,
            runtime_id=session,
        )
        accepted = await load_execution(temporal, handle)
        if (
            accepted["release_id"] != release.identity
            or accepted["release"] != release.model_dump()
            or accepted["runtime_id"] != session
            or accepted["task_queue"] != session
            or accepted["message"] != MESSAGE
        ):
            raise ValueError("discovered execution differs from the intended test")
        return handle


def check_loss(history, effects, receipts, gate, result, kill):
    assert kill["returncode"] == -signal.SIGKILL
    assert result["status"] == "OUTCOME_UNKNOWN" and result["cleanup"] == "DELETED"
    assert result["position"] == gate["accepted"]
    assert result["pending"]["operation_id"] == gate["operation_id"]
    cursor = gate["accepted"]["cursor"]
    assert len(receipts) == cursor and len(effects) == cursor + 1
    assert gate["candidate"]["position"]["cursor"] == cursor + 1
    matching = [e for e in effects if e["operation_id"] == gate["operation_id"]]
    assert len(matching) == 1
    scheduled = matching[0]["scheduled_event_id"]
    started = [
        e
        for e in history.events
        if e.HasField("activity_task_started_event_attributes")
        and e.activity_task_started_event_attributes.scheduled_event_id == scheduled
    ]
    assert (
        len(started) == 1
        and started[0].activity_task_started_event_attributes.identity == gate["identity"]
    )
    age = kill["at_unix"] - started[0].event_time.ToDatetime(tzinfo=UTC).timestamp()
    assert 0 <= age < 40, "kill missed the native Activity deadline"
    terminals = [
        e
        for e in history.events
        if any(
            e.HasField("activity_task_" + kind + "_event_attributes")
            and getattr(e, "activity_task_" + kind + "_event_attributes").scheduled_event_id
            == scheduled
            for kind in ("completed", "failed", "canceled", "timed_out")
        )
    ]
    assert len(terminals) == 1
    terminal = terminals[0]
    assert terminal.HasField("activity_task_timed_out_event_attributes")
    assert (
        terminal.activity_task_timed_out_event_attributes.failure.timeout_failure_info.timeout_type
        in (TimeoutType.TIMEOUT_TYPE_HEARTBEAT, TimeoutType.TIMEOUT_TYPE_START_TO_CLOSE)
    )
    assert terminal.event_time.ToDatetime(tzinfo=UTC).timestamp() > kill["at_unix"]
    assert all(
        e.activity_task_scheduled_event_attributes.activity_type.name == "close_session"
        for e in history.events
        if e.event_id > terminal.event_id and e.HasField("activity_task_scheduled_event_attributes")
    )


def gateway():
    tls = Path(os.environ.get("OPENSHELL_TLS_DIR", "/etc/openshell"))
    return SandboxClient(
        os.environ.get("OPENSHELL_ADDRESS", "zetra-poc-openshell.zetra-poc.svc.cluster.local:8080"),
        tls=TlsConfig(ca_path=tls / "ca.crt", cert_path=tls / "tls.crt", key_path=tls / "tls.key"),
    )


def emit(kind, **values):
    print(json.dumps({"type": kind, **values}), flush=True)


async def child(args):
    temporal = await connect_temporal()
    release = load_release("/etc/zetra/release.json")
    store = FileStore("/artifacts/objects")
    identity = "loss-" + str(os.getpid())

    class ObservedSession(OpenShellSession):
        async def call(self, action, command):
            if action == "execute":
                emit("dispatch", operation_id=command["operation"]["operation_id"])
            value = await super().call(action, command)
            if args.gate and action == "execute" and command["operation"]["kind"] == args.kind:
                info = activity.info()
                emit(
                    "gate",
                    operation_id=command["operation"]["operation_id"],
                    accepted=command["position"],
                    candidate=value,
                    binding=command["binding"],
                    identity=identity,
                    activity_deadline=info.started_time.timestamp()
                    + info.start_to_close_timeout.total_seconds(),
                )
                await asyncio.Future()  # Existing Activity heartbeat task remains live.
            return value

    client = gateway()
    try:
        with patch("zetra.worker.OpenShellSession", ObservedSession):
            worker = create_worker(
                temporal,
                task_queue=args.session,
                runtime_id=args.session,
                sandbox_client=client,
                artifacts=store,
                key=Path("/etc/zetra-key/key").read_bytes(),
                approved_releases={release.identity},
                providers=("kubani-k8s-read",),
                identity=identity,
            )
            async with worker:
                emit("ready", identity=identity)
                await asyncio.Future()
    finally:
        client.close()


async def supervisor(args):
    from qualify_kubani import decoded_history

    root = Path("/artifacts/qualification") / args.session
    root.mkdir(parents=True, exist_ok=True)
    record = {"session": args.session, "kind": args.kind, "qualification": "FAILED"}
    temporal = await connect_temporal()
    release = load_release("/etc/zetra/release.json")
    record.update(release=release.identity, image=release.image)
    store = FileStore("/artifacts/objects")
    client = SessionClient(
        temporal, task_queue=args.session, runtime_id=args.session, artifacts=store
    )
    processes = []
    collectors = []
    dispatches = []
    handle = None
    submission_attempted = False
    replacement = None

    def save():
        record["dispatches"] = dispatches
        (root / "summary.json").write_text(json.dumps(record, indent=2) + "\n")

    async def start(gated):
        with (root / ("gated.log" if gated else "replacement.log")).open("w") as log:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                __file__,
                "--role",
                "worker",
                "--session",
                args.session,
                "--kind",
                args.kind,
                *(["--gate"] if gated else []),
                stdout=asyncio.subprocess.PIPE,
                stderr=log,
            )
        processes.append(process)
        queue = asyncio.Queue()

        async def collect():
            while line := await process.stdout.readline():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "dispatch":
                    dispatches.append({"pid": process.pid, "operation_id": event["operation_id"]})
                await queue.put(event)
            await queue.put({"type": "eof"})

        collectors.append(asyncio.create_task(collect()))
        await next_event(queue, "ready")
        return process, queue

    async def next_event(queue, kind):
        async with asyncio.timeout(90):
            while True:
                event = await queue.get()
                if event["type"] == kind:
                    return event
                if event["type"] == "eof":
                    raise RuntimeError("worker exited before test boundary")

    try:
        first, events = await start(True)
        submission_attempted = True
        handle = await client.submit(
            release,
            session=args.session,
            message=MESSAGE,
        )
        record.update(handle=handle.model_dump(), run_id=handle.run_id)
        save()
        gate = await next_event(events, "gate")
        record["gate"] = gate
        save()
        assert gate["identity"] == "loss-" + str(first.pid)
        assert gate["activity_deadline"] - time.time() > 5
        # Verify the real uploaded candidate without accepting it into history.
        tape = Tape(store, manifest=release.identity)
        entries = tape.load(gate["candidate"]["position"])
        assert entries[-1]["operation"]["operation_id"] == gate["operation_id"]
        Activities(None, None, tape).validate_receipt(
            {"position": gate["accepted"], "operation": entries[-1]["operation"]}, gate["candidate"]
        )
        snapshot = await temporal.get_workflow_handle(
            handle.workflow_id, run_id=handle.run_id
        ).fetch_history()
        assert not any(
            e.HasField("workflow_execution_completed_event_attributes") for e in snapshot.events
        )
        assert gate["activity_deadline"] - time.time() > 5
        killed_at = time.time()
        first.kill()
        await first.wait()
        kill = {"returncode": first.returncode, "at_unix": killed_at}
        record["kill"] = kill
        save()
        assert first.returncode == -signal.SIGKILL
        replacement, _ = await start(False)
        async with asyncio.timeout(120):
            result = await client.wait(handle)
        record["result"] = result
        save()
        execution = temporal.get_workflow_handle(handle.workflow_id, run_id=handle.run_id)
        history, _, effects, receipts, timings = await decoded_history(temporal, execution)
        (root / "history.json").write_text(history.to_json())
        check_loss(history, effects, receipts, gate, result, kill)
        await asyncio.sleep(0.05)
        assert [d["operation_id"] for d in dispatches] == [e["operation_id"] for e in effects]
        assert not any(d["pid"] == replacement.pid for d in dispatches)
        await Replayer(workflows=[SessionWorkflow]).replay_workflow(history)
        native = gateway()
        try:
            try:
                native.get(gate["binding"]["name"], workspace="default")
            except grpc.RpcError as error:
                assert error.code() == grpc.StatusCode.NOT_FOUND
            else:
                raise AssertionError("sandbox remains")
        finally:
            native.close()
        record.update(
            qualification="PASSED",
            release=release.identity,
            image=release.image,
            run_id=handle.run_id,
            result={k: result[k] for k in ("status", "cleanup", "position")},
            gate=gate,
            kill=kill,
            dispatches=dispatches,
            activities=timings,
            history_replay="PASSED",
            candidate_verified=True,
            no_redispatch=True,
        )
        (root / "history.json").write_text(history.to_json())
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        try:
            if submission_attempted and record["qualification"] != "PASSED":
                record["failure_cleanup"] = "NOT_CONFIRMED"
                if handle is None:
                    try:
                        handle = await discover_submission(temporal, release, args.session)
                        record.update(
                            handle=handle.model_dump(),
                            run_id=handle.run_id,
                            submission_ack_recovered=True,
                        )
                    except Exception as exc:  # noqa: BLE001 -- unknown admission needs evidence
                        record["submission_discovery_error"] = type(exc).__name__
            if handle and record["qualification"] != "PASSED":
                try:
                    if replacement is None or replacement.returncode is not None:
                        replacement, _ = await start(False)
                    execution = temporal.get_workflow_handle(
                        handle.workflow_id, run_id=handle.run_id
                    )
                    if not (await execution.describe()).close_time:
                        await execution.cancel()
                    # Preserve the SDK's ten-minute cleanup retry window.
                    async with asyncio.timeout(660):
                        cleaned = await client.wait(handle)
                        if cleaned.get("cleanup") != "DELETED":
                            cleaned = await client.reconcile(handle)
                        record["failure_cleanup"] = cleaned.get("cleanup")
                        assert record["failure_cleanup"] == "DELETED", cleaned
                except Exception as exc:  # noqa: BLE001 -- retain the original test failure
                    record["failure_cleanup_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if handle:
                try:
                    history = await temporal.get_workflow_handle(
                        handle.workflow_id, run_id=handle.run_id
                    ).fetch_history()
                    (root / "history.json").write_text(history.to_json())
                except Exception as exc:  # noqa: BLE001 -- history export must not skip cleanup
                    record["history_export_error"] = f"{type(exc).__name__}: {exc}"
            for process in processes:
                if process.returncode is None:
                    process.terminate()
            for process in processes:
                try:
                    await asyncio.wait_for(process.wait(), 10)
                except TimeoutError:
                    process.kill()
                    await process.wait()
            await asyncio.gather(*collectors)
            save()
    emit("result", qualification=record["qualification"], session=args.session)


async def launch(args):
    import copy
    import re

    from qualify_kubani import kube

    assert re.fullmatch(r"investigate-[a-z0-9-]{1,40}", args.session)
    release = load_release(args.release)
    template = json.loads(
        await kube("-n", "zetra-poc", "get", "deployment", "investigator-worker", "-o", "json")
    )["spec"]["template"]
    assert template["spec"]["containers"][0]["image"] == release.image
    template = copy.deepcopy(template)
    template["metadata"] = {
        "labels": {"app": "investigator-qualification", "qualification": "inflight-loss"}
    }
    pod = template["spec"]
    pod["restartPolicy"] = "Never"
    container = pod["containers"][0]
    container["name"] = "qualification"
    env = container.setdefault("env", [])
    if not any(item["name"] == "TEMPORAL_ADDRESS" for item in env):
        env.append({"name": "TEMPORAL_ADDRESS", "value": TEMPORAL_ADDRESS})
    container["command"] = [
        "/app/.venv/bin/python",
        "/qualification/inflight_loss.py",
        "--role",
        "supervisor",
        "--session",
        args.session,
        "--kind",
        args.kind,
    ]
    pod["volumes"].append({"name": "qualification", "configMap": {"name": args.session}})
    next(v for v in pod["volumes"] if v["name"] == "release")["configMap"] = {
        "name": args.session,
        "items": [{"key": "release.json", "path": "release.json"}],
    }
    container["volumeMounts"].append(
        {"name": "qualification", "mountPath": "/qualification", "readOnly": True}
    )
    directory = Path(__file__).parent
    config = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": args.session, "namespace": "zetra-poc"},
        "immutable": True,
        "data": {
            "release.json": release.model_dump_json(),
            **{
                p.name: p.read_text()
                for p in [directory / "inflight_loss.py", directory / "qualify_kubani.py"]
            },
        },
    }
    job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": args.session, "namespace": "zetra-poc"},
        "spec": {
            "backoffLimit": 0,
            # Startup, injection, replacement and the SDK cleanup retry window.
            "activeDeadlineSeconds": 1200,
            "ttlSecondsAfterFinished": 3600,
            "template": template,
        },
    }
    await kube(
        "create",
        "-f",
        "-",
        data=json.dumps({"apiVersion": "v1", "kind": "List", "items": [config, job]}),
    )
    target = args.output / args.session
    target.mkdir(parents=True, exist_ok=True)
    record = {"session": args.session, "kind": args.kind, "qualification": "FAILED"}
    try:
        async with asyncio.timeout(1260):
            while True:
                status = json.loads(
                    await kube("-n", "zetra-poc", "get", "job", args.session, "-o", "json")
                )["status"]
                if status.get("succeeded") or status.get("failed"):
                    break
                await asyncio.sleep(1)
        raw = await kube(
            "-n",
            "zetra-poc",
            "exec",
            "deployment/investigator-worker",
            "--",
            "/app/.venv/bin/python",
            "-c",
            "import pathlib,sys;print((pathlib.Path('/artifacts/qualification')/sys.argv[1]/'summary.json').read_text())",
            args.session,
        )
        record.update(json.loads(raw))
        record["supervisor_qualification"] = record["qualification"]
        record["qualification"] = "FAILED"
        (target / "summary.json").write_text(json.dumps(record, indent=2) + "\n")
        assert status.get("succeeded") and record["supervisor_qualification"] == "PASSED", (
            "supervisor did not qualify or Job failed"
        )
        assert record["release"] == release.identity and record["image"] == release.image
        assert record["session"] == args.session and record["kind"] == args.kind
        binding = record["gate"]["binding"]
        for kind, name in [
            ("sandbox", "default--" + binding["name"]),
            ("pod", "default--" + binding["name"]),
            ("pod", "os-supervisor-" + binding["sandbox_id"]),
            ("pvc", "workspace-default--" + binding["name"]),
        ]:
            assert not (
                await kube(
                    "-n",
                    "zetra-poc-sandboxes",
                    "get",
                    kind,
                    name,
                    "--ignore-not-found",
                    "-o",
                    "name",
                )
            ).strip()
        record["native_and_kubernetes_absence_confirmed"] = True
        record["qualification"] = "PASSED"
        (target / "summary.json").write_text(json.dumps(record, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "session": args.session,
                    "kind": args.kind,
                    "qualification": "PASSED",
                    "cleanup": "DELETED",
                }
            )
        )
    except Exception as exc:
        record["qualification"] = "FAILED"
        record.setdefault("error", f"{type(exc).__name__}: {exc}")
        record["host_error_type"] = type(exc).__name__
        raise
    finally:
        (target / "summary.json").write_text(json.dumps(record, indent=2) + "\n")
        # Job must finish before removing the script consumed by its processes.
        if "status" in locals() and (status.get("succeeded") or status.get("failed")):
            await kube("-n", "zetra-poc", "delete", "configmap", args.session, "--ignore-not-found")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=["launch", "supervisor", "worker"], default="launch")
    parser.add_argument("--session", required=True)
    parser.add_argument("--kind", choices=["model", "tool"], default="model")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--release", type=Path, default=Path(".tools/release.json"))
    parser.add_argument("--output", type=Path, default=Path(".tools/worker-loss"))
    args = parser.parse_args()
    asyncio.run({"launch": launch, "supervisor": supervisor, "worker": child}[args.role](args))
