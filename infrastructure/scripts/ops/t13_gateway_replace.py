#!/usr/bin/env python3
"""Replace the exact gateway Pods requested by an active, fresh T13 run.

Requires the Kubernetes Python client. Run outside the harness with an explicit
kubeconfig. No workload configuration, budget ledger, or credential is modified.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import time

EVENT = "T13 awaiting gateway replacement"
NAMESPACE = "agent-platform"
JOB = "conformance-budget-day-harness"
GATEWAY_NAMESPACE = "ai-gateway"
LABEL = "gateway.networking.k8s.io/gateway-name"
AGENTS = {"conformance-budget-day", "conformance-budget-day-retry"}


def save(path, value):
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def validate_event(event, now):
    if (
        not isinstance(event, dict)
        or event.get("event") != EVENT
        or type(event.get("emitted_ns")) is not int
        or type(event.get("deadline_seconds")) is not int
        or event["deadline_seconds"] != 100
    ):
        raise ValueError("invalid timestamped T13 signal")
    # Reserve at least30 seconds for deletion and replacement readiness. Refuse
    # clock skew in either direction; clocks are part of qualification evidence.
    if not 0 <= now - event["emitted_ns"] <= 70_000_000_000:
        raise ValueError("T13 signal is expired or clock is ahead of operator")
    pods = event.get("old_pods")
    if (
        not isinstance(pods, list)
        or len(pods) != 2
        or any(not isinstance(p, dict) for p in pods)
        or len({p.get("uid") for p in pods}) != 2
        or len({p.get("name") for p in pods}) != 2
        or any(
            p.get("ready") is not True
            or any(
                not isinstance(p.get(k), str) or not p[k]
                for k in ("name", "uid", "image_id")
            )
            for p in pods
        )
    ):
        raise ValueError("invalid exact gateway Pod inventory")


class API:
    def __init__(self, kubeconfig):
        from kubernetes import client, config

        config.load_kube_config(str(kubeconfig))
        self.client = client
        self.core = client.CoreV1Api()
        self.batch = client.BatchV1Api()

    def active(self, state):
        job = self.batch.read_namespaced_job(JOB, NAMESPACE, _request_timeout=5)
        if (
            job.metadata.deletion_timestamp
            or job.status.succeeded
            or job.status.failed
            or any(
                c.type in ("Complete", "Failed", "FailureTarget", "SuccessCriteriaMet")
                and c.status == "True"
                for c in job.status.conditions or []
            )
        ):
            raise ValueError("T13 Job is finished or terminating")
        if "job_uid" in state and state["job_uid"] != job.metadata.uid:
            raise ValueError("T13 Job replaced")
        state["job_uid"] = job.metadata.uid
        containers = job.spec.template.spec.containers
        if len(containers) != 1:
            raise ValueError("unexpected harness container count")
        args = containers[0].args or []
        if (
            "--tests" not in args
            or args[args.index("--tests") + 1] != "T13"
            or "--agent" not in args
            or args[args.index("--agent") + 1] not in AGENTS
        ):
            raise ValueError("Job is not the exact daily-budget test")
        pods = self.core.list_namespaced_pod(
            NAMESPACE, label_selector="job-name=" + JOB, _request_timeout=5
        ).items
        if not pods:
            if "harness_pod_uid" in state:
                raise ValueError("harness Pod disappeared")
            return None
        if len(pods) != 1:
            raise ValueError("unexpected harness Pod count")
        pod = pods[0]
        if not any(
            o.kind == "Job" and o.controller and o.uid == state["job_uid"]
            for o in pod.metadata.owner_references or []
        ):
            raise ValueError("harness Pod owner mismatch")
        if "harness_pod_uid" in state and state["harness_pod_uid"] != pod.metadata.uid:
            raise ValueError("harness Pod replaced")
        state["harness_pod_uid"] = pod.metadata.uid
        state["harness_pod_name"] = pod.metadata.name
        if (
            pod.metadata.deletion_timestamp
            or pod.status.phase in ("Succeeded", "Failed")
            or any(s.state.terminated for s in pod.status.container_statuses or [])
        ):
            raise ValueError("harness Pod ended")
        if pod.status.phase != "Running":
            if "event" in state:
                raise ValueError("harness Pod no longer Running")
            return None
        state["active_observation"] = {
            "job_uid": job.metadata.uid,
            "job_resource_version": job.metadata.resource_version,
            "harness_pod_uid": pod.metadata.uid,
            "harness_pod_resource_version": pod.metadata.resource_version,
            "observed_ns": time.time_ns(),
        }
        return pod

    def logs(self, pod):
        return self.core.read_namespaced_pod_log(
            pod.metadata.name,
            NAMESPACE,
            container="harness",
            limit_bytes=1048576,
            _request_timeout=5,
        )

    def gateway(self, expected):
        pod = self.core.read_namespaced_pod(
            expected["name"], GATEWAY_NAMESPACE, _request_timeout=5
        )
        statuses = pod.status.container_statuses or []
        if (
            pod.metadata.uid != expected["uid"]
            or pod.metadata.deletion_timestamp
            or (pod.metadata.labels or {}).get(LABEL) != "agents"
            or pod.status.phase != "Running"
            or not statuses
            or not all(s.ready for s in statuses)
            or "|".join(sorted(s.image_id or "" for s in statuses))
            != expected["image_id"]
        ):
            raise ValueError("gateway Pod identity/readiness/image changed")

    def delete(self, expected):
        self.core.delete_namespaced_pod(
            expected["name"],
            GATEWAY_NAMESPACE,
            body=self.client.V1DeleteOptions(
                preconditions=self.client.V1Preconditions(uid=expected["uid"])
            ),
            _request_timeout=5,
        )


def replace(api, state, path, *, now=time.time_ns):
    # Validate both targets before the first action. Never substitute new Pods.
    for pod in state["event"]["old_pods"]:
        api.gateway(pod)
    for pod in state["event"]["old_pods"]:
        api.active(state)
        api.gateway(pod)
        started = now()
        validate_event(state["event"], started)
        state["attempt"] = {
            "name": pod["name"],
            "uid": pod["uid"],
            "started_ns": started,
        }
        save(path, state)
        # API objects cannot be checked atomically together. Recheck the active
        # Job/Pod after the last inventory read and durable receipt write, then
        # enforce freshness again immediately before the UID-conditional DELETE.
        api.active(state)
        state["attempt"]["active_observation"] = state.get("active_observation")
        state["attempt"]["started_ns"] = now()
        validate_event(state["event"], state["attempt"]["started_ns"])
        api.delete(pod)
        state["deletions"].append({**state.pop("attempt"), "acknowledged_ns": now()})
        save(path, state)


def run(api, path):
    if path.exists():
        raise ValueError("use a fresh receipt path")
    state = {
        "schema": "t13-operator-v1",
        "started_ns": time.time_ns(),
        "deletions": [],
        "log_polls": 0,
    }
    save(path, state)
    try:
        until = time.monotonic() + 600
        while time.monotonic() < until:
            pod = api.active(state)
            if pod is not None:
                state["last_poll_started_ns"] = time.time_ns()
                raw = api.logs(pod)
                state["last_poll_finished_ns"] = time.time_ns()
                state["log_polls"] += 1
                for line in raw.splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(event, dict) and event.get("event") == EVENT:
                        validate_event(event, time.time_ns())
                        state["event"] = event
                        state["event_observed_ns"] = time.time_ns()
                        break
                save(path, state)
                if "event" in state:
                    replace(api, state, path)
                    return state
            time.sleep(0.25)
        raise TimeoutError("T13 signal deadline")
    except BaseException as exc:
        # Never write raw Kubernetes errors, arbitrary logs or credentials.
        state["error_type"] = type(exc).__name__
        state["failed_ns"] = time.time_ns()
        save(path, state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubeconfig", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if not args.kubeconfig.is_file():
        parser.error("explicit kubeconfig file required")
    try:
        state = run(API(args.kubeconfig), args.receipt)
    except Exception as exc:
        print(
            json.dumps({"receipt": str(args.receipt), "error_type": type(exc).__name__})
        )
        raise SystemExit(1) from None
    print(
        json.dumps({"receipt": str(args.receipt), "deletions": len(state["deletions"])})
    )


if __name__ == "__main__":
    main()
