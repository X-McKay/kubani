"""Render the standard SDK CLI with explicit caller-owned deployment inputs."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from zetra.manifest import Release, load_agent

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def release_file(tmp_path):
    release = Release(
        agent=load_agent(ROOT),
        image="registry.example/agent@sha256:" + "a" * 64,
        source_sha256="b" * 64,
        policy_sha256="c" * 64,
        lock_sha256="d" * 64,
        sdk_revision="e" * 40,
    )
    path = tmp_path / "release.json"
    path.write_text(release.model_dump_json())
    return path


def render(release_file, *args):
    return subprocess.run(
        [sys.executable, str(ROOT / "deploy/render-worker.py"), str(release_file), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_worker_uses_sdk_cli_and_explicit_connections(release_file):
    run = render(release_file)
    assert run.returncode == 0, run.stderr
    deployment = next(i for i in json.loads(run.stdout)["items"] if i["kind"] == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["command"][:3] == ["/app/.venv/bin/python", "-m", "zetra"]
    assert container["command"][-7:] == [
        "worker",
        "--key-file",
        "/etc/zetra-key/key",
        "--release",
        "/etc/zetra/release.json",
        "--provider",
        "kubani-k8s-read",
    ]
    env = {e["name"]: e["value"] for e in container["env"]}
    assert env["TEMPORAL_NAMESPACE"] == "zetra-poc"
    assert env["TEMPORAL_ADDRESS"] == "temporal-frontend.temporal.svc.cluster.local:7233"
    assert env["OPENSHELL_TLS_DIR"] == "/etc/openshell"


def test_run_job_keeps_exact_identity_without_worker_credentials(release_file):
    run = render(release_file, "--session", "investigate-once")
    assert run.returncode == 0, run.stderr
    job = next(i for i in json.loads(run.stdout)["items"] if i["kind"] == "Job")
    pod = job["spec"]["template"]["spec"]
    container = pod["containers"][0]
    command = container["command"]
    assert command[:3] == ["/app/.venv/bin/python", "-m", "zetra"]
    assert command[command.index("--session") + 1] == "investigate-once"
    assert command[command.index("--output") + 1] == "/artifacts/results/investigate-once"
    assert not {"tls", "key"} & {v["name"] for v in pod["volumes"]}
    assert pod["restartPolicy"] == "OnFailure"
    assert job["spec"]["backoffLimit"] == 2


@pytest.mark.parametrize("session", ["../escape", "/absolute", "", "a/b", "investigate-.."])
def test_invalid_session_is_rejected_before_job_render(release_file, session):
    assert render(release_file, "--session", session).returncode != 0
