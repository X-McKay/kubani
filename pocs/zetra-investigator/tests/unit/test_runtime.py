import pytest

from kubani_investigator import runtime


def test_run_requires_reusable_session_identity():
    with pytest.raises(SystemExit) as error:
        runtime.parse_args(["run"])
    assert error.value.code == 2


def test_run_preserves_explicit_identity():
    args = runtime.parse_args(["run", "--session", "investigate-recovery-01"])
    assert args.session == "investigate-recovery-01"


@pytest.mark.parametrize("session", ["../escape", "/absolute", "", "a/b", "investigate-.."])
def test_session_identity_cannot_escape_results(session):
    with pytest.raises(SystemExit):
        runtime.parse_args(["run", "--session", session])


def test_worker_does_not_need_a_session():
    assert runtime.parse_args(["worker"]).session is None


def test_retry_after_lost_ack_uses_same_temporal_identity(tmp_path):
    import asyncio

    from zetra.session import SessionHandle

    handle = SessionHandle(
        namespace="zetra-poc",
        workflow_id="investigate-retry",
        run_id="exact-run",
        runtime_id="kubani-kubernetes-poc-v1",
    )

    class Client:
        def __init__(self):
            self.requests = []

        async def submit(self, release, **request):
            self.requests.append((release, request))
            if len(self.requests) == 1:
                raise ConnectionError("Accepted start, acknowledgement lost")
            return handle

        async def wait(self, selected):
            assert selected == handle
            return {"status": "SUCCEEDED", "cleanup": "DELETED"}

        async def read_files(self, selected):
            assert selected == handle
            return {"report.md": b"Evidence report"}

    client = Client()
    with pytest.raises(ConnectionError):
        asyncio.run(runtime.run_investigation(client, "release", tmp_path, "investigate-retry"))
    for _ in range(2):
        assert (
            asyncio.run(runtime.run_investigation(client, "release", tmp_path, "investigate-retry"))
            == handle
        )
    assert client.requests[0] == client.requests[1] == client.requests[2]
    assert (tmp_path / "results/investigate-retry/report.md").read_text() == "Evidence report"


@pytest.mark.parametrize("signal_name", ["SIGTERM", "SIGINT"])
def test_worker_drains_on_process_signal(signal_name):
    import subprocess
    import sys

    code = """
import asyncio, os, signal
from kubani_investigator.runtime import run_worker
class Worker:
    def __init__(self):
        self.finished = asyncio.Event()
        self.shutdown_requested = False
    async def run(self):
        asyncio.get_running_loop().call_later(0.05, os.kill, os.getpid(), SIGNAL)
        await self.finished.wait()
        assert self.shutdown_requested
    async def shutdown(self):
        self.shutdown_requested = True
        await asyncio.sleep(0.05)
        self.finished.set()
asyncio.run(run_worker(Worker()))
print("drained")
""".replace("SIGNAL", "signal." + signal_name)
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=10, check=False
    )
    assert completed.returncode == 0, completed.stderr
    assert "drained" in completed.stdout


def test_local_receipt_is_not_recovery_authority(tmp_path):
    import asyncio

    from zetra.session import SessionHandle

    handle = SessionHandle(
        namespace="zetra-poc",
        workflow_id="investigate-receipt",
        run_id="exact-run",
        runtime_id="kubani-kubernetes-poc-v1",
    )
    output = tmp_path / "results/investigate-receipt"
    output.mkdir(parents=True)
    (output / "handle.json").write_text('{"partial":')

    class Client:
        async def submit(self, *args, **kwargs):
            return handle

        async def wait(self, selected):
            return {"status": "SUCCEEDED", "cleanup": "DELETED"}

        async def read_files(self, selected):
            return {"report.md": b"Recovered through Temporal"}

    assert (
        asyncio.run(runtime.run_investigation(Client(), "release", tmp_path, "investigate-receipt"))
        == handle
    )
