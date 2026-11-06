"""Exercise GitOps authorization with the pinned gateway and a local model stub.

RUN_GATEWAY_IMAGE_TESTS=1 python -m unittest discover -s tests -p test_inference_completion_bound.py
The container uses host networking only to reach this process's loopback stub.
No cluster access, JWT, backend credentials, or real model is involved.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ROOT / "infrastructure/gitops/apps/ai-gateway/agents/policies-auth.yaml"
IMAGE = "ghcr.io/agentgateway/agentgateway@sha256:60216aafb03d37f94e952ff3d51d2f630a65b10ecaebdc0a864882f92610c45b"
MODELS = {"llm-main": "Qwen3.6-35B-A3B-NVFP4", "llm-fast": "Qwen/Qwen3.5-0.8B"}


def policies():
    return {doc["metadata"]["name"]: doc for doc in yaml.safe_load_all(POLICIES.read_text())}


def inference_route(backend):
    path = POLICIES.with_name("routes.yaml")
    return next(doc["spec"]["rules"][0] for doc in yaml.safe_load_all(path.read_text())
                if doc["metadata"]["name"] == f"agents-inference-{backend}")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CompletionPolicyTests(unittest.TestCase):
    def test_model_bounds_are_required_alongside_agent_allow(self):
        for backend in MODELS:
            with self.subTest(backend=backend):
                policy = policies()[f"agents-inference-{backend}-model-pin"]
                self.assertEqual(policy["spec"]["traffic"]["authorization"]["action"], "Require")


@unittest.skipUnless(os.environ.get("RUN_GATEWAY_IMAGE_TESTS") == "1", "opt-in pinned Docker image regression")
class CompletionGatewayTests(unittest.TestCase):
    models = MODELS

    def authorization(self, backend):
        return policies()[f"agents-inference-{backend}-model-pin"]["spec"]["traffic"]["authorization"]

    def route(self, backend):
        return inference_route(backend)

    def additional_cases(self, base):
        return [("beam-off", {**base, "use_beam_search": False}, True)]

    def test_actual_request_body_and_model_cannot_bypass_allow(self):
        for backend, model in self.models.items():
            with self.subTest(backend=backend):
                self.check_backend(backend, model)

    def check_backend(self, backend, model):
        received = []

        class ModelStub(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append(body)
                response = json.dumps({
                    "id": "local-stub", "object": "chat.completion", "created": 1,
                    "model": model, "choices": [{"index": 0,
                        "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

        server = ThreadingHTTPServer(("127.0.0.1", 0), ModelStub)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = free_port()
        auth = self.authorization(backend)
        # Match the pinned controller TranslateAuthorization: one entry per
        # expression, all Require entries cumulative. Independent Allow models
        # the valid-agent rule so a model-bound Allow regression is observable.
        rules = [{"allow": "true"}] + [
            {auth["action"].lower(): expression}
            for expression in auth["policy"]["matchExpressions"]
        ]
        route = self.route(backend)
        path_match = route["matches"][0]["path"]
        rewrite = route["filters"][0]["urlRewrite"]["path"]
        config = {
            "config": {"readinessAddr": f"127.0.0.1:{free_port()}", "statsAddr": f"127.0.0.1:{free_port()}"},
            "frontendPolicies": {"http": {"maxBufferSize": 8192}},
            "binds": [{"port": port, "listeners": [{"protocol": "HTTP", "routes": [{
                "matches": [{"path": {"exact" if path_match["type"] == "Exact" else "pathPrefix": path_match["value"]}, "method": "POST"}],
                "backends": [{"ai": {"name": "stub", "provider": {"openAI": {"model": model}},
                    "hostOverride": f"127.0.0.1:{server.server_port}"}}],
                "policies": {"urlRewrite": {"path": {"full" if rewrite["type"] == "ReplaceFullPath" else "prefix": rewrite.get("replaceFullPath", rewrite.get("replacePrefixMatch"))}}, "authorization": {"rules": rules}},
            }]}]}],
        }
        name = "completion-bound-" + uuid.uuid4().hex[:12]
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.yaml"
                path.write_text(yaml.safe_dump(config))
                subprocess.run(["docker", "run", "--detach", "--name", name, "--network", "host",
                    "--read-only", "--tmpfs", "/tmp", "--volume", f"{path}:/config.yaml:ro",
                    IMAGE, "-f", "/config.yaml"], check=True, capture_output=True)
                deadline = time.monotonic() + 15
                while True:
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                            break
                    except OSError:
                        if time.monotonic() >= deadline:
                            logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True).stdout
                            self.fail("local gateway did not start: " + logs[-4000:])
                        time.sleep(0.1)
                base = {"model": model, "messages": [{"role": "user", "content": "hello"}], "max_tokens": 1}
                cases = [("default", base, True), ("one", {**base, "n": 1}, True)]
                cases += self.additional_cases(base)
                cases += [(f"n-{i}", {**base, "n": value}, False)
                          for i, value in enumerate([2, 0, -1, True, "1", None, 1.5, [], {}])]
                cases += [("wrong-model", {**base, "model": "unapproved"}, False),
                          ("malformed", b'{"model":', False),
                          ("oversized", {**base, "messages": [{"role": "user", "content": "a" * 9000}]}, False),
                          ("best-of", {**base, "best_of": 2}, False),
                          ("beam", {**base, "use_beam_search": True}, False),
                          ("duplicate-n", json.dumps(base)[:-1].encode() + b',"n":1,"n":2}', False)]
                for label, body, allowed in cases:
                    with self.subTest(case=label):
                        before = len(received)
                        data = body if isinstance(body, bytes) else json.dumps(body).encode()
                        # Untrusted hint headers must not override the body.
                        request = Request(f"http://127.0.0.1:{port}/models/{backend}/v1/chat/completions", data=data,
                            headers={"Content-Type": "application/json", "x-n": "1", "x-request-n": "1"})
                        try:
                            with urlopen(request, timeout=5) as response:
                                status = response.status
                                response.read()
                        except HTTPError as error:
                            status = error.code
                            error.read()
                        except URLError as error:
                            self.fail(f"local gateway transport failed: {type(error.reason).__name__}")
                        if allowed:
                            self.assertEqual(status, 200)
                            self.assertEqual(len(received) - before, 1)
                            self.assertEqual(received[-1].get("n", 1), 1)
                        else:
                            self.assertIn(status, (400, 403, 413), f"{label} must fail closed")
                            self.assertEqual(len(received), before, "denied request reached upstream")
                for suffix in ("completions", "chat/completions/batch", "chat/completions/", "responses"):
                    with self.subTest(path=suffix):
                        before = len(received)
                        request = Request(f"http://127.0.0.1:{port}/models/{backend}/v1/{suffix}",
                            data=json.dumps(base).encode(), headers={"Content-Type": "application/json"})
                        try:
                            with urlopen(request, timeout=5) as response:
                                status = response.status
                                response.read()
                        except HTTPError as error:
                            status = error.code
                            error.read()
                        self.assertEqual(status, 404, "non-chat endpoints must not match an inference route")
                        self.assertEqual(len(received), before)
        finally:
            subprocess.run(["docker", "rm", "--force", name], capture_output=True)
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
