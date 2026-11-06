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


SERVER_REASONS = {
    "BadRequest": 400,
    "Unauthorized": 401,
    "Forbidden": 403,
    "NotFound": 404,
    "Conflict": 409,
    "Invalid": 422,
    "TooManyRequests": 429,
    "InternalError": 500,
    "ServiceUnavailable": 503,
    "Timeout": 504,
    "ServerTimeout": 504,
}
LOCK_MESSAGE = (
    'Operation cannot be fulfilled on deployments.apps "agent-policy-service": '
    "the object has been modified; please apply your changes to the latest version and try again"
)
MAX_CONFLICT_ATTEMPTS = 3


class APIError(RuntimeError):
    """Only allowlisted metadata escapes; raw stderr/objects are never retained."""

    def __init__(self, operation, returncode, reason="Unknown", *, conflict=False):
        self.status = SERVER_REASONS.get(reason)
        self.reason = reason
        self.returncode = returncode
        self.resource_version_conflict = conflict
        self.category = "resource_version_conflict" if conflict else "request_failed"
        verb = (
            operation if operation in {"get", "create", "patch", "logs"} else "command"
        )
        super().__init__(
            f"kubectl {verb} failed (exit={returncode}, status={self.status}, "
            f"reason={reason}, category={self.category})"
        )


def command_error(operation, returncode, stderr):
    reason, message = "Unknown", ""
    # kubectl prints API Status reasons as this prefix. Do not copy its remainder:
    # validation/admission messages may embed the complete submitted object.
    for line in stderr.splitlines():
        match = re.fullmatch(r"Error from server \(([A-Za-z]+)\): (.*)", line)
        if match:
            if match[1] in SERVER_REASONS:
                reason, message = match[1], match[2]
            break
        if line.startswith("The request is invalid:"):
            reason = "Invalid"
            break
    return APIError(
        operation,
        returncode,
        reason,
        conflict=operation == "patch"
        and reason == "Conflict"
        and message == LOCK_MESSAGE,
    )


