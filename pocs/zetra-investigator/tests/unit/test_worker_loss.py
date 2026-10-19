"""A lost-worker qualification cannot credit a normal provider error or accepted result."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.protobuf.timestamp_pb2 import Timestamp
from temporalio.api.enums.v1 import TimeoutType
from temporalio.api.failure.v1 import Failure, TimeoutFailureInfo
from temporalio.api.history.v1 import (
    ActivityTaskStartedEventAttributes,
    ActivityTaskTimedOutEventAttributes,
    History,
    HistoryEvent,
)


def loss_module():
    spec = importlib.util.spec_from_file_location(
        "inflight_loss", Path(__file__).resolve().parents[2] / "evals/inflight_loss.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "discovery_fails", [None, "unavailable", "untrusted", "release-drift", "queue-drift"]
)
def test_lost_submission_ack_is_discovered_for_cleanup_only(monkeypatch, tmp_path, discovery_fails):
    module = loss_module()
    monkeypatch.setitem(sys.modules, "qualify_kubani", SimpleNamespace(decoded_history=None))
    release = SimpleNamespace(
        identity="release", image="image", model_dump=lambda: {"image": "image"}
    )
    execution = SimpleNamespace(
        describe=AsyncMock(return_value=SimpleNamespace(run_id="exact", close_time=None)),
        cancel=AsyncMock(),
        fetch_history=AsyncMock(return_value=SimpleNamespace(to_json=lambda: "{}")),
    )
    temporal = SimpleNamespace(
        namespace="zetra-poc", get_workflow_handle=lambda *a, **kw: execution
    )
    submit = AsyncMock(side_effect=TimeoutError("submission acknowledgement lost"))
    wait = AsyncMock(return_value={"cleanup": "DELETED"})
    client = SimpleNamespace(submit=submit, wait=wait)
    monkeypatch.setattr(module.Client, "connect", AsyncMock(return_value=temporal))
    monkeypatch.setattr(module, "SessionClient", lambda *a, **kw: client)
    monkeypatch.setattr(module, "FileStore", lambda *a: object())
    monkeypatch.setattr(module, "load_release", lambda *a: release)
    monkeypatch.setattr(
        module, "Path", lambda p: tmp_path if p == "/artifacts/qualification" else Path(p)
    )
    accepted = {
        "release_id": "release",
        "release": {"image": "image"},
        "runtime_id": "investigate-lost",
        "task_queue": "investigate-lost",
        "message": "Investigate investigator-demo-broken in zetra-poc-fixtures. Explain the startup problem using MCP evidence, compare the healthy pod, and write report.md.",
    }
    validate = AsyncMock(return_value=accepted)
    if discovery_fails == "unavailable":
        execution.describe.side_effect = RuntimeError("discovery unavailable")
    elif discovery_fails == "untrusted":
        validate.side_effect = ValueError("untrusted native start")
    elif discovery_fails == "release-drift":
        accepted["release_id"] = "another-release"
    elif discovery_fails == "queue-drift":
        accepted["task_queue"] = "another-queue"
    monkeypatch.setattr(module, "load_execution", validate, raising=False)

    class Process:
        pid = 1
        returncode = None

        def __init__(self, *args, **kwargs):
            self.stdout = asyncio.StreamReader()
            self.stdout.feed_data(b'{"type":"ready"}\n')
            self.stdout.feed_eof()

        def terminate(self):
            self.returncode = 0

        async def wait(self):
            return self.returncode

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", AsyncMock(side_effect=Process))
    args = SimpleNamespace(session="investigate-lost", kind="model")
    with pytest.raises(TimeoutError, match="acknowledgement"):
        asyncio.run(module.supervisor(args))
    record = json.loads((tmp_path / args.session / "summary.json").read_text())
    assert record["qualification"] == "FAILED"
    assert submit.await_count == 1, "cleanup must never submit another execution"
    if discovery_fails:
        assert record["failure_cleanup"] == "NOT_CONFIRMED"
        assert not wait.await_count and not execution.cancel.await_count
    else:
        assert record["failure_cleanup"] == "DELETED"
        assert record["handle"]["run_id"] == "exact"
        assert execution.cancel.await_count == wait.await_count == 1
        assert validate.call_args.args[1].run_id == "exact"


def test_bootstrap_retries_connection_before_any_submission(monkeypatch):
    module = loss_module()
    connected = object()
    connect = AsyncMock(side_effect=[RuntimeError("connection refused"), connected])
    monkeypatch.setattr(module.Client, "connect", connect)
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    assert asyncio.run(module.connect_temporal()) is connected
    assert connect.await_count == 2


def test_bootstrap_does_not_retry_invalid_configuration(monkeypatch):
    module = loss_module()
    connect = AsyncMock(side_effect=ValueError("invalid configuration"))
    monkeypatch.setattr(module.Client, "connect", connect)
    with pytest.raises(ValueError):
        asyncio.run(module.connect_temporal())
    assert connect.await_count == 1


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "inflight_loss", Path(__file__).resolve().parents[2] / "evals/inflight_loss.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    release = SimpleNamespace(
        identity="qualified-release",
        image="registry/image@sha256:123",
        model_dump_json=lambda: '{"identity":"qualified-release"}',
    )
    monkeypatch.setattr(module, "load_release", lambda _: release)
    state = {
        "remaining": "",
        "record": {
            "session": "investigate-loss",
            "kind": "model",
            "qualification": "PASSED",
            "release": release.identity,
            "image": release.image,
            "gate": {"binding": {"name": "sandbox", "sandbox_id": "instance"}},
        },
    }

    async def kube(*args, data=None):
        if args[:3] == ("-n", "zetra-poc", "get") and args[3] == "deployment":
            return json.dumps(
                {
                    "spec": {
                        "template": {
                            "metadata": {},
                            "spec": {
                                "containers": [
                                    {
                                        "image": release.image,
                                        "env": [{"name": "HOME", "value": "/tmp"}],
                                        "volumeMounts": [],
                                    }
                                ],
                                "volumes": [
                                    {"name": "release", "configMap": {"name": "shared-release"}}
                                ],
                            },
                        }
                    }
                }
            )
        if args[0] == "create":
            state["resources"] = json.loads(data)["items"]
            return ""
        if args[:4] == ("-n", "zetra-poc", "get", "job"):
            return '{"status":{"succeeded":1}}'
        if args[:3] == ("-n", "zetra-poc", "exec"):
            return json.dumps(state["record"])
        if args[:2] == ("-n", "zetra-poc-sandboxes"):
            return state["remaining"]
        if args[:3] == ("-n", "zetra-poc", "delete"):
            return ""
        raise AssertionError(args)

    monkeypatch.setitem(sys.modules, "qualify_kubani", SimpleNamespace(kube=kube))
    args = SimpleNamespace(
        session="investigate-loss",
        kind="model",
        release=tmp_path / "release.json",
        output=tmp_path,
    )
    return module, args, state


def test_launcher_isolates_worker_and_pins_release(launcher):
    module, args, state = launcher
    asyncio.run(module.launch(args))
    config, job = state["resources"]
    pod = job["spec"]["template"]
    assert pod["metadata"]["labels"]["app"] != "investigator-worker"
    assert config["immutable"] is True
    assert config["data"]["release.json"] == '{"identity":"qualified-release"}'
    release = next(v for v in pod["spec"]["volumes"] if v["name"] == "release")
    assert release["configMap"]["name"] == "investigate-loss"
    env = {item["name"]: item.get("value") for item in pod["spec"]["containers"][0]["env"]}
    assert env["TEMPORAL_ADDRESS"] == "temporal-frontend.temporal.svc.cluster.local:7233"


@pytest.mark.parametrize("failure", ["remaining-resource", "release-drift", "supervisor-failure"])
def test_launcher_persists_failed_qualification_when_host_checks_fail(launcher, failure):
    module, args, state = launcher
    if failure == "remaining-resource":
        state["remaining"] = "pod/sandbox"
    elif failure == "release-drift":
        state["record"]["release"] = "different-release"
    else:
        state["record"].update(qualification="FAILED", error="TimeoutError: gate not reached")
    with pytest.raises(AssertionError):
        asyncio.run(module.launch(args))
    summary = json.loads((args.output / args.session / "summary.json").read_text())
    assert summary["qualification"] == "FAILED"
    assert summary["error"]
    if failure == "supervisor-failure":
        assert summary["error"] == "TimeoutError: gate not reached"


def test_loss_proof_requires_kill_exact_timeout_and_unaccepted_candidate():
    spec = importlib.util.spec_from_file_location(
        "inflight_loss", Path(__file__).resolve().parents[2] / "evals/inflight_loss.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    gate = {
        "operation_id": "op",
        "accepted": {"cursor": 0},
        "candidate": {"position": {"cursor": 1}},
        "identity": "first",
    }
    kill = {"returncode": -9, "at_unix": 12}
    effects = [{"operation_id": "op", "scheduled_event_id": 1}]
    history = History(
        events=[
            HistoryEvent(
                event_time=Timestamp(seconds=10),
                activity_task_started_event_attributes=ActivityTaskStartedEventAttributes(
                    scheduled_event_id=1, identity="first"
                ),
            ),
            HistoryEvent(
                event_time=Timestamp(seconds=20),
                activity_task_timed_out_event_attributes=ActivityTaskTimedOutEventAttributes(
                    scheduled_event_id=1,
                    failure=Failure(
                        timeout_failure_info=TimeoutFailureInfo(
                            timeout_type=TimeoutType.TIMEOUT_TYPE_HEARTBEAT
                        )
                    ),
                ),
            ),
        ]
    )
    result = {
        "status": "OUTCOME_UNKNOWN",
        "cleanup": "DELETED",
        "position": {"cursor": 0},
        "pending": {"operation_id": "op"},
    }
    module.check_loss(history, effects, [], gate, result, kill)
    for change in (
        {"status": "SUCCEEDED"},
        {"position": {"cursor": 1}},
        {"pending": {"operation_id": "other"}},
        {"cleanup": "NOT_CONFIRMED"},
    ):
        with pytest.raises(AssertionError):
            module.check_loss(history, effects, [], gate, {**result, **change}, kill)
    with pytest.raises(AssertionError):
        module.check_loss(history, effects, [gate["candidate"]], gate, result, kill)
    with pytest.raises(AssertionError):
        module.check_loss(history, effects, [], gate, result, {"returncode": 0, "at_unix": 12})
    with pytest.raises(AssertionError):
        module.check_loss(history, effects, [], gate, result, {"returncode": -9, "at_unix": 50})
    history.events[0].activity_task_started_event_attributes.identity = "other"
    with pytest.raises(AssertionError):
        module.check_loss(history, effects, [], gate, result, kill)
