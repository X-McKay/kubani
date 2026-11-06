import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).parents[1] / "infrastructure/scripts/ops/t13_gateway_replace.py"
spec = importlib.util.spec_from_file_location("t13_operator", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def event(now=1_000_000_000_000):
    return {
        "event": module.EVENT,
        "emitted_ns": now,
        "deadline_seconds": 100,
        "old_pods": [
            {"name": "agents-a", "uid": "uid-a", "ready": True, "image_id": "image"},
            {"name": "agents-b", "uid": "uid-b", "ready": True, "image_id": "image"},
        ],
    }


def test_expired_or_clock_future_signal_refuses():
    e = event()
    for now in (e["emitted_ns"] - 1, e["emitted_ns"] + 71_000_000_000):
        with pytest.raises(ValueError):
            module.validate_event(e, now)
    module.validate_event(e, e["emitted_ns"] + 2_000_000_000)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e.pop("emitted_ns"),
        lambda e: e.update(deadline_seconds=200),
        lambda e: e["old_pods"][1].update(uid="uid-a"),
        lambda e: e["old_pods"][0].update(ready=False),
    ],
)
def test_malformed_signal_refuses(mutate):
    e = event()
    mutate(e)
    with pytest.raises(ValueError):
        module.validate_event(e, 1_000_000_000_000)


class FakeAPI:
    def __init__(self, finish_at=99, replace_at=99, late_at=99):
        self.calls = 0
        self.deletions = []
        self.finish_at = finish_at
        self.replace_at = replace_at
        self.late_at = late_at

    def active(self, state):
        self.calls += 1
        if self.calls >= self.finish_at:
            raise ValueError("Job is finished")
        if self.calls >= self.replace_at:
            raise ValueError("Job Pod replaced")

    def gateway(self, expected):
        return None

    def delete(self, expected):
        self.deletions.append(expected["uid"])


def test_active_and_deadline_checked_before_each_delete(tmp_path):
    e = event()
    api = FakeAPI(finish_at=3)
    state = {"event": e, "deletions": []}
    with pytest.raises(ValueError, match="finished"):
        module.replace(
            api, state, tmp_path / "receipt.json", now=lambda: e["emitted_ns"]
        )
    assert api.deletions == ["uid-a"]
    assert len(state["deletions"]) == 1


def test_replaced_job_pod_refuses_before_any_delete(tmp_path):
    e = event()
    api = FakeAPI(replace_at=1)
    with pytest.raises(ValueError, match="replaced"):
        module.replace(
            api,
            {"event": e, "deletions": []},
            tmp_path / "receipt.json",
            now=lambda: e["emitted_ns"],
        )
    assert not api.deletions


def test_expired_between_deletes_refuses_second(tmp_path):
    e = event()
    api = FakeAPI()
    values = iter(
        [
            e["emitted_ns"],
            e["emitted_ns"],
            e["emitted_ns"],
            e["emitted_ns"] + 71_000_000_000,
        ]
    )
    with pytest.raises(ValueError):
        module.replace(
            api,
            {"event": e, "deletions": []},
            tmp_path / "receipt.json",
            now=lambda: next(values),
        )
    assert api.deletions == ["uid-a"]


def test_success_retains_both_exact_uid_receipts(tmp_path):
    e = event()
    api = FakeAPI()
    state = {"event": e, "deletions": []}
    module.replace(api, state, tmp_path / "receipt.json", now=lambda: e["emitted_ns"])
    assert api.deletions == ["uid-a", "uid-b"]
    assert all(
        row["started_ns"] == row["acknowledged_ns"] == e["emitted_ns"]
        for row in state["deletions"]
    )
    assert (tmp_path / "receipt.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "fault",
    [
        "job_uid",
        "pod_uid",
        "owner_uid",
        "job_complete",
        "pod_terminated",
        "pod_pending",
        "retry3",
        "arbitrary_agent",
        "session_agent",
    ],
)
@pytest.mark.parametrize(
    "agent",
    [
        "conformance-budget-day",
        "conformance-budget-day-retry",
        "conformance-budget-day-retry2",
    ],
)
def test_real_active_adapter_refuses_changed_or_inactive_run(fault, agent):
    from types import SimpleNamespace as NS

    job = NS(
        metadata=NS(uid="job-exact", resource_version="10", deletion_timestamp=None),
        status=NS(succeeded=0, failed=0, conditions=[]),
        spec=NS(
            template=NS(
                spec=NS(containers=[NS(args=["--tests", "T13", "--agent", agent])])
            )
        ),
    )
    pod = NS(
        metadata=NS(
            uid="pod-exact",
            resource_version="20",
            name="harness-exact",
            deletion_timestamp=None,
            owner_references=[NS(kind="Job", controller=True, uid="job-exact")],
        ),
        status=NS(phase="Running", container_statuses=[NS(state=NS(terminated=None))]),
    )
    state = {"job_uid": "job-exact", "harness_pod_uid": "pod-exact", "event": event()}
    api = module.API.__new__(module.API)
    api.batch = NS(read_namespaced_job=lambda *a, **kw: job)
    api.core = NS(list_namespaced_pod=lambda *a, **kw: NS(items=[pod]))
    assert api.active(state) is pod
    assert state["active_observation"]["job_resource_version"] == "10"
    if fault == "job_uid":
        job.metadata.uid = "other-job"
    elif fault == "pod_uid":
        pod.metadata.uid = "other-pod"
    elif fault == "owner_uid":
        pod.metadata.owner_references[0].uid = "other-owner"
    elif fault == "job_complete":
        job.status.conditions = [NS(type="Complete", status="True")]
    elif fault == "pod_terminated":
        pod.status.container_statuses[0].state.terminated = NS(exit_code=0)
    elif fault == "pod_pending":
        pod.status.phase = "Pending"
    else:
        job.spec.template.spec.containers[0].args[-1] = {
            "retry3": "conformance-budget-day-retry3",
            "arbitrary_agent": "conformance-budget-day-arbitrary",
            "session_agent": "conformance-budget-session",
        }[fault]
    with pytest.raises(ValueError):
        api.active(state)


def test_real_kubernetes_client_preserves_single_json_log_line():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from types import SimpleNamespace as NS

    client = pytest.importorskip("kubernetes.client")
    raw = (json.dumps(event()) + "\n").encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = client.Configuration()
    config.host = f"http://127.0.0.1:{server.server_port}"
    config.proxy = None
    api_client = client.ApiClient(config)
    try:
        api = module.API.__new__(module.API)
        api.core = client.CoreV1Api(api_client)
        # The generated response_type=str deserializes JSON then str(dict),
        # despite text/plain, losing the wire representation of a sole event.
        parsed = api.core.read_namespaced_pod_log("test", "agent-platform")
        assert parsed != raw.decode()
        assert api.logs(NS(metadata=NS(name="test"))) == raw.decode()
        assert json.loads(api.logs(NS(metadata=NS(name="test")))) == event()
    finally:
        api_client.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
