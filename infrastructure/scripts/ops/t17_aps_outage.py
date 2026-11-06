#!/usr/bin/env python3
"""Explicit operator-only T17 outage control. The conformance Job has no write rights."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

NAMESPACE = "agent-platform"
DEPLOYMENT = "agent-policy-service"
CONTROL = "conformance-aps-outage-control"
RECONCILE = "kustomize.toolkit.fluxcd.io/reconcile"


class API:
    def __init__(self, kubeconfig):
        self.prefix = [
            "kubectl",
            "--kubeconfig",
            str(kubeconfig),
            "--request-timeout=15s",
        ]

    def command(self, args, document=None):
        result = subprocess.run(
            self.prefix + args,
            input=json.dumps(document) if document is not None else None,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        if result.returncode:
            # Avoid printing server output: deployment responses can contain configuration.
            raise RuntimeError(f"kubectl {args[0]} failed ({result.returncode})")
        return result.stdout

    def get(self, resource, name, namespace=NAMESPACE, optional=False):
        raw = self.command(
            ["get", resource, name, "-n", namespace, "-o", "json"]
            + (["--ignore-not-found"] if optional else [])
        )
        return json.loads(raw) if raw.strip() else None

    def create(self, obj):
        return json.loads(self.command(["create", "-f", "-", "-o", "json"], obj))

    def patch(self, resource, name, patch, namespace=NAMESPACE):
        return json.loads(
            self.command(
                [
                    "patch",
                    resource,
                    name,
                    "-n",
                    namespace,
                    "--type=json",
                    "-p",
                    json.dumps(patch),
                    "-o",
                    "json",
                ]
            )
        )


def save(path, state):
    path = Path(path)
    # A unique 0600 sibling also permits recovery after SIGKILL left an old temp.
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(state, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def config_hash(obj):
    spec = {k: v for k, v in obj["spec"].items() if k != "replicas"}
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def guards(obj):
    return [
        {"op": "test", "path": "/metadata/uid", "value": obj["metadata"]["uid"]},
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": obj["metadata"]["resourceVersion"],
        },
    ]


def current(api, state):
    obj = api.get("deployment", DEPLOYMENT)
    annotation = obj["metadata"].get("annotations", {}).get(RECONCILE)
    if (
        obj["metadata"]["uid"] != state["deployment_uid"]
        or config_hash(obj) != state["spec_sha"]
        or obj["spec"].get("replicas") not in (0, state["original_replicas"])
        or annotation not in ("disabled", state["original_annotation"])
    ):
        raise ValueError(
            "APS identity/spec/replicas/Flux annotation changed concurrently; refusing overwrite"
        )
    return obj


def receipt(api, state):
    obj = api.get("configmap", CONTROL)
    if obj["metadata"]["uid"] != state["receipt_uid"]:
        raise ValueError("operator receipt ConfigMap replaced")
    data = json.loads(obj["data"]["receipt.json"])
    if any(
        k not in state["receipt"] or state["receipt"][k] != v for k, v in data.items()
    ):
        raise ValueError("operator receipt changed concurrently")
    return obj, data


def publish(api, state):
    obj, data = receipt(api, state)
    if data != state["receipt"]:
        api.patch(
            "configmap",
            CONTROL,
            guards(obj)
            + [
                {
                    "op": "replace",
                    "path": "/data/receipt.json",
                    "value": json.dumps(state["receipt"], separators=(",", ":")),
                }
            ],
        )


def prepare(api, marker, path):
    if not re.fullmatch(r"[0-9a-f]{16}", marker) or Path(path).exists():
        raise ValueError("use a fresh 16-hex marker and unused local state path")
    obj = api.get("deployment", DEPLOYMENT)
    if obj["spec"].get("replicas") != 2 or obj["status"].get("readyReplicas") != 2:
        raise ValueError("APS must initially have two Ready replicas")
    if api.get("configmap", CONTROL, optional=True) is not None:
        raise ValueError(
            "archive and remove the prior receipt ConfigMap before a new run"
        )
    state = {
        "schema": "t17-operator-v1",
        "marker": marker,
        "deployment_uid": obj["metadata"]["uid"],
        "original_resource_version": obj["metadata"]["resourceVersion"],
        "original_replicas": 2,
        "original_annotation": obj["metadata"].get("annotations", {}).get(RECONCILE),
        "spec_sha": config_hash(obj),
        "restored": False,
    }
    state["receipt"] = {
        "schema": "t17-v1",
        "marker": marker,
        "deployment_uid": state["deployment_uid"],
        "original_replicas": 2,
    }
    # Save before any API write; this file is the recovery authority if the process dies.
    save(path, state)
    cm = api.create(
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": CONTROL, "namespace": NAMESPACE},
            "data": {
                "receipt.json": json.dumps(state["receipt"], separators=(",", ":"))
            },
        }
    )
    state["receipt_uid"] = cm["metadata"]["uid"]
    save(path, state)
    return state


def annotation_patch(obj, value):
    if "annotations" not in obj["metadata"]:
        return (
            [
                {
                    "op": "add",
                    "path": "/metadata/annotations",
                    "value": {RECONCILE: value},
                }
            ]
            if value is not None
            else []
        )
    key = "/metadata/annotations/" + RECONCILE.replace("/", "~1")
    if value is None:
        return (
            [{"op": "remove", "path": key}]
            if RECONCILE in obj["metadata"]["annotations"]
            else []
        )
    return [{"op": "add", "path": key, "value": value}]


def pause(api, state):
    obj = current(api, state)
    if obj["spec"]["replicas"] != state["original_replicas"]:
        raise ValueError("APS was scaled before the operator-controlled window")
    api.patch("deployment", DEPLOYMENT, guards(obj) + annotation_patch(obj, "disabled"))


def scale(api, state, replicas, phase, path):
    obj = current(api, state)
    receipt(api, state)
    if phase in state["receipt"]:
        raise ValueError("scale receipt already exists; use restore after a failed run")
    expected = 2 if phase == "down" else 0
    if replicas != (0 if phase == "down" else 2) or obj["spec"]["replicas"] != expected:
        raise ValueError("unexpected scale transition")
    if obj["metadata"].get("annotations", {}).get(RECONCILE) != "disabled":
        raise ValueError("Flux reconciliation is not paused for APS")
    started = time.time_ns()
    updated = api.patch(
        "deployment",
        DEPLOYMENT,
        guards(obj)
        + [
            {"op": "test", "path": "/spec/replicas", "value": expected},
            {"op": "replace", "path": "/spec/replicas", "value": replicas},
        ],
    )
    acknowledged = time.time_ns()
    state["receipt"][phase] = {
        "started_ns": started,
        "acknowledged_ns": acknowledged,
        "resource_version": updated["metadata"]["resourceVersion"],
        "generation": updated["metadata"]["generation"],
    }
    save(path, state)
    publish(api, state)


def restore(api, state, path):
    # Independent best-effort steps: a failed replica write must not leave Flux
    # disabled. Fresh UID/RV/spec checks precede every idempotent retry.
    failures = []

    def replicas():
        obj = current(api, state)
        if obj["spec"]["replicas"] != state["original_replicas"]:
            if "up" in state["receipt"]:
                raise ValueError("replicas changed after the recorded restoration")
            started = time.time_ns()
            obj = api.patch(
                "deployment",
                DEPLOYMENT,
                guards(obj)
                + [
                    {
                        "op": "replace",
                        "path": "/spec/replicas",
                        "value": state["original_replicas"],
                    }
                ],
            )
            state["receipt"]["up"] = {
                "started_ns": started,
                "acknowledged_ns": time.time_ns(),
                "resource_version": obj["metadata"]["resourceVersion"],
                "generation": obj["metadata"]["generation"],
            }
            save(path, state)

    def annotation():
        obj = current(api, state)
        patches = annotation_patch(obj, state["original_annotation"])
        if patches:
            api.patch("deployment", DEPLOYMENT, guards(obj) + patches)

    for operation in (replicas, annotation):
        for attempt in range(3):
            try:
                operation()
                break
            except RuntimeError:
                if attempt == 2:
                    failures.append(operation.__name__)
                else:
                    time.sleep(0.2)
            except Exception:
                failures.append(operation.__name__)
                break
    if failures:
        state["restoration_failures"] = failures
        save(path, state)
        raise RuntimeError(
            "configuration restoration incomplete: " + ", ".join(failures)
        )
    final = current(api, state)
    if (
        final["spec"]["replicas"] != state["original_replicas"]
        or final["metadata"].get("annotations", {}).get(RECONCILE)
        != state["original_annotation"]
    ):
        raise ValueError("exact restoration was not observed")
    state["restored"] = (
        True  # desired configuration, not a substitute for Ready evidence
    )
    save(path, state)
    # Receipt failure is reported after restoring the workload configuration.
    publish(api, state)


def wait_phase(api, state, job, phase, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        obj = api.get("job", job)
        if "job_uid" not in state:
            state["job_uid"] = obj["metadata"]["uid"]
        if obj["metadata"]["uid"] != state["job_uid"]:
            raise ValueError("T17 Job replaced")
        container = obj["spec"]["template"]["spec"]["containers"][0]
        args = container.get("args", [])
        env = {item["name"]: item.get("value") for item in container.get("env", [])}
        if (
            "--tests" not in args
            or args[args.index("--tests") + 1] != "T17"
            or env.get("APS_OUTAGE_MARKER") != state["marker"]
        ):
            raise ValueError("operator Job is not the exact T17 marker/test")
        pods = json.loads(
            api.command(
                ["get", "pods", "-n", NAMESPACE, "-l", "job-name=" + job, "-o", "json"]
            )
        )["items"]
        if len(pods) > 1:
            raise ValueError("T17 Job has more than one Pod")
        if pods:
            pod = pods[0]
            if not any(
                owner.get("kind") == "Job"
                and owner.get("uid") == state["job_uid"]
                and owner.get("controller") is True
                for owner in pod["metadata"].get("ownerReferences", [])
            ):
                raise ValueError("T17 Pod is not owned by the pinned Job")
            if "job_pod_uid" not in state:
                state["job_pod_uid"] = pod["metadata"]["uid"]
            if pod["metadata"]["uid"] != state["job_pod_uid"]:
                raise ValueError("T17 Job Pod replaced")
            if pod["status"]["phase"] == "Running":
                raw = api.command(
                    [
                        "logs",
                        pod["metadata"]["name"],
                        "-n",
                        NAMESPACE,
                        "-c",
                        "harness",
                        "--limit-bytes=1048576",
                    ]
                )
                for line in raw.splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if (
                        isinstance(event, dict)
                        and event.get("test") == "T17"
                        and event.get("marker") == state["marker"]
                        and event.get("phase") == phase
                    ):
                        return
            elif pod["status"]["phase"] in ("Succeeded", "Failed"):
                raise RuntimeError("T17 Job ended before the required operator phase")
        time.sleep(0.5)
    raise TimeoutError("T17 operator phase deadline")


def run(api, state, path, job):
    if state.get("restored") or any(p in state["receipt"] for p in ("down", "up")):
        raise ValueError("run requires a freshly prepared state")
    try:
        wait_phase(api, state, job, "baseline_ready", 240)
        save(path, state)
        pause(api, state)
        scale(api, state, 0, "down", path)
        wait_phase(api, state, job, "zero_confirmed_restore_now", 100)
        scale(api, state, 2, "up", path)
        wait_phase(api, state, job, "replicas_restored", 100)
    finally:
        restore(api, state, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "restore"))
    parser.add_argument("--kubeconfig", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--marker")
    parser.add_argument("--job", default="conformance-fail-closed-harness")
    args = parser.parse_args(argv)
    if not args.kubeconfig.is_file():
        parser.error("explicit kubeconfig file required")
    api = API(args.kubeconfig)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    if args.action == "prepare":
        state = prepare(api, args.marker or "", args.state)
    else:
        state = json.loads(args.state.read_text())
        if state.get("schema") != "t17-operator-v1":
            raise ValueError("invalid local recovery state")
        if args.action == "run":
            run(api, state, args.state, args.job)
        else:
            restore(api, state, args.state)
    print(
        json.dumps(
            {
                "marker": state["marker"],
                "state": str(args.state),
                "restored": state["restored"],
            }
        )
    )


if __name__ == "__main__":
    main()
