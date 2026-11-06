from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "inference_bench", ROOT / "infrastructure/scripts/inference_bench/bench.py"
)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


class InferenceBenchAuthTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.required_key = None
        owner = self

        class Engine(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                owner.requests.append((self.path, self.headers.get("Authorization")))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"version":"test"}')

            def do_POST(self):
                owner.requests.append((self.path, self.headers.get("Authorization")))
                self.rfile.read(int(self.headers["Content-Length"]))
                if owner.required_key and self.headers.get("Authorization") != owner.required_key:
                    self.send_response(401)
                    self.end_headers()
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(
                    b'data: {"choices":[{"text":"blue"}],'
                    b'"usage":{"prompt_tokens":2000,"completion_tokens":1}}\n\n'
                    b'data: [DONE]\n\n'
                )

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Engine)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def run_cli(self, key=None):
        with tempfile.TemporaryDirectory() as directory:
            profiles = Path(directory) / "profiles.json"
            profiles.write_text(json.dumps({"profiles": {"test": {
                "served_model": "test", "request_timeout_s": 5,
                "broker_url": self.url, "engine_url": self.url,
            }}}))
            argv = ["bench.py", "--profile", "test", "--profiles", str(profiles),
                    "--label", "auth-check", "--suites", ""]
            env = {"GPU_BROKER_ADMIN_TOKEN": "test-admin-credential"}
            if key:
                env["VLLM_API_KEY"] = key
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, env, clear=True), patch("sys.argv", argv), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(bench.main(), 0)
            return stdout.getvalue() + stderr.getvalue()

    def test_authenticated_completion_succeeds_without_disclosing_credentials(self):
        self.required_key = "Bearer test-engine-credential"
        output = self.run_cli("test-engine-credential")
        self.assertEqual(self.requests, [
            ("/version", None), ("/v1/completions", "Bearer test-engine-credential"),
        ])
        self.assertNotIn("test-engine-credential", output)
        self.assertNotIn("test-admin-credential", output)

    def test_gateway_without_engine_credential_remains_supported(self):
        self.run_cli()
        self.assertEqual(self.requests, [("/version", None), ("/v1/completions", None)])

    def test_admin_calls_use_only_the_admin_credential(self):
        with patch.dict(os.environ, {"VLLM_API_KEY": "test-engine-credential"}):
            runner = bench.Bench({"served_model": "test", "request_timeout_s": 5},
                                 self.url, self.url, self.url, "test-admin-credential",
                                 "test-engine-credential")
            self.assertEqual(runner.admin_call("GET", "/internal/v1/engines")[0], 200)
        self.assertEqual(self.requests, [("/internal/v1/engines", "Bearer test-admin-credential")])


if __name__ == "__main__":
    unittest.main()