class API:
    def __init__(self, kubeconfig):
        self.prefix = [
            "kubectl",
            "--kubeconfig",
            str(kubeconfig),
            "--request-timeout=15s",
        ]

    def command(self, args, document=None):
        try:
            result = subprocess.run(
                self.prefix + args,
                input=json.dumps(document) if document is not None else None,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise APIError(args[0], None, "ClientTimeout") from None
        if result.returncode:
            raise command_error(args[0], result.returncode, result.stderr) from None
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


def annotation_hash(obj):
    value = obj["metadata"].get("annotations", {}).get(RECONCILE)
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def phase_receipt(state, phase, before, updated, changed, started):
    row = {
        "started_ns": started,
        "acknowledged_ns": time.time_ns(),
        "resource_version": updated["metadata"]["resourceVersion"],
        "generation": updated["metadata"]["generation"],
    }
    if state["receipt"]["schema"] == "t17-v2":
        row.update(
            resource_version_before=before["metadata"]["resourceVersion"],
            generation_before=before["metadata"]["generation"],
            replicas_before=before["spec"]["replicas"],
            replicas=updated["spec"]["replicas"],
            annotation_sha_before=annotation_hash(before),
            annotation_sha=annotation_hash(updated),
            changed=changed,
        )
    state["receipt"][phase] = row


def guards(obj):
    return [
        {"op": "test", "path": "/metadata/uid", "value": obj["metadata"]["uid"]},
        {
            # A stale nonempty RV reaches the storage CAS and returns explicit 409.
            # A JSON test here instead fails generically with 422 before storage.
            "op": "replace",
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
        "schema": "t17-v2",
        "marker": marker,
        "deployment_uid": state["deployment_uid"],
        "original_replicas": 2,
        "original_generation": obj["metadata"]["generation"],
        "original_annotation_sha": annotation_hash(obj),
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
    if obj["metadata"].get("annotations", {}).get(RECONCILE) == value:
        return []
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


def mutate_deployment(api, state, operation, build_patch, path=None):
    for attempt in range(1, MAX_CONFLICT_ATTEMPTS + 1):
        obj = current(api, state)
        patches = build_patch(obj)
        if not patches:
            return obj, False, obj
        try:
            return api.patch("deployment", DEPLOYMENT, guards(obj) + patches), True, obj
        except RuntimeError as error:
            diagnostic = {
                "operation": operation,
                "attempt": attempt,
                "observed_ns": time.time_ns(),
                "status": error.status if isinstance(error, APIError) else None,
                "reason": error.reason if isinstance(error, APIError) else "Unknown",
                "category": error.category
                if isinstance(error, APIError)
                else "uncertain_failure",
            }
            state.setdefault("operation_errors", []).append(diagnostic)
            if path is not None:
                save(path, state)
            if not (
                isinstance(error, APIError)
                and error.resource_version_conflict
                and attempt < MAX_CONFLICT_ATTEMPTS
            ):
                raise
            time.sleep(0.1)
    raise AssertionError("bounded mutation loop exhausted")


def pause(api, state, path=None):
    if "pause" in state["receipt"]:
        raise ValueError("pause receipt already exists")

    def patch(obj):
        if obj["spec"]["replicas"] != state["original_replicas"]:
            raise ValueError("APS was scaled before the operator-controlled window")
        return annotation_patch(obj, "disabled")

    started = time.time_ns()
    updated, changed, before = mutate_deployment(api, state, "pause", patch, path)
    if state["receipt"]["schema"] == "t17-v2":
        phase_receipt(state, "pause", before, updated, changed, started)
        if path is not None:
            save(path, state)
        publish(api, state)


def scale(api, state, replicas, phase, path):
    if phase in state["receipt"]:
        raise ValueError("scale receipt already exists; use restore after a failed run")
    expected = 2 if phase == "down" else 0

    def patch(obj):
        receipt(api, state)
        if (
            replicas != (0 if phase == "down" else 2)
            or obj["spec"]["replicas"] != expected
        ):
            raise ValueError("unexpected scale transition")
        if obj["metadata"].get("annotations", {}).get(RECONCILE) != "disabled":
            raise ValueError("Flux reconciliation is not paused for APS")
        return [
            {"op": "test", "path": "/spec/replicas", "value": expected},
            {"op": "replace", "path": "/spec/replicas", "value": replicas},
        ]

    started = time.time_ns()
    updated, changed, before = mutate_deployment(api, state, "scale_" + phase, patch, path)
    phase_receipt(state, phase, before, updated, changed, started)
    save(path, state)
    publish(api, state)


def restore(api, state, path):
    # Independent best-effort steps: a failed replica write must not leave Flux
    # disabled. Fresh UID/RV/spec checks precede every idempotent retry.
    failures = []

    def replicas():
        def patch(obj):
            if obj["spec"]["replicas"] == state["original_replicas"]:
                return []
            if "up" in state["receipt"]:
                raise ValueError("replicas changed after the recorded restoration")
            return [
                {"op": "test", "path": "/spec/replicas", "value": 0},
                {
                    "op": "replace",
                    "path": "/spec/replicas",
                    "value": state["original_replicas"],
                },
            ]

        started = time.time_ns()
        obj, changed, before = mutate_deployment(api, state, "restore_replicas", patch, path)
        if changed:
            phase_receipt(state, "up", before, obj, changed, started)
            save(path, state)

    def annotation():
        def patch(obj):
            if "resume" in state["receipt"]:
                if annotation_patch(obj, state["original_annotation"]):
                    raise ValueError("annotation changed after recorded restoration")
                return []
            return annotation_patch(obj, state["original_annotation"])

        started = time.time_ns()
        updated, changed, before = mutate_deployment(
            api, state, "restore_annotation", patch, path
        )
        # Never turn an external/unacknowledged restore into our mutation receipt.
        # The explicit no-op is valid only when the original annotation was disabled.
        if (
            state["receipt"]["schema"] == "t17-v2"
            and "resume" not in state["receipt"]
            and (changed or state["original_annotation"] == "disabled")
        ):
            phase_receipt(state, "resume", before, updated, changed, started)
            save(path, state)

    for operation in (replicas, annotation):
        try:
            operation()
        except Exception:
            failures.append(operation.__name__)
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
    if (
        state["receipt"]["schema"] != "t17-v2"
        or state.get("restored")
        or any(p in state["receipt"] for p in ("pause", "down", "up", "resume"))
    ):
        raise ValueError("run requires a freshly prepared state")
    try:
        wait_phase(api, state, job, "baseline_ready", 240)
        save(path, state)
        pause(api, state, path)
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
