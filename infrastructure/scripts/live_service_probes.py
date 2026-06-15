#!/usr/bin/env python3
"""Run read-only live probes against Kubani cluster services.

These are operational smoke probes, not CI-safe unit tests. They require a
reachable Kubernetes cluster and live service credentials in Kubernetes Secrets.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator


TIMEOUT_SECONDS = 30


@dataclass
class ProbeResult:
    name: str
    status: str
    message: str


class ProbeError(RuntimeError):
    """Raised when a live service probe fails."""


class ProbeSkip(RuntimeError):
    """Raised when an optional live service probe is intentionally skipped."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        return None


def run_command(args: list[str], *, input_text: str | None = None) -> str:
    result = subprocess.run(
        args,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ProbeError(detail or f"{args[0]} exited {result.returncode}")
    return result.stdout


def kubectl(args: list[str]) -> str:
    return run_command(["kubectl", *args])


def get_secret_value(namespace: str, name: str, key: str) -> str:
    encoded = kubectl(
        [
            "get",
            "secret",
            "-n",
            namespace,
            name,
            "-o",
            f"jsonpath={{.data.{key}}}",
        ]
    ).strip()
    if not encoded:
        raise ProbeError(f"secret {namespace}/{name} key {key} is empty or missing")
    return base64.b64decode(encoded).decode("utf-8")


def http_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    no_redirect: bool = False,
    basic_auth: tuple[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes, str]:
    request_headers = headers or {}
    if basic_auth is not None:
        user, password = basic_auth
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        request_headers = {**request_headers, "Authorization": f"Basic {token}"}

    request = urllib.request.Request(url, method=method, headers=request_headers)
    opener = urllib.request.build_opener(NoRedirectHandler) if no_redirect else urllib.request.build_opener()
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, dict(response.headers), response.read(), response.url
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read(), exc.url


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def port_forward(namespace: str, resource: str, remote_port: int) -> Iterator[int]:
    local_port = free_local_port()
    proc = subprocess.Popen(
        [
            "kubectl",
            "port-forward",
            "-n",
            namespace,
            "--address",
            "127.0.0.1",
            resource,
            f"{local_port}:{remote_port}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.time() + TIMEOUT_SECONDS
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                if sock.connect_ex(("127.0.0.1", local_port)) == 0:
                    yield local_port
                    return
            if proc.poll() is not None:
                output = proc.stdout.read() if proc.stdout else ""
                raise ProbeError(output.strip() or f"port-forward exited {proc.returncode}")
            time.sleep(0.2)
        raise ProbeError(f"timed out waiting for port-forward to {resource}:{remote_port}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def probe_cluster_reachable() -> str:
    kubectl(["cluster-info"])
    return "kubectl can reach the cluster"


def probe_neo4j_cypher() -> str:
    output = kubectl(
        [
            "exec",
            "-n",
            "database",
            "deploy/neo4j",
            "--",
            "bash",
            "-lc",
            'PASS="${NEO4J_AUTH#neo4j/}"; /var/lib/neo4j/bin/cypher-shell -a bolt://localhost:7687 -u neo4j -p "$PASS" "RETURN 1 AS ok"',
        ]
    )
    if "1" not in output:
        raise ProbeError("cypher-shell did not return expected sentinel value")
    return "Cypher read query returned expected sentinel"


def probe_qdrant_collections() -> str:
    api_key = get_secret_value("database", "qdrant-credentials", "api-key")
    with port_forward("database", "svc/qdrant", 6333) as port:
        status, _, body, _ = http_request(
            f"http://127.0.0.1:{port}/collections",
            headers={"api-key": api_key},
        )
    if status != 200:
        raise ProbeError(f"Qdrant returned HTTP {status}")
    payload = json.loads(body.decode("utf-8"))
    if payload.get("status") != "ok" or "result" not in payload:
        raise ProbeError("Qdrant response did not include expected status/result")
    return "Qdrant collections endpoint returned status ok"


def probe_registry_internal() -> str:
    output = kubectl(
        [
            "exec",
            "-n",
            "registry",
            "deploy/registry",
            "--",
            "wget",
            "-q",
            "-O-",
            "http://localhost:5000/v2/",
        ]
    )
    if output.strip() != "{}":
        raise ProbeError("registry internal /v2/ response was not the expected empty JSON object")
    return "internal registry /v2/ endpoint responded"


def probe_registry_external_challenge() -> str:
    status, headers, _, _ = http_request("https://registry.almckay.io/v2/", no_redirect=True)
    auth_header = headers.get("Www-Authenticate") or headers.get("WWW-Authenticate") or ""
    if status != 401:
        raise ProbeError(f"expected HTTP 401 auth challenge, got {status}")
    if "Basic" not in auth_header:
        raise ProbeError("registry auth challenge did not advertise Basic auth")
    return "external registry requires BasicAuth"


def probe_registry_external_authenticated() -> str:
    user = os.environ.get("KUBANI_REGISTRY_USER")
    password = os.environ.get("KUBANI_REGISTRY_PASSWORD")
    if not user or not password:
        raise ProbeSkip(
            "set KUBANI_REGISTRY_USER and KUBANI_REGISTRY_PASSWORD to test authenticated registry access"
        )
    status, _, body, _ = http_request(
        "https://registry.almckay.io/v2/_catalog",
        basic_auth=(user, password),
    )
    if status != 200:
        raise ProbeError(f"authenticated registry catalog returned HTTP {status}")
    payload = json.loads(body.decode("utf-8"))
    if "repositories" not in payload:
        raise ProbeError("authenticated registry catalog response omitted repositories")
    return "authenticated registry catalog request succeeded"


def probe_forward_auth(host: str) -> str:
    status, headers, _, _ = http_request(f"https://{host}/", no_redirect=True)
    location = headers.get("Location", "")
    if status not in {302, 303}:
        raise ProbeError(f"expected redirect to Authentik, got HTTP {status}")
    if "auth.almckay.io" not in location:
        raise ProbeError(f"redirect location did not target Authentik: {location}")
    return f"{host} redirects unauthenticated requests to Authentik"


def probe_temporal_web() -> str:
    status, _, _, _ = http_request("https://temporal.almckay.io/")
    if status != 200:
        raise ProbeError(f"Temporal Web returned HTTP {status}")
    return "Temporal Web responded over HTTPS"


def probe_vllm_models(host: str) -> str:
    status, _, body, _ = http_request(f"https://{host}/v1/models")
    if status != 200:
        raise ProbeError(f"{host} returned HTTP {status}")
    payload = json.loads(body.decode("utf-8"))
    if payload.get("object") != "list":
        raise ProbeError(f"{host} response was not an OpenAI-compatible model list")
    return f"{host} returned model list"


def run_probe(name: str, func: Callable[[], str]) -> ProbeResult:
    try:
        return ProbeResult(name, "PASS", func())
    except ProbeSkip as exc:
        return ProbeResult(name, "SKIP", str(exc))
    except Exception as exc:  # noqa: BLE001 - report all operational probe failures
        return ProbeResult(name, "FAIL", str(exc))


def build_probes(include_external: bool) -> list[tuple[str, Callable[[], str]]]:
    probes: list[tuple[str, Callable[[], str]]] = [
        ("cluster.reachable", probe_cluster_reachable),
        ("neo4j.cypher_read", probe_neo4j_cypher),
        ("qdrant.collections_read", probe_qdrant_collections),
        ("registry.internal_v2", probe_registry_internal),
    ]

    if include_external:
        probes.extend(
            [
                ("registry.external_auth_challenge", probe_registry_external_challenge),
                ("registry.external_authenticated", probe_registry_external_authenticated),
                ("neo4j.external_forward_auth", lambda: probe_forward_auth("neo4j.almckay.io")),
                ("qdrant.external_forward_auth", lambda: probe_forward_auth("qdrant.almckay.io")),
                ("temporal.web_https", probe_temporal_web),
                ("vllm.models", lambda: probe_vllm_models("llm.almckay.io")),
                ("vllm_fast.models", lambda: probe_vllm_models("llm-fast.almckay.io")),
                ("embeddings.models", lambda: probe_vllm_models("embeddings.almckay.io")),
            ]
        )
    return probes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--internal-only",
        action="store_true",
        help="skip public HTTPS route probes and only test in-cluster service interaction",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON",
    )
    args = parser.parse_args()

    if shutil.which("kubectl") is None:
        print("kubectl is required", file=sys.stderr)
        return 2

    results = [run_probe(name, func) for name, func in build_probes(not args.internal_only)]
    failures = [result for result in results if result.status == "FAIL"]

    if args.json:
        print(json.dumps([result.__dict__ for result in results], indent=2))
    else:
        print("Kubani live service probes")
        print("=" * 28)
        for result in results:
            marker = {"PASS": "OK", "SKIP": "SKIP", "FAIL": "FAIL"}[result.status]
            print(f"[{marker}] {result.name}: {result.message}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
